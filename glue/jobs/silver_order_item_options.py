"""Validate Bronze order-item options against accepted Silver order items."""

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
    max as spark_max,
    row_number,
    size,
    trim,
    when,
)
from pyspark.sql.window import Window


TABLE_NAME = "order_item_options"
EXPECTED_COLUMNS = {
    "order_id",
    "lineitem_id",
    "option_group_name",
    "option_name",
    "option_price",
    "option_quantity",
}
REPEAT_KEY_COLUMNS = [
    "order_id",
    "lineitem_id",
    "option_group_name",
    "option_name",
    "option_price",
    "option_quantity",
]


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
    """Run Bronze-to-Silver option validation and parent checks."""
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
    silver_order_items_path = (
        f"s3://{bucket}/silver/order_items/load_date={load_date}/"
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
                "event": "silver_order_item_options_started",
                "run_id": run_id,
                "load_date": load_date,
                "input_path": input_path,
                "silver_order_items_path": silver_order_items_path,
            }
        )
    )

    source = spark.read.parquet(input_path).cache()
    input_count = source.count()

    if input_count == 0:
        raise RuntimeError(
            "The Bronze order_item_options partition returned zero rows; "
            "existing Silver output was not replaced."
        )

    missing_columns = sorted(EXPECTED_COLUMNS.difference(source.columns))
    if missing_columns:
        raise RuntimeError(
            "Bronze order_item_options is missing expected columns: "
            + ", ".join(missing_columns)
        )

    accepted_order_items = spark.read.parquet(silver_order_items_path)
    parent_pairs = (
        accepted_order_items.select(
            col("order_id").alias("_parent_order_id_for_pair"),
            col("lineitem_id").alias("_parent_lineitem_id"),
        )
        .filter(
            col("_parent_order_id_for_pair").isNotNull()
            & col("_parent_lineitem_id").isNotNull()
        )
        .distinct()
        .cache()
    )
    parent_orders = (
        accepted_order_items.select(
            col("order_id").alias("_parent_order_id")
        )
        .filter(col("_parent_order_id").isNotNull())
        .distinct()
        .cache()
    )

    parent_pair_count = parent_pairs.count()
    parent_order_count = parent_orders.count()

    if parent_pair_count == 0 or parent_order_count == 0:
        raise RuntimeError(
            "The accepted Silver order_items partition returned no parent keys."
        )

    repeat_group_window = Window.partitionBy(*REPEAT_KEY_COLUMNS)
    repeat_sequence_window = Window.partitionBy(*REPEAT_KEY_COLUMNS).orderBy(
        lit(1)
    )

    typed = (
        source.withColumn("order_id", cleaned_string("order_id"))
        .withColumn("lineitem_id", cleaned_string("lineitem_id"))
        .withColumn(
            "option_group_name", cleaned_string("option_group_name")
        )
        .withColumn("option_name", cleaned_string("option_name"))
        .withColumn(
            "option_price", col("option_price").cast("decimal(18,2)")
        )
        .withColumn(
            "option_quantity", col("option_quantity").cast("integer")
        )
        .withColumn(
            "_source_repeat_group_size",
            count(lit(1)).over(repeat_group_window),
        )
        .withColumn(
            "_source_repeat_occurrence_number",
            row_number().over(repeat_sequence_window),
        )
        .cache()
    )

    repeated_groups = (
        typed.filter(col("_source_repeat_group_size") > 1)
        .select(*REPEAT_KEY_COLUMNS)
        .distinct()
        .count()
    )
    rows_in_repeated_groups = typed.filter(
        col("_source_repeat_group_size") > 1
    ).count()
    repeated_rows_after_first = typed.filter(
        col("_source_repeat_occurrence_number") > 1
    ).count()
    maximum_repeat_group_size = typed.agg(
        spark_max(col("_source_repeat_group_size")).alias("maximum")
    ).first()["maximum"]

    joined_pairs = typed.join(
        broadcast(parent_pairs),
        (typed["order_id"] == parent_pairs["_parent_order_id_for_pair"])
        & (typed["lineitem_id"] == parent_pairs["_parent_lineitem_id"]),
        "left",
    )
    joined = joined_pairs.join(
        broadcast(parent_orders),
        joined_pairs["order_id"] == parent_orders["_parent_order_id"],
        "left",
    )

    quarantine_reason_columns = [
        when(col("order_id").isNull(), lit("MISSING_ORDER_ID")),
        when(col("lineitem_id").isNull(), lit("MISSING_LINEITEM_ID")),
        when(
            col("option_group_name").isNull(),
            lit("MISSING_OPTION_GROUP_NAME"),
        ),
        when(col("option_name").isNull(), lit("MISSING_OPTION_NAME")),
        when(
            col("option_price").isNull(),
            lit("MISSING_OR_INVALID_OPTION_PRICE"),
        ),
        when(col("option_price") < 0, lit("NEGATIVE_OPTION_PRICE")),
        when(
            col("option_quantity").isNull(),
            lit("MISSING_OR_INVALID_OPTION_QUANTITY"),
        ),
        when(
            col("option_quantity").isNotNull()
            & (col("option_quantity") <= 0),
            lit("NON_POSITIVE_OPTION_QUANTITY"),
        ),
        when(
            col("order_id").isNotNull()
            & col("_parent_order_id").isNull(),
            lit("ORPHAN_ORDER_ID"),
        ),
        when(
            col("order_id").isNotNull()
            & col("lineitem_id").isNotNull()
            & col("_parent_lineitem_id").isNull(),
            lit("ORPHAN_ORDER_LINEITEM"),
        ),
    ]

    quality_flag_columns = [
        when(
            col("_source_repeat_occurrence_number") > 1,
            lit("REPEATED_SOURCE_OCCURRENCE"),
        )
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
        .withColumn("_silver_run_id", lit(run_id))
        .withColumn("_silver_processed_at_utc", lit(processed_at_utc))
        .drop(
            "_parent_order_id_for_pair",
            "_parent_lineitem_id",
            "_parent_order_id",
        )
        .cache()
    )

    accepted = validated.filter(col("_quality_status") == "ACCEPTED")
    quarantined = validated.filter(col("_quality_status") == "QUARANTINED")

    accepted_count = accepted.count()
    quarantined_count = quarantined.count()

    if input_count != accepted_count + quarantined_count:
        raise RuntimeError(
            "Option reconciliation failed: "
            f"input={input_count}, accepted={accepted_count}, "
            f"quarantined={quarantined_count}"
        )

    if accepted_count == 0:
        raise RuntimeError(
            "No option rows passed validation; "
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

    orphan_rows = validated.filter(
        expr("array_contains(_quality_reason_codes, 'ORPHAN_ORDER_LINEITEM')")
    ).cache()
    distinct_orphan_order_ids = orphan_rows.select("order_id").distinct().count()
    distinct_orphan_order_lineitem_pairs = (
        orphan_rows.select("order_id", "lineitem_id").distinct().count()
    )

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
        "silver_order_items_path": silver_order_items_path,
        "accepted_output_path": accepted_path,
        "quarantine_output_path": quarantine_path,
        "parent_order_count": parent_order_count,
        "parent_order_lineitem_pair_count": parent_pair_count,
        "input_count": input_count,
        "accepted_count": accepted_count,
        "quarantined_count": quarantined_count,
        "quality_reason_counts": reason_counts,
        "quality_flag_counts": flag_counts,
        "distinct_orphan_order_ids": distinct_orphan_order_ids,
        "distinct_orphan_order_lineitem_pairs": (
            distinct_orphan_order_lineitem_pairs
        ),
        "repeated_groups": repeated_groups,
        "rows_in_repeated_groups": rows_in_repeated_groups,
        "repeated_rows_after_first": repeated_rows_after_first,
        "maximum_repeat_group_size": maximum_repeat_group_size,
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

    orphan_rows.unpersist()
    validated.unpersist()
    typed.unpersist()
    parent_orders.unpersist()
    parent_pairs.unpersist()
    source.unpersist()
    job.commit()


if __name__ == "__main__":
    main()
