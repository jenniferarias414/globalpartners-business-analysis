# SQL Server Source Setup

## Objective

Establish the supplied source data in Amazon RDS for SQL Server so the AWS pipeline can extract it through a JDBC connection.

## Implementation

A SQL Server Express instance was created in Amazon RDS with encrypted storage and an AWS-managed password. DBeaver was used from a Mac to connect securely, create the project database, and load the source records.

The database contains three tables:

- `dbo.order_items`
- `dbo.order_item_options`
- `dbo.date_dim`

The table definitions use SQL Server data types that match the source content. A primary key was added only to `date_dim`, where `date_key` is complete and unique. Keys were not forced onto the two order tables because the profiling results did not support them.

## Source Preparation

The source files used text values and date formats that required conversion before loading into SQL Server.

The preparation script:

- Preserves the original CSV files.
- Creates separate SQL Server load-ready files.
- Converts `TRUE` and `FALSE` to `1` and `0`.
- Converts dates and timestamps to SQL Server-compatible formats.
- Preserves identifiers as text.
- Confirms the expected row count for each file.

## Load Validation

| SQL Server Table | Loaded Rows |
|---|---:|
| `date_dim` | 365 |
| `order_items` | 203,519 |
| `order_item_options` | 193,017 |

All loaded row counts match the delivered source files.

## Outcome

The SQL Server source is ready for the AWS Glue extraction job. The next step is to configure Glue access to RDS and extract the source tables into the S3 Bronze layer.