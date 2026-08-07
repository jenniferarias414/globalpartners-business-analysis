# AWS Architecture and Solution Design

## Objective

Design an AWS-based pipeline that reads from SQL Server, performs PySpark transformations, supports scheduled and repeatable processing, and provides analytical data to a Streamlit dashboard.

## Approved Design

The source data will be loaded into Amazon RDS for SQL Server during project setup. DBeaver will be used from a Mac to create the source tables, import the supplied CSV records, and validate the import.

The daily pipeline will follow this flow:

1. An AWS Glue Workflow starts on a schedule.
2. A Glue PySpark extraction job reads the SQL Server tables and writes raw files to the S3 Bronze layer.
3. Separate Glue PySpark jobs validate and standardize the order-items, item-options, and date-dimension data.
4. Accepted records are written to Silver, while rejected source records can be written to Quarantine.
5. A Gold job creates business-facing analytical tables.
6. A Glue Crawler registers the completed Silver and Gold tables in the Glue Data Catalog.
7. Athena queries the cataloged S3 data.
8. Streamlit presents the results from an EC2-hosted application.

## Design Decisions

One S3 bucket will contain separate prefixes for Bronze, Silver, Gold, Quarantine, control files, Glue scripts, and Athena results.

Separate Silver jobs provide more control over table-specific validation and recovery. The item-options job depends on accepted order-items data because an option must have a matching parent order item.

The Glue Workflow manages the schedule and job dependencies. CloudWatch, EventBridge, and SNS support logging and failure notification.

Raw files remain available in Bronze so failed or corrected transformations can be processed again without creating duplicate results.

Database credentials will be stored in Secrets Manager. IAM, encryption at rest, and encryption in transit will be applied to the AWS resources.

## Approval

The SME confirmed that the Glue extraction job should ingest data from Amazon RDS for SQL Server into the S3 Bronze layer.

The architecture and solution design were approved on August 7, 2026.