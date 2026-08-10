"""Build business-ready Gold tables from accepted Silver records."""

import json
import sys
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import boto3
from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from pyspark.sql import DataFrame
from pyspark.sql.functions import (
    array_contains,
    avg,
    coalesce,
    col,
    count,
    countDistinct,
    date_add,
    date_format,
    date_sub,
    datediff,
    dayofweek,
    first as spark_first,
    floor,
    lag,
    least,
    lit,
    max as spark_max,
    min as spark_min,
    month,
    ntile,
    percent_rank,
    round as spark_round,
    sum as spark_sum,
    to_date,
    weekofyear,
    when,
    year,
)
from pyspark.sql.window import Window


OUTPUT_TABLES = [
    "fact_order_line",
    "fact_order",
    "customer_daily_clv",
    "customer_profile",
    "daily_sales",
]

ORDER_ITEM_COLUMNS = {
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
    "_order_date",
    "_date_dimension_match",
    "_quality_flag_codes",
}

OPTION_COLUMNS = {
    "order_id",
    "lineitem_id",
    "option_price",
    "option_quantity",
    "_quality_flag_codes",
}

DATE_COLUMNS = {
    "date_key",
    "is_holiday",
    "holiday_name",
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


def positive_integer_argument(name: str, default: int) -> int:
    """Read an optional positive integer Glue argument."""
    value = int(get_optional_argument(name, str(default)))
    if value <= 0:
        raise ValueError(f"--{name} must be greater than zero")
    return value


def validate_columns(
    dataframe: DataFrame,
    expected_columns: set[str],
    dataset_name: str,
) -> None:
    """Stop when a required Silver column is unavailable."""
    missing_columns = sorted(expected_columns.difference(dataframe.columns))
    if missing_columns:
        raise RuntimeError(
            f"{dataset_name} is missing columns: {', '.join(missing_columns)}"
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


def decimal_text(value: Decimal | None) -> str:
    """Serialize a Spark decimal result without losing precision."""
    return str(value if value is not None else Decimal("0"))


def main() -> None:
    """Build and reconcile the complete Gold analytical model."""
    args = getResolvedOptions(sys.argv, ["JOB_NAME", "data_bucket"])

    default_load_date = datetime.now(timezone.utc).date().isoformat()
    load_date = validate_load_date(
        get_optional_argument("load_date", default_load_date)
    )
    run_id = get_optional_argument("run_id", str(uuid.uuid4()))
    rfm_lookback_days = positive_integer_argument("rfm_lookback_days", 365)
    spend_period_days = positive_integer_argument("spend_period_days", 90)
    churn_threshold_days = positive_integer_argument(
        "churn_threshold_days", 45
    )
    processed_at_utc = datetime.now(timezone.utc).isoformat()

    spark_context = SparkContext.getOrCreate()
    glue_context = GlueContext(spark_context)
    spark = glue_context.spark_session
    job = Job(glue_context)
    job.init(args["JOB_NAME"], args)

    bucket = args["data_bucket"]
    silver_paths = {
        "date_dim": f"s3://{bucket}/silver/date_dim/load_date={load_date}/",
        "order_items": (
            f"s3://{bucket}/silver/order_items/load_date={load_date}/"
        ),
        "order_item_options": (
            f"s3://{bucket}/silver/order_item_options/load_date={load_date}/"
        ),
    }
    output_prefixes = {
        table_name: f"gold/{table_name}/load_date={load_date}/"
        for table_name in OUTPUT_TABLES
    }
    output_paths = {
        table_name: f"s3://{bucket}/{prefix}"
        for table_name, prefix in output_prefixes.items()
    }

    print(
        json.dumps(
            {
                "event": "gold_business_metrics_started",
                "run_id": run_id,
                "load_date": load_date,
                "silver_paths": silver_paths,
                "parameters": {
                    "rfm_lookback_days": rfm_lookback_days,
                    "spend_period_days": spend_period_days,
                    "churn_threshold_days": churn_threshold_days,
                },
            }
        )
    )

    order_items = spark.read.parquet(silver_paths["order_items"]).cache()
    options = spark.read.parquet(silver_paths["order_item_options"]).cache()
    date_dim = spark.read.parquet(silver_paths["date_dim"]).cache()

    validate_columns(order_items, ORDER_ITEM_COLUMNS, "Silver order_items")
    validate_columns(options, OPTION_COLUMNS, "Silver order_item_options")
    validate_columns(date_dim, DATE_COLUMNS, "Silver date_dim")

    silver_order_item_count = order_items.count()
    silver_option_count = options.count()
    silver_date_count = date_dim.count()

    if min(
        silver_order_item_count,
        silver_option_count,
        silver_date_count,
    ) <= 0:
        raise RuntimeError("One or more accepted Silver inputs returned zero rows")

    # Confirm that one order can safely become one Gold order row.
    order_header_checks = (
        order_items.groupBy("order_id")
        .agg(
            countDistinct("app_name").alias("app_name_values"),
            countDistinct("restaurant_id").alias("restaurant_values"),
            countDistinct("creation_time_utc").alias("timestamp_values"),
            countDistinct("user_id").alias("user_values"),
            countDistinct("is_loyalty").alias("loyalty_values"),
            countDistinct("currency").alias("currency_values"),
            spark_sum(
                when(col("user_id").isNull(), lit(1)).otherwise(lit(0))
            ).alias("missing_user_rows"),
            spark_sum(
                when(col("user_id").isNotNull(), lit(1)).otherwise(lit(0))
            ).alias("populated_user_rows"),
        )
        .withColumn(
            "mixed_missing_and_populated_user",
            (col("missing_user_rows") > 0)
            & (col("populated_user_rows") > 0),
        )
        .cache()
    )

    inconsistent_orders = order_header_checks.filter(
        (col("app_name_values") > 1)
        | (col("restaurant_values") > 1)
        | (col("timestamp_values") > 1)
        | (col("user_values") > 1)
        | (col("loyalty_values") > 1)
        | (col("currency_values") > 1)
        | col("mixed_missing_and_populated_user")
    ).count()

    if inconsistent_orders > 0:
        raise RuntimeError(
            f"Gold order grain validation failed for {inconsistent_orders} orders"
        )

    option_summary = (
        options.groupBy("order_id", "lineitem_id")
        .agg(
            spark_sum(col("option_price")).cast("decimal(20,2)").alias(
                "option_revenue"
            ),
            spark_sum(col("option_quantity")).cast("long").alias(
                "option_quantity"
            ),
            count(lit(1)).cast("long").alias("option_row_count"),
            spark_sum(
                when(
                    array_contains(
                        col("_quality_flag_codes"),
                        "REPEATED_SOURCE_OCCURRENCE",
                    ),
                    lit(1),
                ).otherwise(lit(0))
            )
            .cast("long")
            .alias("repeated_option_occurrence_count"),
        )
        .cache()
    )

    summarized_option_rows = option_summary.agg(
        spark_sum("option_row_count").alias("rows")
    ).first()["rows"]
    if summarized_option_rows != silver_option_count:
        raise RuntimeError(
            "Option aggregation reconciliation failed: "
            f"silver={silver_option_count}, summarized={summarized_option_rows}"
        )

    holiday_lookup = (
        date_dim.select(
            to_date(col("date_key")).alias("_holiday_date"),
            col("is_holiday").alias("_is_holiday"),
            col("holiday_name").alias("_holiday_name"),
        )
        .dropDuplicates(["_holiday_date"])
    )

    item_alias = order_items.alias("item")
    option_alias = option_summary.alias("option")
    joined_lines = item_alias.join(
        option_alias,
        (col("item.order_id") == col("option.order_id"))
        & (col("item.lineitem_id") == col("option.lineitem_id")),
        "left",
    )

    fact_order_line_base = (
        joined_lines.select(
            col("item.app_name").alias("app_name"),
            col("item.restaurant_id").alias("restaurant_id"),
            col("item.creation_time_utc").alias("creation_time_utc"),
            col("item._order_date").alias("order_date"),
            col("item.order_id").alias("order_id"),
            col("item.user_id").alias("user_id"),
            col("item.printed_card_number").alias("printed_card_number"),
            col("item.is_loyalty").alias("is_loyalty"),
            col("item.currency").alias("currency"),
            col("item.lineitem_id").alias("lineitem_id"),
            col("item.item_category").alias("item_category"),
            col("item.item_name").alias("item_name"),
            col("item.item_price").cast("decimal(20,2)").alias(
                "item_revenue"
            ),
            col("item.item_quantity").cast("long").alias("item_quantity"),
            coalesce(
                col("option.option_revenue"), lit(0).cast("decimal(20,2)")
            ).alias("option_revenue"),
            coalesce(
                col("option.option_quantity"), lit(0).cast("long")
            ).alias("option_quantity"),
            coalesce(
                col("option.option_row_count"), lit(0).cast("long")
            ).alias("option_row_count"),
            coalesce(
                col("option.repeated_option_occurrence_count"),
                lit(0).cast("long"),
            ).alias("repeated_option_occurrence_count"),
            col("item._date_dimension_match").alias(
                "date_dimension_match"
            ),
            col("item._quality_flag_codes").alias(
                "silver_quality_flag_codes"
            ),
        )
        .withColumn(
            "line_revenue",
            (col("item_revenue") + col("option_revenue")).cast(
                "decimal(20,2)"
            ),
        )
        .withColumn(
            "has_repeated_options",
            col("repeated_option_occurrence_count") > 0,
        )
        .withColumn("order_year", year(col("order_date")))
        .withColumn("order_month", month(col("order_date")))
        .withColumn("order_week", weekofyear(col("order_date")))
        .withColumn("order_day_of_week", date_format(col("order_date"), "EEEE"))
        .withColumn(
            "order_is_weekend", dayofweek(col("order_date")).isin(1, 7)
        )
    )

    fact_order_line = (
        fact_order_line_base.join(
            holiday_lookup,
            fact_order_line_base["order_date"]
            == holiday_lookup["_holiday_date"],
            "left",
        )
        .withColumn(
            "is_holiday",
            coalesce(col("_is_holiday"), lit(False)),
        )
        .withColumn("holiday_name", col("_holiday_name"))
        .withColumn("_gold_run_id", lit(run_id))
        .withColumn("_gold_processed_at_utc", lit(processed_at_utc))
        .drop("_holiday_date", "_is_holiday", "_holiday_name")
        .cache()
    )

    fact_order_line_count = fact_order_line.count()
    if fact_order_line_count != silver_order_item_count:
        raise RuntimeError(
            "Gold line-count reconciliation failed: "
            f"silver={silver_order_item_count}, gold={fact_order_line_count}"
        )

    line_revenue_totals = fact_order_line.agg(
        spark_sum("item_revenue").alias("item_revenue"),
        spark_sum("option_revenue").alias("option_revenue"),
        spark_sum("line_revenue").alias("line_revenue"),
        spark_sum("option_row_count").alias("option_rows"),
    ).first()

    item_revenue_total = line_revenue_totals["item_revenue"]
    option_revenue_total = line_revenue_totals["option_revenue"]
    line_revenue_total = line_revenue_totals["line_revenue"]
    joined_option_rows = line_revenue_totals["option_rows"]

    if joined_option_rows != silver_option_count:
        raise RuntimeError(
            "Gold option-to-line reconciliation failed: "
            f"silver={silver_option_count}, joined={joined_option_rows}"
        )
    if line_revenue_total != item_revenue_total + option_revenue_total:
        raise RuntimeError("Gold line revenue does not equal item plus option revenue")

    fact_order = (
        fact_order_line.groupBy("order_id")
        .agg(
            spark_first("app_name", ignorenulls=True).alias("app_name"),
            spark_first("restaurant_id", ignorenulls=True).alias(
                "restaurant_id"
            ),
            spark_first("creation_time_utc", ignorenulls=True).alias(
                "creation_time_utc"
            ),
            spark_first("order_date", ignorenulls=True).alias("order_date"),
            spark_first("user_id", ignorenulls=True).alias("user_id"),
            spark_first("is_loyalty", ignorenulls=True).alias("is_loyalty"),
            spark_first("currency", ignorenulls=True).alias("currency"),
            spark_first("order_year", ignorenulls=True).alias("order_year"),
            spark_first("order_month", ignorenulls=True).alias("order_month"),
            spark_first("order_week", ignorenulls=True).alias("order_week"),
            spark_first("order_day_of_week", ignorenulls=True).alias(
                "order_day_of_week"
            ),
            spark_first("order_is_weekend", ignorenulls=True).alias(
                "order_is_weekend"
            ),
            spark_first("date_dimension_match", ignorenulls=True).alias(
                "date_dimension_match"
            ),
            spark_first("is_holiday", ignorenulls=True).alias("is_holiday"),
            spark_first("holiday_name", ignorenulls=True).alias(
                "holiday_name"
            ),
            spark_sum("item_revenue").cast("decimal(20,2)").alias(
                "item_revenue"
            ),
            spark_sum("option_revenue").cast("decimal(20,2)").alias(
                "option_revenue"
            ),
            spark_sum("line_revenue").cast("decimal(20,2)").alias(
                "order_revenue"
            ),
            count(lit(1)).cast("long").alias("line_count"),
            spark_sum("item_quantity").cast("long").alias("item_quantity"),
            spark_sum("option_quantity").cast("long").alias(
                "option_quantity"
            ),
            spark_sum("option_row_count").cast("long").alias(
                "option_row_count"
            ),
            spark_sum("repeated_option_occurrence_count")
            .cast("long")
            .alias("repeated_option_occurrence_count"),
            spark_max(col("has_repeated_options").cast("integer")).alias(
                "has_repeated_options_integer"
            ),
        )
        .withColumn(
            "has_repeated_options",
            col("has_repeated_options_integer") == 1,
        )
        .withColumn("has_identified_customer", col("user_id").isNotNull())
        .withColumn("_gold_run_id", lit(run_id))
        .withColumn("_gold_processed_at_utc", lit(processed_at_utc))
        .drop("has_repeated_options_integer")
        .cache()
    )

    fact_order_count = fact_order.count()
    fact_order_revenue_total = fact_order.agg(
        spark_sum("order_revenue").alias("revenue")
    ).first()["revenue"]

    if fact_order_revenue_total != line_revenue_total:
        raise RuntimeError("Gold order revenue does not reconcile to line revenue")

    analysis_date = fact_order.agg(
        spark_max("order_date").alias("analysis_date")
    ).first()["analysis_date"]
    if analysis_date is None:
        raise RuntimeError("Gold fact_order has no valid analysis date")

    identified_orders = fact_order.filter(col("user_id").isNotNull()).cache()
    identified_order_count = identified_orders.count()

    daily_customer_activity = (
        identified_orders.groupBy("user_id", "order_date")
        .agg(
            countDistinct("order_id").cast("long").alias("daily_order_count"),
            spark_sum("item_revenue").cast("decimal(20,2)").alias(
                "daily_item_revenue"
            ),
            spark_sum("option_revenue").cast("decimal(20,2)").alias(
                "daily_option_revenue"
            ),
            spark_sum("order_revenue").cast("decimal(20,2)").alias(
                "daily_revenue"
            ),
        )
    )
    customer_day_window = (
        Window.partitionBy("user_id")
        .orderBy("order_date")
        .rowsBetween(Window.unboundedPreceding, Window.currentRow)
    )
    customer_daily_clv = (
        daily_customer_activity.withColumn(
            "cumulative_order_count",
            spark_sum("daily_order_count").over(customer_day_window),
        )
        .withColumn(
            "customer_lifetime_value",
            spark_sum("daily_revenue").over(customer_day_window).cast(
                "decimal(20,2)"
            ),
        )
        .withColumn("analysis_date", lit(analysis_date))
        .withColumn("_gold_run_id", lit(run_id))
        .withColumn("_gold_processed_at_utc", lit(processed_at_utc))
        .cache()
    )
    customer_daily_clv_count = customer_daily_clv.count()

    order_gap_window = Window.partitionBy("user_id").orderBy(
        "creation_time_utc", "order_id"
    )
    order_gaps = (
        identified_orders.select(
            "user_id", "order_id", "creation_time_utc"
        )
        .withColumn(
            "previous_order_timestamp",
            lag("creation_time_utc").over(order_gap_window),
        )
        .withColumn(
            "gap_days",
            datediff(
                to_date(col("creation_time_utc")),
                to_date(col("previous_order_timestamp")),
            ),
        )
    )
    average_order_gaps = order_gaps.groupBy("user_id").agg(
        spark_round(avg("gap_days"), 2).alias("average_gap_days")
    )

    rfm_start_date = date_sub(lit(analysis_date), rfm_lookback_days - 1)
    recent_start_date = date_sub(lit(analysis_date), spend_period_days - 1)
    prior_end_date = date_sub(lit(analysis_date), spend_period_days)
    prior_start_date = date_sub(
        lit(analysis_date), (2 * spend_period_days) - 1
    )

    customer_aggregates = (
        identified_orders.groupBy("user_id")
        .agg(
            spark_min("creation_time_utc").alias("first_order_timestamp"),
            spark_max("creation_time_utc").alias("last_order_timestamp"),
            countDistinct("order_id").cast("long").alias(
                "lifetime_order_count"
            ),
            spark_sum("order_revenue").cast("decimal(20,2)").alias(
                "lifetime_revenue"
            ),
            spark_round(avg("order_revenue"), 2).cast("decimal(20,2)").alias(
                "average_order_value"
            ),
            countDistinct(
                when(col("order_date") >= rfm_start_date, col("order_id"))
            )
            .cast("long")
            .alias("rfm_frequency"),
            spark_sum(
                when(
                    col("order_date") >= rfm_start_date,
                    col("order_revenue"),
                ).otherwise(lit(0).cast("decimal(20,2)"))
            )
            .cast("decimal(20,2)")
            .alias("rfm_monetary"),
            spark_sum(
                when(
                    col("order_date") >= recent_start_date,
                    col("order_revenue"),
                ).otherwise(lit(0).cast("decimal(20,2)"))
            )
            .cast("decimal(20,2)")
            .alias("recent_period_revenue"),
            spark_sum(
                when(
                    (col("order_date") >= prior_start_date)
                    & (col("order_date") <= prior_end_date),
                    col("order_revenue"),
                ).otherwise(lit(0).cast("decimal(20,2)"))
            )
            .cast("decimal(20,2)")
            .alias("prior_period_revenue"),
            spark_max(col("is_loyalty").cast("integer")).alias(
                "has_loyalty_activity_integer"
            ),
        )
        .join(average_order_gaps, on="user_id", how="left")
        .withColumn("analysis_date", lit(analysis_date))
        .withColumn(
            "days_since_last_order",
            datediff(lit(analysis_date), to_date(col("last_order_timestamp"))),
        )
        .withColumn(
            "spend_change_percent",
            when(
                col("prior_period_revenue") > 0,
                spark_round(
                    (
                        (col("recent_period_revenue") - col("prior_period_revenue"))
                        / col("prior_period_revenue")
                    )
                    * 100,
                    2,
                ),
            ).otherwise(lit(None).cast("decimal(20,2)")),
        )
        .withColumn(
            "spend_change_status",
            when(
                col("prior_period_revenue") > 0,
                lit("COMPARABLE"),
            ).otherwise(lit("NO_PRIOR_PERIOD_SPEND")),
        )
        .withColumn(
            "loyalty_activity_group",
            when(
                col("has_loyalty_activity_integer") == 1,
                lit("HAS_LOYALTY_ACTIVITY"),
            ).otherwise(lit("NO_LOYALTY_ACTIVITY")),
        )
        .drop("has_loyalty_activity_integer")
    )

    recency_score_window = Window.orderBy(
        col("days_since_last_order").desc(), col("user_id")
    )
    frequency_score_window = Window.orderBy(
        col("rfm_frequency").asc(), col("user_id")
    )
    monetary_score_window = Window.orderBy(
        col("rfm_monetary").asc(), col("user_id")
    )
    clv_tier_window = Window.orderBy(
        col("lifetime_revenue").asc(), col("user_id")
    )

    customer_profile = (
        customer_aggregates.withColumn(
            "_recency_percent_rank", percent_rank().over(recency_score_window)
        )
        .withColumn(
            "_frequency_percent_rank",
            percent_rank().over(frequency_score_window),
        )
        .withColumn(
            "_monetary_percent_rank",
            percent_rank().over(monetary_score_window),
        )
        .withColumn(
            "rfm_recency_score",
            least(
                lit(5), floor(col("_recency_percent_rank") * 5) + 1
            ).cast("integer"),
        )
        .withColumn(
            "rfm_frequency_score",
            least(
                lit(5), floor(col("_frequency_percent_rank") * 5) + 1
            ).cast("integer"),
        )
        .withColumn(
            "rfm_monetary_score",
            least(
                lit(5), floor(col("_monetary_percent_rank") * 5) + 1
            ).cast("integer"),
        )
        .withColumn("clv_quintile", ntile(5).over(clv_tier_window))
        .withColumn(
            "clv_tier",
            when(col("clv_quintile") == 5, lit("HIGH"))
            .when(col("clv_quintile") == 1, lit("LOW"))
            .otherwise(lit("MEDIUM")),
        )
        .withColumn(
            "churn_status",
            when(
                col("days_since_last_order") > churn_threshold_days,
                lit("AT_RISK"),
            ).otherwise(lit("ACTIVE")),
        )
        .withColumn(
            "customer_segment",
            when(
                (col("rfm_recency_score") >= 4)
                & (col("rfm_frequency_score") >= 4)
                & (col("rfm_monetary_score") >= 4),
                lit("VIP"),
            )
            .when(
                (col("lifetime_order_count") == 1)
                & (col("days_since_last_order") <= churn_threshold_days),
                lit("NEW_CUSTOMER"),
            )
            .when(
                col("days_since_last_order") > churn_threshold_days,
                lit("CHURN_RISK"),
            )
            .otherwise(lit("OTHER_ACTIVE")),
        )
        .withColumn("rfm_lookback_days", lit(rfm_lookback_days))
        .withColumn("spend_period_days", lit(spend_period_days))
        .withColumn("churn_threshold_days", lit(churn_threshold_days))
        .withColumn("_gold_run_id", lit(run_id))
        .withColumn("_gold_processed_at_utc", lit(processed_at_utc))
        .drop(
            "_recency_percent_rank",
            "_frequency_percent_rank",
            "_monetary_percent_rank",
        )
        .cache()
    )
    customer_profile_count = customer_profile.count()

    daily_sales = (
        fact_order_line.groupBy(
            "order_date",
            "order_year",
            "order_month",
            "order_week",
            "order_day_of_week",
            "order_is_weekend",
            "date_dimension_match",
            "is_holiday",
            "holiday_name",
            "restaurant_id",
            "app_name",
            "item_category",
            "is_loyalty",
            "currency",
        )
        .agg(
            spark_sum("item_revenue").cast("decimal(20,2)").alias(
                "item_revenue"
            ),
            spark_sum("option_revenue").cast("decimal(20,2)").alias(
                "option_revenue"
            ),
            spark_sum("line_revenue").cast("decimal(20,2)").alias(
                "total_revenue"
            ),
            countDistinct("order_id").cast("long").alias("order_count"),
            count(lit(1)).cast("long").alias("line_count"),
            spark_sum("item_quantity").cast("long").alias("units_sold"),
            countDistinct("user_id").cast("long").alias(
                "identified_customer_count"
            ),
            spark_sum("option_row_count").cast("long").alias(
                "option_row_count"
            ),
            spark_sum("repeated_option_occurrence_count")
            .cast("long")
            .alias("repeated_option_occurrence_count"),
        )
        .withColumn("_gold_run_id", lit(run_id))
        .withColumn("_gold_processed_at_utc", lit(processed_at_utc))
        .cache()
    )
    daily_sales_count = daily_sales.count()

    customer_lifetime_revenue_total = customer_profile.agg(
        spark_sum("lifetime_revenue").alias("revenue")
    ).first()["revenue"]
    identified_order_revenue_total = identified_orders.agg(
        spark_sum("order_revenue").alias("revenue")
    ).first()["revenue"]
    if customer_lifetime_revenue_total != identified_order_revenue_total:
        raise RuntimeError(
            "Customer lifetime revenue does not reconcile to identified orders"
        )

    daily_sales_revenue_total = daily_sales.agg(
        spark_sum("total_revenue").alias("revenue")
    ).first()["revenue"]
    if daily_sales_revenue_total != line_revenue_total:
        raise RuntimeError("Daily sales revenue does not reconcile to line revenue")

    output_dataframes = {
        "fact_order_line": fact_order_line,
        "fact_order": fact_order,
        "customer_daily_clv": customer_daily_clv,
        "customer_profile": customer_profile,
        "daily_sales": daily_sales,
    }
    output_counts = {
        "fact_order_line": fact_order_line_count,
        "fact_order": fact_order_count,
        "customer_daily_clv": customer_daily_clv_count,
        "customer_profile": customer_profile_count,
        "daily_sales": daily_sales_count,
    }

    s3_client = boto3.client("s3")
    deleted_objects = {
        table_name: delete_s3_prefix(
            s3_client, bucket, output_prefixes[table_name]
        )
        for table_name in OUTPUT_TABLES
    }

    for table_name in OUTPUT_TABLES:
        write_parquet(output_dataframes[table_name], output_paths[table_name])

    control_key = (
        f"control/gold/load_date={load_date}/run_id={run_id}/"
        "gold_business_metrics_summary.json"
    )
    control_document = {
        "status": "SUCCEEDED",
        "job_name": args["JOB_NAME"],
        "run_id": run_id,
        "load_date": load_date,
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "analysis_date": str(analysis_date),
        "parameters": {
            "rfm_lookback_days": rfm_lookback_days,
            "spend_period_days": spend_period_days,
            "churn_threshold_days": churn_threshold_days,
        },
        "silver_input_counts": {
            "date_dim": silver_date_count,
            "order_items": silver_order_item_count,
            "order_item_options": silver_option_count,
        },
        "order_header_inconsistency_count": inconsistent_orders,
        "identified_order_count": identified_order_count,
        "output_counts": output_counts,
        "revenue_totals": {
            "item_revenue": decimal_text(item_revenue_total),
            "option_revenue": decimal_text(option_revenue_total),
            "line_revenue": decimal_text(line_revenue_total),
            "order_revenue": decimal_text(fact_order_revenue_total),
            "identified_order_revenue": decimal_text(
                identified_order_revenue_total
            ),
            "customer_lifetime_revenue": decimal_text(
                customer_lifetime_revenue_total
            ),
            "daily_sales_revenue": decimal_text(
                daily_sales_revenue_total
            ),
        },
        "reconciliation": {
            "silver_items_equal_gold_lines": (
                silver_order_item_count == fact_order_line_count
            ),
            "silver_options_equal_joined_options": (
                silver_option_count == joined_option_rows
            ),
            "line_revenue_equals_item_plus_option": (
                line_revenue_total
                == item_revenue_total + option_revenue_total
            ),
            "order_revenue_equals_line_revenue": (
                fact_order_revenue_total == line_revenue_total
            ),
            "customer_revenue_equals_identified_order_revenue": (
                customer_lifetime_revenue_total
                == identified_order_revenue_total
            ),
            "daily_sales_revenue_equals_line_revenue": (
                daily_sales_revenue_total == line_revenue_total
            ),
        },
        "output_paths": output_paths,
        "objects_deleted_before_write": deleted_objects,
    }

    s3_client.put_object(
        Bucket=bucket,
        Key=control_key,
        Body=json.dumps(control_document, indent=2).encode("utf-8"),
        ContentType="application/json",
    )

    print(json.dumps(control_document))

    daily_sales.unpersist()
    customer_profile.unpersist()
    customer_daily_clv.unpersist()
    identified_orders.unpersist()
    fact_order.unpersist()
    fact_order_line.unpersist()
    option_summary.unpersist()
    order_header_checks.unpersist()
    date_dim.unpersist()
    options.unpersist()
    order_items.unpersist()
    job.commit()


if __name__ == "__main__":
    main()
