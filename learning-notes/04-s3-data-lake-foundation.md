# S3 Data Lake Foundation

## Objective

Create secure Amazon S3 storage for the Bronze, Silver, Gold, Quarantine, control, script, and Athena output areas of the pipeline.

## Bucket Design

The project uses one S3 bucket:

`globalpartners-data-jenny`

The following prefixes organize the pipeline data:

- `bronze/` — raw source extracts
- `silver/` — validated and standardized tables
- `gold/` — business-facing analytical tables
- `quarantine/` — source records that fail defined quality rules
- `control/` — pipeline status and processing records
- `scripts/` — AWS Glue job scripts
- `athena-results/` — Athena query results

Using prefixes keeps the data layers separate without requiring a different bucket for every stage.

## Security and Recovery

All public access is blocked.

Default server-side encryption uses AWS KMS. S3 Bucket Key is enabled to reduce the number of requests made to KMS.

Versioning keeps earlier versions when an object is replaced or deleted, which provides a recovery option if pipeline data is accidentally changed.

## Resource Tags

The bucket includes tags for the project name, environment, and management method. These labels help identify, filter, track, and eventually remove project resources.

## Validation

AWS CLI commands confirmed:

- Public-access blocking
- KMS encryption
- S3 Bucket Key
- Versioning
- All required prefixes
