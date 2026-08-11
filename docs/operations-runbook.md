# GlobalPartners Pipeline Operations Runbook

## Purpose

This runbook describes how to monitor, investigate, recover, and reload the
GlobalPartners AWS Glue pipeline.

## Pipeline Order

1. `globalpartners-bronze-ingest`
2. `globalpartners-silver-date-dim`
3. `globalpartners-silver-order-items`
4. `globalpartners-silver-order-item-options`
5. `globalpartners-gold-business-metrics`
6. `globalpartners-gold-crawler`

Workflow: `globalpartners-daily-pipeline`

Configured schedule: daily at 11:00 UTC. The scheduled trigger remains inactive
while the portfolio source is unchanged.

## Failure Alerts

EventBridge monitors the five jobs for `FAILED`, `TIMEOUT`, and `STOPPED`, and
the crawler for `Failed`. Matching events are published to the
`globalpartners-pipeline-alerts` SNS topic.

An alert identifies the failed resource, state, run ID when available, time,
region, account, and Glue message.

## Initial Response

1. Confirm the alert belongs to account `272987324508` and region `us-east-2`.
2. Record the job or crawler name and run ID.
3. Open AWS Glue and locate the workflow run.
4. Inspect action statistics and every node state. Do not rely only on the
   workflow's `COMPLETED` label.
5. Open the failed job run and review its error message and CloudWatch logs.
6. Identify and correct the root cause before retrying.

## CLI Investigation

Inspect a job run:

```bash
aws glue get-job-run \
  --job-name JOB_NAME \
  --run-id JOB_RUN_ID \
  --profile retail-poc \
  --region us-east-2 \
  --no-cli-pager
```

List recent workflow runs:

```bash
aws glue get-workflow-runs \
  --name globalpartners-daily-pipeline \
  --max-results 10 \
  --profile retail-poc \
  --region us-east-2 \
  --no-cli-pager
```

Inspect a workflow graph:

```bash
aws glue get-workflow-run \
  --name globalpartners-daily-pipeline \
  --run-id WORKFLOW_RUN_ID \
  --include-graph \
  --profile retail-poc \
  --region us-east-2 \
  --no-cli-pager
```

## Recovery Options

### Resume an Attempted Node

Use this when an attempted job failed and its upstream data is still valid:

1. Open AWS Glue Workflows.
2. Select `globalpartners-daily-pipeline`.
3. Open **History** and select the affected run.
4. Choose **View run details**.
5. Select the failed attempted job node.
6. Choose **Resume run**.
7. Monitor the new workflow run and its downstream nodes.

Glue records the resumed execution as a new workflow run linked to the previous
run.

### Reload the Processing Date

Use a full date reload when outputs may be incomplete or when transformation
logic changed:

1. Confirm the intended `load_date`.
2. Correct the cause of the failure.
3. Run the controlled workflow runner for the current processing date.
4. Allow the jobs to remove and replace their own date-specific objects.
5. Do not manually delete an entire Bronze, Silver, quarantine, or Gold layer.
6. Run the workflow validator using the completed workflow run ID.

Current-date controlled run:

```bash
./scripts/run_glue_workflow.sh
```

Validate the completed run:

```bash
./scripts/validate_glue_workflow_run.sh WORKFLOW_RUN_ID
```

## Required Post-Run Checks

Confirm all of the following:

- Five job states are `SUCCEEDED`.
- Crawler state is `SUCCEEDED`.
- Failed, timed-out, stopped, and errored action counts are zero.
- Bronze row counts match the SQL Server source.
- Silver input equals accepted plus quarantined rows.
- Gold line count matches accepted Silver order-item count.
- Gold joined option count matches accepted Silver option count.
- Item plus option revenue equals line revenue.
- Line revenue equals order and daily-sales revenue.
- Customer revenue equals identified-order revenue.
- Latest control files have `status=SUCCEEDED`.

## Expected Validated Counts

| Dataset | Expected rows |
|---|---:|
| Bronze date dimension | 365 |
| Bronze order items | 203,519 |
| Bronze order-item options | 193,017 |
| Silver date dimension | 365 |
| Silver order items accepted | 203,518 |
| Silver order items quarantined | 1 |
| Silver order-item options accepted | 192,989 |
| Silver order-item options quarantined | 28 |
| Gold fact order line | 203,518 |
| Gold fact order | 131,328 |
| Gold customer daily CLV | 100,084 |
| Gold customer profile | 20,174 |
| Gold daily sales | 67,807 |

These values apply to the supplied project snapshot. A changed SQL Server source
requires comparison with the new source counts.

## Schedule Control

Activate the configured daily schedule:

```bash
aws glue start-trigger \
  --name globalpartners-start-daily \
  --profile retail-poc \
  --region us-east-2 \
  --no-cli-pager
```

Deactivate it for cost control:

```bash
aws glue stop-trigger \
  --name globalpartners-start-daily \
  --profile retail-poc \
  --region us-east-2 \
  --no-cli-pager
```

Stopping the schedule prevents future scheduled starts. It does not stop a
workflow run that is already in progress.
