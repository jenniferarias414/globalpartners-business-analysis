# Silver Date Dimension Validation

## Objective

Validate the Bronze date dimension before making it available for downstream analysis.

## Processing

The AWS Glue PySpark job:

- read the Bronze `date_dim` partition from Amazon S3;
- applied the expected data types;
- checked required values, duplicate dates, and calendar-field consistency;
- separated accepted and quarantined records;
- replaced the matching Silver load-date partition during a reload;
- reconciled the input, accepted, and quarantined row counts; and
- wrote a JSON control report for the run.

## Validation Results

| Measure | Result |
|---|---:|
| Bronze input rows | 365 |
| Silver accepted rows | 365 |
| Quarantined rows | 0 |
| Reconciliation passed | Yes |

All supplied date records passed the Silver validation rules. The accepted records were written as Snappy-compressed Parquet files under the Silver `date_dim` load-date partition.

The supplied date dimension still covers only January 1 through December 31, 2023. This validation confirms the quality of the delivered records; it does not extend the dimension to cover the complete order history.
