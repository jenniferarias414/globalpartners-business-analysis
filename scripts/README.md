# Operational Scripts

These `.sh` files are reusable terminal commands for running and validating resources that already exist in AWS. Run them from the repository root.

| Script | What it does |
|---|---|
| `run_athena_business_queries.sh` | Runs every numbered SQL file in `sql/business`, waits for Athena to finish, downloads each CSV result, and writes a query-run summary under `reports/generated/athena-business`. |
| `run_glue_workflow.sh` | Temporarily replaces the inactive daily trigger with an on-demand validation trigger, runs the full six-action Glue Workflow, waits for completion, checks for six successes and zero failures, and restores the inactive daily schedule. |
| `validate_glue_workflow_run.sh` | Does not start jobs. It checks a successful workflow run, displays job and crawler states, downloads the Bronze, Silver, and Gold control files for the load date, and validates their statuses, row counts, quarantine counts, reload deletions, and Gold reconciliations. |
| `test_failure_notification_delivery.sh` | Temporarily allows a synthetic EventBridge source, publishes one fake Glue failure event, sends it through the real SNS email path, and restores the final Glue-only event pattern. It does not run or fail a Glue job and does not change project data. |

## Variables

The variables at the top use working project defaults, including `retail-poc`, `us-east-2`, the expected AWS account, and the project resource names. A value can be overridden by exporting its `GP_...` environment variable before running a script.

`validate_glue_workflow_run.sh` automatically selects the newest run with six successful actions. A specific run ID can be supplied as its first argument. Its load date defaults to today's UTC date, so set `GP_LOAD_DATE=YYYY-MM-DD` when validating an older run.

## Rerun guidance

- `test_failure_notification_delivery.sh` is the safest quick demo. It sends another synthetic SNS email if the topic, confirmed subscription, EventBridge rule, and target still exist.
- `validate_glue_workflow_run.sh` is read-only against AWS, apart from downloading report copies locally.
- `run_athena_business_queries.sh` reruns the business queries and creates small Athena query charges.
- `run_glue_workflow.sh` reruns all five Glue jobs and the crawler, creates Glue charges, and replaces the current load-date outputs by design. It is not recommended for a short live demo.

Example synthetic notification test:

```bash
export GP_AWS_PROFILE=retail-poc
export GP_AWS_REGION=us-east-2

./scripts/test_failure_notification_delivery.sh
```
