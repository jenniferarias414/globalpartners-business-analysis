# Repository Structure

The repository separates analysis, deployed job code, infrastructure creation, operational commands, documentation, and validation evidence. Similar AWS-related folders are intentionally separated by responsibility.

| Path | Purpose |
|---|---|
| `.github/workflows/` | GitHub Actions automation for validation and delivery packaging. |
| `analysis/` | Local source profiling, exception analysis, reconciliation, and validation scripts. |
| `architecture/` | Architecture overview and final AWS architecture diagram. |
| `docs/` | Technical design, data rules, operations, data model, CI/CD, and repository documentation. |
| `glue/jobs/` | PySpark programs deployed as AWS Glue jobs for Bronze, Silver, and Gold processing. |
| `infrastructure/ec2/` | Scripts that create, validate, update, and destroy the temporary Streamlit EC2 deployment. |
| `infrastructure/glue/` | Script that provisions the Glue Workflow, job dependencies, crawler, and schedule. |
| `infrastructure/iam/` | IAM trust and access-policy documents used by the Glue execution role. |
| `infrastructure/monitoring/` | EventBridge and SNS failure-notification configuration and event patterns. |
| `learning-notes/` | Public, phase-based explanations of the implementation and lessons learned. |
| `reports/generated/` | Git-ignored outputs produced by local and AWS validation commands. |
| `screenshots/full-walkthrough/` | Numbered validation evidence covering source analysis through GitHub Actions. |
| `scripts/` | Commands used to run, validate, and test resources after the infrastructure exists. |
| `sql/business/` | Athena SQL for CLV, RFM, sales, loyalty, location, and availability analysis. |
| `sql/validation/` | Athena reconciliation checks for the Gold analytical layer. |
| `streamlit/` | Dashboard application, Athena client, and dashboard-specific dependencies. |
| `tests/events/` | Synthetic AWS event payloads used to validate failure notifications safely. |

## Glue-related paths

The Glue folders are separate because they contain different types of work:

| Path | What it answers |
|---|---|
| `glue/jobs/` | What transformation code does each Glue job execute? |
| `infrastructure/glue/` | How are the Glue jobs, crawler, triggers, workflow, and schedule created and connected? |
| `scripts/` | How is an existing workflow started, checked, or validated? |
| `infrastructure/iam/` | What AWS permissions allow Glue to access the required services and data? |
| `infrastructure/monitoring/` | How are Glue and crawler failures detected and reported? |

Keeping these responsibilities separate prevents deployment configuration from being mixed into transformation code. It also makes the individual PySpark jobs easier to test and update.

## Local and generated content

The following content is intentionally excluded from Git:

- `.venv/` and Python cache directories.
- `project-assets/`, which contains supplied source files and local load-ready copies.
- `notes/private/`, which contains detailed personal learning notes.
- Generated reports and Parquet data.
- Environment variables, AWS configuration, private keys, and Streamlit secrets.

`reports/generated/.gitkeep` remains in the repository because scripts write validation output to that directory, while the generated files themselves remain ignored.
