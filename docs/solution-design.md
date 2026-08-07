# Solution Design

**Project:** GlobalPartners Business Analysis  
**Status:** Draft for SME review  
**AWS Region:** `us-east-2`

## 1. Purpose

This document describes the proposed AWS solution for loading SQL Server source data, applying PySpark transformations, calculating business metrics, and serving the results to Athena and Streamlit.

The design uses:

- Amazon RDS for SQL Server
- AWS Glue Workflow
- PySpark jobs
- Bronze, Silver, and Gold S3 layers
- Individual Silver jobs
- Athena
- Streamlit on Amazon EC2

## 2. Requirements

The solution must:

- Use SQL Server as the pipeline source.
- Use AWS services for the data pipeline.
- Implement transformation and metric logic in PySpark.
- Update Customer Lifetime Value daily.
- Include scheduling.
- Encrypt data.
- Support failure recovery and reloads.
- Produce SQL-accessible analytical tables.
- Provide a Streamlit dashboard.
- Support GitHub-based CI/CD.
- Avoid Snowflake and dbt.

## 3. Design Summary

The supplied CSV files will be loaded into Amazon RDS for SQL Server during one-time source setup.

A daily AWS Glue Workflow will:

1. Extract the SQL Server tables to the S3 Bronze prefix.
2. Run individual Silver jobs for order items, options, and dates.
3. Route approved record-level exceptions to quarantine.
4. Run a Gold PySpark job to calculate the required metrics.
5. Run a Glue Crawler after successful processing.
6. Make the Silver and Gold tables queryable through Athena.

A Streamlit application running on Amazon EC2 will query the Gold tables through Athena.

## 4. AWS Components

| Component | Responsibility |
|---|---|
| Amazon RDS for SQL Server | Hosts the three source tables |
| DBeaver | Performs one-time source setup and SQL validation from the Mac |
| AWS Secrets Manager | Stores the SQL Server credentials |
| AWS Glue Workflow | Manages the schedule, jobs, dependencies, crawler, and reruns |
| AWS Glue PySpark jobs | Extract, validate, transform, and calculate metrics |
| Amazon S3 | Stores Bronze, Silver, Gold, quarantine, control, scripts, and Athena results |
| AWS Glue Crawler | Discovers completed Silver and Gold schemas and partitions |
| AWS Glue Data Catalog | Stores metadata used by Athena |
| Amazon Athena | Queries Silver and Gold Parquet data |
| Amazon EC2 | Hosts the Streamlit application |
| Amazon CloudWatch | Stores Glue logs and execution information |
| Amazon EventBridge | Detects failed Glue job events |
| Amazon SNS | Sends pipeline failure notifications |
| AWS KMS | Encrypts supported data and logs |
| AWS IAM | Controls service permissions |
| GitHub Actions | Validates and deploys approved project code |

## 5. Source Setup

The project currently has three CSV files:

- `order_items.csv`
- `order_item_options.csv`
- `date_dim.csv`

DBeaver will be used to connect from the Mac to Amazon RDS for SQL Server.

The one-time setup process will:

1. Create the SQL Server tables.
2. Import the corresponding CSV records.
3. Validate the table schemas.
4. Confirm the SQL Server row counts.

Expected source counts:

| Source Table | Expected Rows |
|---|---:|
| `order_items` | 203,519 |
| `order_item_options` | 193,017 |
| `date_dim` | 365 |

After setup, the Glue pipeline will read from SQL Server rather than the local CSV files.

DBeaver is not part of the scheduled pipeline.

## 6. S3 Data Lake

The project will use one encrypted S3 bucket.

Proposed name:

```text
globalpartners-data-jenny
```

Proposed prefixes:

```text
bronze/
silver/
gold/
quarantine/
control/
scripts/
athena-results/
```

The final bucket name must be checked for global availability before creation.

### Bronze

Contains the daily SQL Server snapshots before business rules are applied.

### Silver

Contains accepted and standardized source-level tables.

### Gold

Contains business-ready metric tables.

### Quarantine

Contains records that fail approved Silver data-quality rules.

### Control

Contains stage-level run manifests with counts, status, paths, and error details.

### Scripts

Contains the deployed Glue PySpark scripts.

### Athena Results

Contains Athena query-result files.

## 7. AWS Glue Workflow

### Workflow Sequence

```text
Daily scheduled trigger
        ↓
SQL Server extract job
        ↓
Bronze source snapshots
        ↓
Silver order-items job ───────┐
        ↓                     │
Silver options job            │
                              ├──→ Gold metrics job
Silver date-dimension job ────┘
        ↓
Glue Crawler
        ↓
Glue Data Catalog
```

The Silver order-items and date-dimension jobs can begin after the extract job succeeds.

The Silver options job begins after the Silver order-items job succeeds because option records must be compared with accepted parent order items.

The Gold job begins only after all three Silver jobs succeed.

The crawler begins only after the Gold job succeeds.

## 8. PySpark Jobs

### `extract_sql_server_to_bronze.py`

Reads the three source tables through JDBC and writes the daily Bronze snapshots.

Responsibilities:

- Connect to SQL Server
- Extract each source table
- Add technical run metadata
- Write versioned Bronze data
- Record source and output counts
- Write the extraction-stage manifest

### `transform_order_items_silver.py`

Creates the accepted Silver order-items table.

Responsibilities:

- Parse `creation_time_utc`
- Parse item price and quantity
- Standardize boolean values
- Validate required columns
- Validate order and line-item identifiers
- Add an order date
- Write accepted records to Silver
- Write rejected records to quarantine
- Reconcile input and output counts
- Write the order-items stage manifest

### `transform_order_item_options_silver.py`

Creates the accepted Silver option table.

Responsibilities:

- Parse option price and quantity
- Validate required fields
- Match options to accepted parent order items
- Identify orphan option records
- Apply the approved repeated-row rule
- Write accepted records to Silver
- Write rejected records to quarantine
- Reconcile input and output counts
- Write the options stage manifest

### `build_date_dimension_silver.py`

Creates the Silver date dimension.

Responsibilities:

- Parse `date_key`
- Validate uniqueness
- Validate calendar fields
- Evaluate date-range coverage
- Apply the approved date-extension rule
- Preserve supplied holiday information
- Write accepted records to Silver
- Write rejected records to quarantine
- Write the date-dimension stage manifest

### `build_business_metrics_gold.py`

Creates the Gold analytical tables.

Responsibilities:

- Join the approved Silver tables
- Calculate item revenue
- Apply accepted option-price adjustments
- Calculate daily Customer Lifetime Value
- Assign customer value groups
- Calculate RFM measures
- Create churn indicators
- Create sales summaries
- Compare loyalty performance
- Calculate restaurant performance
- Analyze discounts
- Write the Gold stage manifest

## 9. Run Manifests

The jobs will write separate stage manifests rather than allowing parallel jobs to update the same file.

Example control paths:

```text
control/processing_date=YYYY-MM-DD/workflow_run_id=<run-id>/extract.json
control/processing_date=YYYY-MM-DD/workflow_run_id=<run-id>/silver_order_items.json
control/processing_date=YYYY-MM-DD/workflow_run_id=<run-id>/silver_order_item_options.json
control/processing_date=YYYY-MM-DD/workflow_run_id=<run-id>/silver_date_dim.json
control/processing_date=YYYY-MM-DD/workflow_run_id=<run-id>/gold_metrics.json
```

Each stage manifest can record:

- Processing date
- Workflow run ID
- Job name
- Job status
- Input paths
- Output paths
- Input row counts
- Accepted row counts
- Quarantine counts
- Repeated-row counts
- Start and completion times
- Error details

Separate files prevent parallel Silver jobs from overwriting one another’s status.

## 10. Proposed Silver Tables

### `silver_order_items`

Grain:

One accepted order item.

Candidate key:

`lineitem_id`

Known exception:

One source row has a missing `lineitem_id`.

### `silver_order_item_options`

Grain:

One accepted option occurrence associated with an order item.

The source does not provide a complete natural key.

A technical identifier can be finalized after the repeated-row rule is approved.

### `silver_date_dim`

Grain:

One calendar date.

Key:

`date_key`

The supplied source covers only 2023. The final coverage rule requires approval.

Holiday values outside the supplied 2023 data will not be invented.

## 11. Proposed Gold Tables

### `customer_daily_value`

Grain:

One customer per calendar date.

Purpose:

Show how cumulative customer value changes daily.

Proposed key:

```text
user_id + as_of_date
```

### `customer_rfm_snapshot`

Grain:

One customer per calculation date.

Proposed fields:

- Recency days
- Distinct order frequency
- Monetary value
- RFM scores
- Customer segment

### `customer_churn_indicator`

Grain:

One customer per calculation date.

Proposed fields:

- Days since last order
- Average gap between orders
- Recent-period spending
- Prior-period spending
- Spend percentage change
- Churn status

This is a threshold-based indicator, not a predictive model.

### `sales_daily`

Grain:

One date and approved reporting combination.

Possible breakdowns:

- Restaurant
- Item category
- Loyalty status

### `sales_monthly`

Grain:

One month and approved reporting combination.

### `loyalty_performance`

Purpose:

Compare loyalty and non-loyalty customer activity.

### `location_performance`

Purpose:

Rank restaurant locations using revenue, order count, and average order value.

### `discount_effectiveness`

Purpose:

Compare discounted and non-discounted orders using option-price adjustments.

## 12. Proposed Metric Logic

### Item Revenue

```text
item revenue = item_price × item_quantity
```

### Option Adjustment

```text
option adjustment = option_price × option_quantity
```

A negative option price represents a potential discount or price reduction.

### Net Revenue

```text
net revenue = item revenue + accepted option adjustments
```

The repeated-option rule must be approved before finalizing this calculation.

### Daily Customer Lifetime Value

```text
daily CLV =
cumulative accepted net revenue for one customer through as_of_date
```

Rows without an approved customer identifier cannot be assigned to customer-level CLV.

They may still qualify for overall sales reporting.

### Customer Value Groups

The requirements define:

- High value: top 20%
- Medium value: middle 60%
- Low value: bottom 20%

### RFM

**Recency**

Days between the calculation date and the customer’s most recent order.

**Frequency**

Distinct order count during the approved lookback period.

**Monetary**

Accepted net revenue during the approved lookback period.

The lookback period remains configurable until approved.

### Churn Indicators

Proposed measures:

- Days since last order
- Average days between orders
- Percentage change in spending

The requirements provide more than 45 inactive days as an example. The final threshold requires approval.

### Discount Analysis

An order can be classified as discounted when it contains an accepted option with:

```text
option_price < 0
```

The available source supports revenue and discount analysis.

True profitability cannot be calculated without product-cost data.

## 13. Data-Quality Handling

### Record-Level Exceptions

After approval, quarantine rules may include:

- Missing required key
- Invalid timestamp
- Invalid decimal, integer, or boolean
- Option without a parent order
- Option without a parent order item

### Metric Eligibility

A record can be valid for one metric but ineligible for another.

Example:

An order without `user_id` may remain valid for restaurant sales but cannot contribute to customer-level CLV or RFM.

Metric ineligibility does not automatically mean that the source record belongs in quarantine.

### Dataset-Level Failures

The workflow should stop when:

- A required SQL Server table cannot be read.
- Required columns are missing.
- A source table is unexpectedly empty.
- Input and output counts do not reconcile.
- A Silver or Gold output cannot be written.
- A required Gold calculation cannot complete.

## 14. Crawler and Athena

The Gold job reads Silver Parquet directly from S3.

After the Gold job succeeds, one Glue Crawler scans the completed Silver and Gold paths.

The crawler updates the Glue Data Catalog with:

- Table names
- Columns
- Data types
- S3 locations
- Partitions

Athena uses the Data Catalog to query the Parquet files.

Athena does not store a separate copy of the data.

The quarantine prefix will not be included in the primary analytics crawler.

## 15. Scheduling

The Glue Workflow will use a daily scheduled trigger.

The schedule time remains configurable.

The workflow can also be started manually for:

- Testing
- Backfills
- Reloads
- Controlled reprocessing

## 16. Failure and Reload Handling

### Automatic Retry

Each Glue job will have a limited retry count for temporary failures.

### Failed Workflow

When a job fails after its retries:

1. Dependent jobs do not start.
2. Glue records the failed job and workflow.
3. CloudWatch retains the error logs.
4. EventBridge matches the failed Glue job event.
5. SNS sends a notification.
6. Previously successful Gold data remains available.

### Repair and Resume

AWS Glue supports repairing and resuming a workflow from a failed node.

Separate Silver jobs allow the failed table process to be restarted without combining all Silver logic into one job.

### Manual Reload

A processing date can also be rerun manually.

The reload uses:

- The original processing date
- A new workflow run ID
- The same PySpark rules

Silver and Gold processing-date partitions are replaced after a successful rerun rather than appended. This prevents double-counting.

## 17. Encryption and Access

- RDS will use KMS encryption at rest.
- SQL Server credentials will be stored in Secrets Manager.
- Temporary DBeaver access will be restricted to the approved developer IP.
- Glue will connect to SQL Server through JDBC.
- The JDBC connection will require encrypted communication.
- S3 will block public access.
- S3 objects will use SSE-KMS.
- Glue output and logs will use a security configuration.
- IAM roles will use least-privilege permissions.
- EC2 will use an IAM role for Athena and S3 access.
- Streamlit will use HTTPS for its final deployment.

## 18. Streamlit

Streamlit will run directly on a small Amazon EC2 instance using Python.

The application will:

- Query Athena
- Read approved Gold results
- Display the required dashboards
- Use an EC2 role instead of stored AWS credentials

Docker, Amazon ECR, and Amazon ECS are not included.

EC2 is proposed because it keeps the dashboard in AWS without adding container services.

The EC2 instance can be stopped when it is not needed.

## 19. CI/CD

GitHub Actions will provide automated project checks and deployment steps.

Proposed checks include:

- Python syntax validation
- PySpark unit tests
- SQL validation
- Sensitive-file checks
- AWS CLI deployment-script validation

Approved deployment steps will include:

- Uploading Glue scripts to the S3 scripts prefix
- Updating Glue job definitions
- Deploying Streamlit code
- Running controlled configuration commands

AWS access from GitHub should use short-lived role access rather than stored AWS access keys.

CI/CD is separate from the runtime data flow and will be finalized after the core pipeline is approved.

## 20. Validation Plan

The completed build will validate:

1. RDS SQL Server connectivity
2. Source table schemas and row counts
3. SQL Server-to-Bronze extraction
4. Bronze-to-Silver reconciliation
5. Quarantine counts and reasons
6. Separate Silver job execution
7. Silver-to-Gold calculations
8. Date-dimension coverage
9. Customer daily-value calculations
10. RFM and churn calculations
11. Workflow scheduling
12. Failed-job notification
13. Workflow repair or reload
14. Glue Crawler results
15. Athena queries
16. Streamlit dashboard access
17. Encryption settings
18. CI/CD checks

## 21. Cost and Performance

The design is based on the current source volume and daily processing requirement.

Cost controls include:

- Small project-sized RDS configuration
- Glue jobs that run only when triggered
- One encrypted S3 bucket
- Parquet files for efficient Athena queries
- Limited CloudWatch retention
- EC2 stopped when not in use
- Cleanup instructions after validation

Streaming and CDC are not required for the initial build.

## 22. Decisions Requiring SME Confirmation

1. Is `user_id` the approved customer identifier?
2. Should rows without `user_id` remain in sales metrics but be excluded from customer metrics?
3. Is `restaurant_id` the approved location identifier?
4. How should the 2,299 exact repeated option rows be handled?
5. Should the 28 orphan option rows be quarantined?
6. How should the missing `lineitem_id` be handled?
7. Should the date dimension be extended for the full order history?
8. How should profitability be addressed without product-cost data?
9. What lookback period should be used for RFM?
10. What inactivity threshold should define churn risk?
11. Is a daily full snapshot acceptable?
12. Is Amazon EC2 acceptable for hosting Streamlit?

## 23. Out of Scope

The initial build does not include:

- Real-time streaming
- AWS DMS change data capture
- Predictive churn modeling
- Machine learning
- Snowflake
- dbt
- Docker
- Amazon ECS
- True profit calculations without product-cost data
- Invented holiday values outside the supplied source