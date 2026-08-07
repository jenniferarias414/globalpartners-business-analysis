# GlobalPartners Business Analysis

AWS-based data engineering and analytics project using SQL Server source data, PySpark transformations, and Streamlit reporting.

## Project Objective

Build a production-style pipeline that creates a unified view of customer behavior and business performance across restaurant locations and ordering platforms.

The final solution will support daily Customer Lifetime Value, RFM segmentation, churn indicators, sales trends, loyalty comparisons, location performance, and pricing and discount analysis.

## Project Plan

| Phase | Work | Status |
|---|---|---|
| 00 | Repository setup and source-file organization | Complete |
| 01 | Source profiling, integrity checks, keys, and relationships | In progress |
| 02 | AWS architecture, data model, solution design, and review | Not started |
| 03 | AWS infrastructure and SQL Server ingestion | Not started |
| 04 | PySpark transformation pipeline, scheduling, encryption, and reload handling | Not started |
| 05 | Business metrics and analytical SQL queries | Not started |
| 06 | Streamlit dashboard | Not started |
| 07 | Testing, CI/CD, documentation, and walkthrough | Not started |

## Work Completed

- Created the repository structure and protected local source files with `.gitignore`.
- Created a reproducible Python environment.
- Built scripts for source profiling, candidate-key testing, relationship validation, and exception analysis.
- Verified the delivered schemas and documented row counts.
- Generated local reports for column quality, keys, relationships, and date coverage.
- Documented the profiling process and current findings.

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

## Current Focus

Complete Phase 01 by validating customer identifiers, loyalty relationships, numeric fields, and the business meaning of the remaining data-quality exceptions.