# AWS Network Foundation

## Objective

Create the network controls that allow AWS Glue to communicate with Amazon RDS for SQL Server and Amazon S3.

## Security Group

The project uses a dedicated security group:

`globalpartners-glue-rds-sg`

The security group has a self-referencing inbound rule for TCP ports `0–65535`. The source is the security group itself, so the rule only allows communication between resources using the same security group.

AWS Glue requires this rule so its Spark components can communicate while the job is running.

A separate SQL Server rule will later allow DBeaver to connect through port `1433` from an approved IP address.

## S3 Gateway Endpoint

The S3 gateway endpoint gives resources in the VPC a private route to Amazon S3.

This allows the VPC-based Glue job to read and write S3 data without requiring a NAT gateway for S3 traffic.

The endpoint is associated with the VPC route table and is currently available.

## Validation

The AWS Console confirmed:

- The project security group exists in the correct VPC.
- The security-group rule is self-referencing.
- The S3 gateway endpoint is available.
- The endpoint type is Gateway.
- The endpoint uses the correct VPC and route table.

## References

- [AWS Glue JDBC networking](https://docs.aws.amazon.com/glue/latest/dg/connection-JDBC-VPC.html)
- [Amazon S3 VPC endpoints for AWS Glue](https://docs.aws.amazon.com/glue/latest/dg/vpc-endpoints-s3.html)