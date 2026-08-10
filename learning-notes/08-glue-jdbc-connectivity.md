git # AWS Glue JDBC Connectivity

## Objective

Establish a secure connection between AWS Glue and the SQL Server source database.

## Implementation

- Created an IAM role for AWS Glue.
- Granted the role access to the project S3 bucket and RDS-managed database secret.
- Connected Glue to the same VPC, subnet, and security group as RDS.
- Used an S3 gateway endpoint for private S3 access.
- Added a Secrets Manager interface endpoint so Glue can retrieve database credentials without a NAT gateway.
- Configured the JDBC connection to require SSL.

## Validation

The AWS Glue connection test completed successfully using the `globalpartners-glue-role`. This confirmed that Glue could retrieve the database credentials and reach the SQL Server source through the configured VPC network.

## Troubleshooting

The initial test failed because the Availability Zone was not included in the CLI-created connection. The existing connection was updated with the subnet’s Availability Zone, and the next test succeeded.

## Result

The SQL Server source is ready for the AWS Glue ingestion job. No source data has been copied to S3 yet.