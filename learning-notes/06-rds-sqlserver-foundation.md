# Amazon RDS for SQL Server Foundation

## Objective

Create the SQL Server source required by the pipeline and prepare it for access from DBeaver and AWS Glue.

## Database Configuration

The source uses Amazon RDS for SQL Server Express with the following configuration:

| Setting | Selection |
|---|---|
| SQL Server version | SQL Server 2022 |
| Instance class | `db.t3.micro` |
| Storage | 20 GiB `gp3` |
| Availability | Single-AZ |
| Encryption | Enabled |
| Automated backup retention | One day |
| Credentials | Managed by AWS Secrets Manager |

The configuration uses the smallest supported instance class and minimum general-purpose storage suitable for the project.

## Networking

A dedicated RDS subnet group contains subnets from three Availability Zones in the project VPC.

The database uses the same project security group planned for the Glue JDBC connection. The security group allows internal Glue communication and restricts external SQL Server access to port `1433` from an approved IP address.

The database is publicly reachable for the one-time DBeaver source setup, but the security-group rule limits which IP address can connect.

## Credential Protection

Amazon RDS generated the master password and stored it in AWS Secrets Manager. The password was not included in terminal commands, source code, documentation, or GitHub.

## Validation

AWS CLI and Console checks confirmed:

- Database status is `available`.
- SQL Server Express is running on `db.t3.micro`.
- Storage encryption is enabled.
- The database uses 20 GiB of `gp3` storage.
- Automated backup retention is one day.
- The managed secret is active.
- The expected VPC, subnet group, security group, and SQL Server port are configured.
