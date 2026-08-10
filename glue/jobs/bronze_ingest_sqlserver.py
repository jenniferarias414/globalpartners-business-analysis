"""Extract SQL Server source tables to the S3 Bronze layer as Parquet snapshots."""

import json
import sys
import uuid
from datetime import datetime, timezone

import boto3
from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from pyspark.sql.functions import lit


SOURCE_SCHEMA = "dbo"
SOURCE_TABLES = (
    "date_dim",
    "order_items",
    "order_item_options",
)


def get_optional_argument(name: str, default: str) -> str:
    """Return an optional Glue job argument or its default value."""
    flag = f"--{name}"
    if flag not in sys.argv:
        return default

    value_index = sys.argv.index(flag) + 1
    if value_index >= len(sys.argv):
        raise ValueError(f"Missing value for {flag}")

    return sys.argv[value_index]


def validate_load_date(value: str) -> str:
    """Require the partition date to use YYYY-MM-DD format."""
    datetime.strptime(value, "%Y-%m-%d")
    return value


def delete_s3_prefix(s3_client, bucket: str, prefix: str) -> int:
    """Delete current objects under a partition prefix before a reload."""
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


def main() -> None:
    """Run the SQL Server-to-Bronze snapshot ingestion."""
    args = getResolvedOptions(
        sys.argv,
        [
            "JOB_NAME",
            "source_connection_name",
            "destination_bucket",
        ],
    )

    default_load_date = datetime.now(timezone.utc).date().isoformat()
    load_date = validate_load_date(
        get_optional_argument("load_date", default_load_date)
    )
    run_id = get_optional_argument("run_id", str(uuid.uuid4()))
    ingested_at_utc = datetime.now(timezone.utc).isoformat()

    spark_context = SparkContext.getOrCreate()
    glue_context = GlueContext(spark_context)
    job = Job(glue_context)
    job.init(args["JOB_NAME"], args)

    s3_client = boto3.client("s3")
    summaries = []

    print(
        json.dumps(
            {
                "event": "bronze_ingestion_started",
                "load_date": load_date,
                "run_id": run_id,
                "source_connection": args["source_connection_name"],
                "destination_bucket": args["destination_bucket"],
            }
        )
    )

    for table_name in SOURCE_TABLES:
        qualified_table = f"{SOURCE_SCHEMA}.{table_name}"
        output_prefix = (
            f"bronze/sqlserver/{SOURCE_SCHEMA}/{table_name}/"
            f"load_date={load_date}/"
        )
        output_path = f"s3://{args['destination_bucket']}/{output_prefix}"

        print(f"Reading {qualified_table} through AWS Glue JDBC connection...")

        source_dynamic_frame = glue_context.create_dynamic_frame.from_options(
            connection_type="sqlserver",
            connection_options={
                "useConnectionProperties": "true",
                "connectionName": args["source_connection_name"],
                "dbtable": qualified_table,
            },
            transformation_ctx=f"read_{table_name}",
        )

        dataframe = (
            source_dynamic_frame.toDF()
            .withColumn("_source_system", lit("rds_sqlserver"))
            .withColumn("_source_schema", lit(SOURCE_SCHEMA))
            .withColumn("_source_table", lit(table_name))
            .withColumn("_load_date", lit(load_date))
            .withColumn("_run_id", lit(run_id))
            .withColumn("_ingested_at_utc", lit(ingested_at_utc))
        )

        dataframe.cache()
        row_count = dataframe.count()

        if row_count == 0:
            raise RuntimeError(
                f"Source table {qualified_table} returned zero rows; "
                "the existing Bronze partition was not replaced."
            )

        deleted_objects = delete_s3_prefix(
            s3_client,
            args["destination_bucket"],
            output_prefix,
        )

        print(
            f"Writing {row_count:,} rows from {qualified_table} to {output_path}"
        )

        (
            dataframe.write.mode("overwrite")
            .format("parquet")
            .option("compression", "snappy")
            .save(output_path)
        )

        dataframe.unpersist()

        table_summary = {
            "source_table": qualified_table,
            "row_count": row_count,
            "output_path": output_path,
            "objects_deleted_before_write": deleted_objects,
        }
        summaries.append(table_summary)
        print(json.dumps(table_summary))

    control_key = (
        f"control/bronze/load_date={load_date}/"
        f"run_id={run_id}/bronze_ingestion_summary.json"
    )
    control_document = {
        "status": "SUCCEEDED",
        "job_name": args["JOB_NAME"],
        "run_id": run_id,
        "load_date": load_date,
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "tables": summaries,
    }

    s3_client.put_object(
        Bucket=args["destination_bucket"],
        Key=control_key,
        Body=json.dumps(control_document, indent=2).encode("utf-8"),
        ContentType="application/json",
    )

    print(
        json.dumps(
            {
                "event": "bronze_ingestion_succeeded",
                "control_uri": (
                    f"s3://{args['destination_bucket']}/{control_key}"
                ),
                "tables_written": len(summaries),
            }
        )
    )

    job.commit()


if __name__ == "__main__":
    main()
