# Glue Catalog and Athena Validation

## Objective

Register the five Gold Parquet datasets as queryable tables and confirm their counts and revenue totals with SQL.

## Catalog Setup

The `globalpartners-gold-crawler` scanned the Gold S3 layer and created five tables in the `globalpartners_gold` Glue Data Catalog database:

- `customer_daily_clv`
- `customer_profile`
- `daily_sales`
- `fact_order`
- `fact_order_line`

Each table uses Parquet format and includes `load_date` as a partition key.

## Athena Setup

The `globalpartners-analysis` workgroup provides an enforced encrypted S3 results location, CloudWatch metrics, and a 1 GiB per-query scan cutoff.

The first SQL validation query scanned approximately 2.5 MiB and completed successfully. It confirmed the five Gold row counts and the following revenue reconciliation:

| Measure | Amount |
|---|---:|
| Item revenue | $1,778,729.14 |
| Option revenue | $85,245.14 |
| Line revenue | $1,863,974.28 |
| Order revenue | $1,863,974.28 |
| Daily-sales revenue | $1,863,974.28 |
| Identified-customer revenue | $1,690,600.00 |
| Customer lifetime revenue | $1,690,600.00 |

The SQL results independently matched the Gold Glue job control report.
