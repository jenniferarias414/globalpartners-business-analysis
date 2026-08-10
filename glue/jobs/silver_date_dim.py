"""Validate the Bronze date dimension and write accepted Silver records."""

import json
import sys
import uuid
from datetime import datetime, timezone

import boto3
from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from pyspark.sql import DataFrame
from pyspark.sql.functions import (
    array,
    col,
    count,
    date_format,
    dayofweek,
    explode,
    expr,
    length,
    lit,
    lower,
    month as spark_month,
    size,
    to_date,
    trim,
    weekofyear,
    when,
    year as spark_year,
)
from pyspark.sql.window import Window


TABLE_NAME = "date_dim"


def get_optional_argument(name: str, default: str) -> str:
    """Return an optional Glue argument or its default value."""
    flag = f"--{name}"
    if flag not in sys.argv:
        return default

    value_index = sys.argv.index(flag) + 1
    if value_index >= len(sys.argv):
        raise ValueError(f"Missing value for {flag}")

    return sys.argv[value_index]


def validate_load_date(value: str) -> str:
    """Require the processing date to use YYYY-MM-DD format."""
    datetime.strptime(value, "%Y-%m-%d")
    return value


def normalized_boolean(column_name: str):
    """Convert common source representations to a nullable Boolean value."""
    normalized_value = lower(trim(col(column_name).cast("string")))
    return (
        when(normalized_value.isin("true", "1"), lit(True))
        .when(normalized_value.isin("false", "0"), lit(False))
        .otherwise(lit(None).cast("boolean"))
    )


def delete_s3_prefix(s3_client, bucket: str, prefix: str) -> int:
    """Delete current objects under one same-date output prefix."""
    deleted_count = 0
    paginator = s3_client.get_paginator("list_objects_v2")

    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        keys = [item["Key"] for item in page.get("Contents", [])]

        for start in range(0, len(keys), 1000):
            batch = keys[start : start + 1000]
            s3_client.delete_objects(
                Bucket=bucket,
                Delete={
                    "Objects": [{"Key": key} for key in batch],
                    "Quiet": True,
                },
            )
            deleted_count += len(batch)

    return deleted_count


def write_parquet(dataframe: DataFrame, output_path: str) -> None:
    """Write Snappy-compressed Parquet to an exact S3 path."""
    (
        dataframe.write.mode("overwrite")
        .format("parquet")
        .option("compression", "snappy")
        .save(output_path)
    )


def main() -> None:
    """Run the Bronze-to-Silver date-dimension validation."""
    args = getResolvedOptions(sys.argv, ["JOB_NAME", "data_bucket"])

    default_load_date = datetime.now(timezone.utc).date().isoformat()
    load_date = validate_load_date(
        get_optional_argument("load_date", default_load_date)
    )
    run_id = get_optional_argument("run_id", str(uuid.uuid4()))
    processed_at_utc = datetime.now(timezone.utc).isoformat()

    spark_context = SparkContext.getOrCreate()
    glue_context = GlueContext(spark_context)
    spark = glue_context.spark_session
    job = Job(glue_context)
    job.init(args["JOB_NAME"], args)

    bucket = args["data_bucket"]
    input_path = (
        f"s3://{bucket}/bronze/sqlserver/dbo/{TABLE_NAME}/"
        f"load_date={load_date}/"
    )
    accepted_prefix = f"silver/{TABLE_NAME}/load_date={load_date}/"
    quarantine_prefix = (
        f"quarantine/silver/{TABLE_NAME}/load_date={load_date}/"
    )
    accepted_path = f"s3://{bucket}/{accepted_prefix}"
    quarantine_path = f"s3://{bucket}/{quarantine_prefix}"

    print(
        json.dumps(
            {
                "event": "silver_date_dim_started",
                "run_id": run_id,
                "load_date": load_date,
                "input_path": input_path,
            }
        )
    )

    source = spark.read.parquet(input_path).cache()
    input_count = source.count()

    if input_count == 0:
        raise RuntimeError(
            "The Bronze date_dim partition returned zero rows; "
            "existing Silver output was not replaced."
        )

    typed = (
        source.withColumn("date_key", to_date(col("date_key")))
        .withColumn("year", col("year").cast("integer"))
        .withColumn("month", col("month").cast("integer"))
        .withColumn("week", col("week").cast("integer"))
        .withColumn("day_of_week", trim(col("day_of_week").cast("string")))
        .withColumn("is_weekend", normalized_boolean("is_weekend"))
        .withColumn("is_holiday", normalized_boolean("is_holiday"))
        .withColumn(
            "holiday_name",
            when(
                length(trim(col("holiday_name").cast("string"))) == 0,
                lit(None).cast("string"),
            ).otherwise(trim(col("holiday_name").cast("string"))),
        )
        .withColumn(
            "_date_key_count",
            count(lit(1)).over(Window.partitionBy("date_key")),
        )
    )

    reason_columns = [
        when(col("date_key").isNull(), lit("MISSING_OR_INVALID_DATE_KEY")),
        when(
            col("date_key").isNotNull() & (col("_date_key_count") > 1),
            lit("DUPLICATE_DATE_KEY"),
        ),
        when(col("year").isNull(), lit("MISSING_OR_INVALID_YEAR")),
        when(
            col("date_key").isNotNull()
            & col("year").isNotNull()
            & (col("year") != spark_year(col("date_key"))),
            lit("YEAR_MISMATCH"),
        ),
        when(col("month").isNull(), lit("MISSING_OR_INVALID_MONTH")),
        when(
            col("date_key").isNotNull()
            & col("month").isNotNull()
            & (col("month") != spark_month(col("date_key"))),
            lit("MONTH_MISMATCH"),
        ),
        when(col("week").isNull(), lit("MISSING_OR_INVALID_WEEK")),
        when(
            col("date_key").isNotNull()
            & col("week").isNotNull()
            & (col("week") != weekofyear(col("date_key"))),
            lit("WEEK_MISMATCH"),
        ),
        when(
            col("day_of_week").isNull() | (length(col("day_of_week")) == 0),
            lit("MISSING_DAY_OF_WEEK"),
        ),
        when(
            col("date_key").isNotNull()
            & col("day_of_week").isNotNull()
            & (
                lower(col("day_of_week"))
                != lower(date_format(col("date_key"), "EEEE"))
            ),
            lit("DAY_OF_WEEK_MISMATCH"),
        ),
        when(col("is_weekend").isNull(), lit("MISSING_OR_INVALID_IS_WEEKEND")),
        when(
            col("date_key").isNotNull()
            & col("is_weekend").isNotNull()
            & (col("is_weekend") != dayofweek(col("date_key")).isin(1, 7)),
            lit("WEEKEND_FLAG_MISMATCH"),
        ),
        when(col("is_holiday").isNull(), lit("MISSING_OR_INVALID_IS_HOLIDAY")),
        when(
            (col("is_holiday") == lit(True)) & col("holiday_name").isNull(),
            lit("HOLIDAY_NAME_MISSING"),
        ),
        when(
            (col("is_holiday") == lit(False))
            & col("holiday_name").isNotNull(),
            lit("HOLIDAY_NAME_WITH_FALSE_FLAG"),
        ),
    ]

    validated = (
        typed.withColumn("_quality_reason_codes", array(*reason_columns))
        .withColumn(
            "_quality_reason_codes",
            expr("filter(_quality_reason_codes, reason -> reason is not null)"),
        )
        .withColumn(
            "_quality_status",
            when(
                size(col("_quality_reason_codes")) == 0,
                lit("ACCEPTED"),
            ).otherwise(lit("QUARANTINED")),
        )
        .withColumn("_silver_run_id", lit(run_id))
        .withColumn("_silver_processed_at_utc", lit(processed_at_utc))
        .drop("_date_key_count")
        .cache()
    )

    accepted = validated.filter(col("_quality_status") == "ACCEPTED")
    quarantined = validated.filter(col("_quality_status") == "QUARANTINED")

    accepted_count = accepted.count()
    quarantined_count = quarantined.count()

    if input_count != accepted_count + quarantined_count:
        raise RuntimeError(
            "Date-dimension reconciliation failed: "
            f"input={input_count}, accepted={accepted_count}, "
            f"quarantined={quarantined_count}"
        )

    if accepted_count == 0:
        raise RuntimeError(
            "No date-dimension rows passed validation; "
            "existing Silver output was not replaced."
        )

    reason_counts = {
        row["reason"]: row["count"]
        for row in (
            quarantined.select(
                explode(col("_quality_reason_codes")).alias("reason")
            )
            .groupBy("reason")
            .count()
            .collect()
        )
    }

    s3_client = boto3.client("s3")
    deleted_accepted_objects = delete_s3_prefix(
        s3_client, bucket, accepted_prefix
    )
    deleted_quarantine_objects = delete_s3_prefix(
        s3_client, bucket, quarantine_prefix
    )

    write_parquet(accepted, accepted_path)

    if quarantined_count > 0:
        write_parquet(quarantined, quarantine_path)

    control_key = (
        f"control/silver/{TABLE_NAME}/load_date={load_date}/"
        f"run_id={run_id}/silver_{TABLE_NAME}_summary.json"
    )
    control_document = {
        "status": "SUCCEEDED",
        "job_name": args["JOB_NAME"],
        "table_name": TABLE_NAME,
        "run_id": run_id,
        "load_date": load_date,
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "input_path": input_path,
        "accepted_output_path": accepted_path,
        "quarantine_output_path": quarantine_path,
        "input_count": input_count,
        "accepted_count": accepted_count,
        "quarantined_count": quarantined_count,
        "quality_reason_counts": reason_counts,
        "objects_deleted_before_write": {
            "accepted": deleted_accepted_objects,
            "quarantine": deleted_quarantine_objects,
        },
        "reconciliation_passed": (
            input_count == accepted_count + quarantined_count
        ),
    }

    s3_client.put_object(
        Bucket=bucket,
        Key=control_key,
        Body=json.dumps(control_document, indent=2).encode("utf-8"),
        ContentType="application/json",
    )

    print(json.dumps(control_document))

    validated.unpersist()
    source.unpersist()
    job.commit()


if __name__ == "__main__":
    main()
