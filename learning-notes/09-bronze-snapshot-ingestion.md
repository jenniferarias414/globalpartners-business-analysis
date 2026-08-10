# Bronze Snapshot Ingestion

## Objective

Extract the SQL Server source tables into the Amazon S3 Bronze layer while preserving source-level detail and supporting controlled reloads.

## Source Strategy

The available sources do not provide a reliable change timestamp across all three tables. The Bronze job therefore creates a complete snapshot of each table for the processing date instead of claiming unsupported incremental behavior.

## Implementation

The AWS Glue PySpark job:

- Reads `dbo.date_dim`, `dbo.order_items`, and `dbo.order_item_options` through the tested JDBC connection.
- Adds source, processing-date, run, and ingestion-time audit fields.
- Checks that each source table returns records before replacing an existing partition.
- Writes Snappy-compressed Parquet files to table-specific Bronze paths.
- Creates a JSON control document containing the run status, output paths, and row counts.
- Replaces the existing S3 objects when the same processing date is rerun.

## Initial Load Results

| Source Table | Bronze Row Count |
|---|---:|
| `dbo.date_dim` | 365 |
| `dbo.order_items` | 203,519 |
| `dbo.order_item_options` | 193,017 |

All Bronze counts matched the validated SQL Server source counts.

## Reload Validation

The job was rerun using the same processing date. It removed 20 current S3 objects from each table partition, wrote replacement Parquet files, and produced the same row counts.

The reload did not create a second logical copy of the data. S3 versioning retains earlier object versions for recovery while the current partition contains the latest successful snapshot.

## Result

The source data is available in the S3 Bronze layer with reproducible audit information, validated row counts, and tested same-date reload handling.
