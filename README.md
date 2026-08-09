# GlobalPartners Business Analysis

AWS-based data engineering and analytics project using SQL Server source data, PySpark transformations, and Streamlit reporting.

## Project Objective

Build a production-style pipeline that creates a unified view of customer behavior and business performance across restaurant locations and ordering platforms.

The solution will support customer value analysis, RFM segmentation, churn indicators, sales trends, loyalty comparisons, location performance, and pricing or discount analysis where supported by the source data.

## Current Status

Source profiling and relationship analysis are complete. The proposed AWS architecture and solution design were approved by the SME on August 7, 2026.

Phase 03 will begin with AWS account verification and cost-controlled infrastructure setup.

## Project Plan

| Phase | Work | Status |
|---|---|---|
| 00 | Repository setup and source-file organization | Complete |
| 01 | Source profiling, integrity checks, keys, and relationships | Complete |
| 02 | AWS architecture, data model, solution design, and review | Complete |
| 03 | AWS infrastructure and SQL Server source setup | In progress |
| 04 | PySpark transformation pipeline, scheduling, encryption, and reload handling | Not started |
| 05 | Business metrics and analytical SQL queries | Not started |
| 06 | Streamlit dashboard | Not started |
| 07 | Testing, CI/CD, documentation, and walkthrough | Not started |

## Work Completed

- Created the repository structure and protected local source files with `.gitignore`.
- Created a reproducible Python environment.
- Built scripts for source profiling, candidate-key testing, relationship validation, and exception analysis.
- Verified the supplied schemas and documented row counts.
- Generated reports for column quality, keys, relationships, and date coverage.
- Documented the profiling process and current findings.
- Drafted the AWS architecture and solution design.
- Submitted the proposed design for SME approval.
- Created the encrypted S3 data lake foundation with public-access blocking, versioning, project tags, and separate data-layer prefixes.
- Created the project security group and S3 gateway endpoint for private Glue, RDS, and S3 connectivity.
- Created the encrypted Amazon RDS for SQL Server source with restricted network access, automated backups, and RDS-managed credentials in Secrets Manager.
- Provisioned the encrypted S3, network, and RDS SQL Server foundations.
- Connected to RDS SQL Server from macOS using DBeaver.
- Created the `globalpartners` database and three typed source tables.
- Prepared SQL Server-compatible load files without modifying the original CSVs.
- Loaded and validated all 396,901 source records in SQL Server.

## Findings to Date

- `order_items.csv` contains 203,519 rows, matching the documented count.
- `order_item_options.csv` contains 193,017 rows, matching the documented count.
- `date_dim.csv` contains 365 dates covering only calendar year 2023.
- Order activity spans April 21, 2020 through February 21, 2024.
- Every 2023 order-item row matches the supplied date dimension.
- Populated `lineitem_id` values are unique, but one value is missing.
- The options source contains 2,299 exact repeated rows.
- No supplied option-column combination uniquely identifies every option row.
- Twenty-eight option rows reference 14 orders that are absent from `order_items`.
- `user_id` is missing from 8.75% of order-item rows.
- `printed_card_number` is missing from 77.36% of order-item rows.

## Proposed AWS Architecture

![Proposed AWS architecture](architecture/globalpartners-architecture-diagram.png)

The proposed design uses Amazon RDS for SQL Server as the pipeline source. A scheduled AWS Glue Workflow extracts the source data to an Amazon S3 Bronze layer and runs separate PySpark jobs for the Silver tables. A Gold job creates business-facing analytical tables.

AWS Glue Data Catalog and Athena provide the SQL query layer. The final Streamlit dashboard will be hosted temporarily on Amazon EC2 for validation, screenshots, and the project walkthrough.

The design also includes encryption, pipeline monitoring, failure notifications, and processing-date reload support.

## Open Decisions

The following items require confirmation before transformation rules are finalized:

- Whether `user_id` should be treated as the requested customer identifier.
- Whether `restaurant_id` should be treated as the requested location identifier.
- Whether the date dimension should be extended to cover the complete order history.
- How exact repeated option rows and orphan option records should be handled.
- How missing customer identifiers should affect customer-level metrics.
- How profitability and discount analysis should be handled without documented product-cost or explicit discount fields.
- What thresholds should be used for RFM and churn indicators.

## Documentation

- [Architecture overview](architecture/architecture-overview.md)
- [Solution design](docs/solution-design.md)
- [Source analysis](docs/source-analysis.md)

## Current Focus

Configure AWS Glue access to RDS SQL Server and build the first extraction job from SQL Server into the S3 Bronze layer.