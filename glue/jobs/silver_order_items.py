"""Validate Bronze order items and write accepted and quarantined Silver records."""

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
    broadcast,
    col,
    count,
    explode,
    expr,
    length,
    lit,
    lower,
    size,
    to_date,
    to_timestamp,
    trim,
    upper,
    when,
)
from pyspark.sql.window import Window


TABLE_NAME = "order_items"
EXPECTED_COLUMNS = {
    "app_name",
    "restaurant_id",
    "creation_time_utc",
    "order_id",
    "user_id",
    "printed_card_number",
    "is_loyalty",
    "currency",
    "lineitem_id",
    "item_category",
    "item_name",
    "item_price",
    "item_quantity",
}


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


def cleaned_string(column_name: str):
    """Trim a string and convert blank values to null."""
    value = trim(col(column_name).cast("string"))
    return when(length(value) == 0, lit(None).cast("string")).otherwise(value)


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
    """Run Bronze-to-Silver order-item validation."""
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
    silver_date_path = (
        f"s3://{bucket}/silver/date_dim/load_date={load_date}/"
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
                "event": "silver_order_items_started",
                "run_id": run_id,
                "load_date": load_date,
                "input_path": input_path,
                "silver_date_path": silver_date_path,
            }
        )
    )

    source = spark.read.parquet(input_path).cache()
    input_count = source.count()

    if input_count == 0:
        raise RuntimeError(
            "The Bronze order_items partition returned zero rows; "
            "existing Silver output was not replaced."
        )

    missing_columns = sorted(EXPECTED_COLUMNS.difference(source.columns))
    if missing_columns:
        raise RuntimeError(
            "Bronze order_items is missing expected columns: "
            + ", ".join(missing_columns)
        )

    silver_dates = (
        spark.read.parquet(silver_date_path)
        .select(to_date(col("date_key")).alias("_matched_date_key"))
        .filter(col("_matched_date_key").isNotNull())
        .distinct()
        .cache()
    )
    silver_date_count = silver_dates.count()

    if silver_date_count == 0:
        raise RuntimeError(
            "The accepted Silver date_dim partition returned zero dates."
        )

    typed = (
        source.withColumn("app_name", cleaned_string("app_name"))
        .withColumn("restaurant_id", cleaned_string("restaurant_id"))
        .withColumn(
            "creation_time_utc", to_timestamp(col("creation_time_utc"))
        )
        .withColumn("order_id", cleaned_string("order_id"))
        .withColumn("user_id", cleaned_string("user_id"))
        .withColumn(
            "printed_card_number", cleaned_string("printed_card_number")
        )
        .withColumn("is_loyalty", normalized_boolean("is_loyalty"))
        .withColumn("currency", upper(cleaned_string("currency")))
        .withColumn("lineitem_id", cleaned_string("lineitem_id"))
        .withColumn("item_category", cleaned_string("item_category"))
        .withColumn("item_name", cleaned_string("item_name"))
        .withColumn("item_price", col("item_price").cast("decimal(18,2)"))
        .withColumn("item_quantity", col("item_quantity").cast("integer"))
        .withColumn("_order_date", to_date(col("creation_time_utc")))
        .withColumn(
            "_lineitem_id_count",
            count(lit(1)).over(Window.partitionBy("lineitem_id")),
        )
    )

    joined = typed.join(
        broadcast(silver_dates),
        typed["_order_date"] == silver_dates["_matched_date_key"],
        "left",
    )

    quarantine_reason_columns = [
        when(col("app_name").isNull(), lit("MISSING_APP_NAME")),
        when(col("restaurant_id").isNull(), lit("MISSING_RESTAURANT_ID")),
        when(
            col("creation_time_utc").isNull(),
            lit("MISSING_OR_INVALID_CREATION_TIME_UTC"),
        ),
        when(col("order_id").isNull(), lit("MISSING_ORDER_ID")),
        when(
            col("is_loyalty").isNull(),
            lit("MISSING_OR_INVALID_IS_LOYALTY"),
        ),
        when(col("currency").isNull(), lit("MISSING_CURRENCY")),
        when(col("lineitem_id").isNull(), lit("MISSING_LINEITEM_ID")),
        when(
            col("lineitem_id").isNotNull()
            & (col("_lineitem_id_count") > 1),
            lit("DUPLICATE_LINEITEM_ID"),
        ),
        when(col("item_category").isNull(), lit("MISSING_ITEM_CATEGORY")),
        when(col("item_name").isNull(), lit("MISSING_ITEM_NAME")),
        when(
            col("item_price").isNull(),
            lit("MISSING_OR_INVALID_ITEM_PRICE"),
        ),
        when(col("item_price") < 0, lit("NEGATIVE_ITEM_PRICE")),
        when(
            col("item_quantity").isNull(),
            lit("MISSING_OR_INVALID_ITEM_QUANTITY"),
        ),
        when(
            col("item_quantity").isNotNull()
            & (col("item_quantity") <= 0),
            lit("NON_POSITIVE_ITEM_QUANTITY"),
        ),
    ]

    quality_flag_columns = [
        when(col("user_id").isNull(), lit("MISSING_USER_ID")),
        when(
            col("printed_card_number").isNull(),
            lit("MISSING_PRINTED_CARD_NUMBER"),
        ),
        when(
            col("_matched_date_key").isNull(),
            lit("DATE_OUTSIDE_SUPPLIED_DIMENSION"),
        ),
        when(
            lower(col("app_name")).contains("development"),
            lit("DEVELOPMENT_APP"),
        ),
    ]

    validated = (
        joined.withColumn(
            "_quality_reason_codes", array(*quarantine_reason_columns)
        )
        .withColumn(
            "_quality_reason_codes",
            expr("filter(_quality_reason_codes, reason -> reason is not null)"),
        )
        .withColumn("_quality_flag_codes", array(*quality_flag_columns))
        .withColumn(
            "_quality_flag_codes",
            expr("filter(_quality_flag_codes, flag -> flag is not null)"),
        )
        .withColumn(
            "_quality_status",
            when(
                size(col("_quality_reason_codes")) == 0,
                lit("ACCEPTED"),
            ).otherwise(lit("QUARANTINED")),
        )
        .withColumn(
            "_date_dimension_match", col("_matched_date_key").isNotNull()
        )
        .withColumn("_silver_run_id", lit(run_id))
        .withColumn("_silver_processed_at_utc", lit(processed_at_utc))
        .drop("_matched_date_key", "_lineitem_id_count")
        .cache()
    )

    accepted = validated.filter(col("_quality_status") == "ACCEPTED")
    quarantined = validated.filter(col("_quality_status") == "QUARANTINED")

    accepted_count = accepted.count()
    quarantined_count = quarantined.count()

    if input_count != accepted_count + quarantined_count:
        raise RuntimeError(
            "Order-item reconciliation failed: "
            f"input={input_count}, accepted={accepted_count}, "
            f"quarantined={quarantined_count}"
        )

    if accepted_count == 0:
        raise RuntimeError(
            "No order-item rows passed validation; "
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
    flag_counts = {
        row["flag"]: row["count"]
        for row in (
            validated.select(
                explode(col("_quality_flag_codes")).alias("flag")
            )
            .groupBy("flag")
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
        "silver_date_path": silver_date_path,
        "accepted_output_path": accepted_path,
        "quarantine_output_path": quarantine_path,
        "input_count": input_count,
        "accepted_count": accepted_count,
        "quarantined_count": quarantined_count,
        "quality_reason_counts": reason_counts,
        "quality_flag_counts": flag_counts,
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

    silver_dates.unpersist()
    validated.unpersist()
    source.unpersist()
    job.commit()


if __name__ == "__main__":
    main()
