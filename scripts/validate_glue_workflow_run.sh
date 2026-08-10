#!/usr/bin/env bash

set -euo pipefail

PROFILE="${GP_AWS_PROFILE:-retail-poc}"
REGION="${GP_AWS_REGION:-us-east-2}"
EXPECTED_ACCOUNT="${GP_EXPECTED_AWS_ACCOUNT:-272987324508}"
WORKFLOW_NAME="${GP_WORKFLOW_NAME:-globalpartners-daily-pipeline}"
SCHEDULED_TRIGGER="globalpartners-start-daily"
BUCKET="${GP_BUCKET_NAME:-globalpartners-data-jenny}"
LOAD_DATE="${GP_LOAD_DATE:-$(date -u +%F)}"
OUTPUT_DIRECTORY="${GP_WORKFLOW_VALIDATION_DIRECTORY:-reports/generated/workflow-validation}"

actual_account="$(aws sts get-caller-identity \
    --profile "$PROFILE" \
    --region "$REGION" \
    --query Account \
    --output text \
    --no-cli-pager)"

if [[ "$actual_account" != "$EXPECTED_ACCOUNT" ]]; then
    echo "ERROR: Expected AWS account ${EXPECTED_ACCOUNT}, but found ${actual_account}." >&2
    exit 1
fi

workflow_run_id="${1:-}"

if [[ -z "$workflow_run_id" ]]; then
    workflow_run_id="$(aws glue get-workflow-runs \
        --name "$WORKFLOW_NAME" \
        --profile "$PROFILE" \
        --region "$REGION" \
        --query 'Runs[?Statistics.SucceededActions==`6`] | [0].WorkflowRunId' \
        --output text \
        --no-cli-pager)"
fi

if [[ -z "$workflow_run_id" || "$workflow_run_id" == "None" ]]; then
    echo "ERROR: No workflow run with six successful actions was found." >&2
    exit 1
fi

echo "Verified AWS account: ${actual_account}"
echo "Workflow: ${WORKFLOW_NAME}"
echo "Workflow run ID: ${workflow_run_id}"
echo "Load date: ${LOAD_DATE}"

echo
echo "Final workflow summary"
aws glue get-workflow-run \
    --name "$WORKFLOW_NAME" \
    --run-id "$workflow_run_id" \
    --include-graph \
    --profile "$PROFILE" \
    --region "$REGION" \
    --query 'Run.{Status:Status,Started:StartedOn,Completed:CompletedOn,Statistics:Statistics,Error:ErrorMessage}' \
    --output json \
    --no-cli-pager

echo
echo "Job and crawler states"
aws glue get-workflow-run \
    --name "$WORKFLOW_NAME" \
    --run-id "$workflow_run_id" \
    --include-graph \
    --profile "$PROFILE" \
    --region "$REGION" \
    --query 'Run.Graph.Nodes[?Type==`JOB` || Type==`CRAWLER`].{Type:Type,Name:Name,JobState:JobDetails.JobRuns[0].JobRunState,CrawlerState:CrawlerDetails.Crawls[0].State}' \
    --output table \
    --no-cli-pager

echo
echo "Restored daily schedule"
aws glue get-trigger \
    --name "$SCHEDULED_TRIGGER" \
    --profile "$PROFILE" \
    --region "$REGION" \
    --query 'Trigger.{Name:Name,Type:Type,State:State,Schedule:Schedule,JobAction:Actions[0].JobName}' \
    --output table \
    --no-cli-pager

mkdir -p "$OUTPUT_DIRECTORY"

download_latest_control() {
    local label="$1"
    local prefix="$2"
    local destination="${OUTPUT_DIRECTORY}/${label}.json"
    local key

    key="$(aws s3api list-objects-v2 \
        --bucket "$BUCKET" \
        --prefix "$prefix" \
        --profile "$PROFILE" \
        --region "$REGION" \
        --query 'reverse(sort_by(Contents,&LastModified))[0].Key' \
        --output text \
        --no-cli-pager)"

    if [[ -z "$key" || "$key" == "None" ]]; then
        echo "ERROR: No control file found under s3://${BUCKET}/${prefix}" >&2
        exit 1
    fi

    aws s3 cp \
        "s3://${BUCKET}/${key}" \
        "$destination" \
        --profile "$PROFILE" \
        --region "$REGION" \
        --no-progress

    echo "Downloaded ${label}: s3://${BUCKET}/${key}"
}

download_latest_control \
    "bronze_summary" \
    "control/bronze/load_date=${LOAD_DATE}/"

download_latest_control \
    "silver_date_dim_summary" \
    "control/silver/date_dim/load_date=${LOAD_DATE}/"

download_latest_control \
    "silver_order_items_summary" \
    "control/silver/order_items/load_date=${LOAD_DATE}/"

download_latest_control \
    "silver_order_item_options_summary" \
    "control/silver/order_item_options/load_date=${LOAD_DATE}/"

download_latest_control \
    "gold_summary" \
    "control/gold/load_date=${LOAD_DATE}/"

python - "$OUTPUT_DIRECTORY" <<'PY'
import json
import sys
from pathlib import Path


directory = Path(sys.argv[1])
files = [
    "bronze_summary.json",
    "silver_date_dim_summary.json",
    "silver_order_items_summary.json",
    "silver_order_item_options_summary.json",
    "gold_summary.json",
]

print("\nLATEST CONTROL-FILE VALIDATION")

for file_name in files:
    path = directory / file_name
    with path.open(encoding="utf-8") as source:
        data = json.load(source)

    if data.get("status") != "SUCCEEDED":
        raise SystemExit(f"ERROR: {file_name} status was not SUCCEEDED")

    reconciliation = data.get("reconciliation_passed")
    if reconciliation is False:
        raise SystemExit(f"ERROR: {file_name} reconciliation failed")

    if file_name == "bronze_summary.json":
        rows = {
            table["source_table"]: table["row_count"]
            for table in data["tables"]
        }
        deleted = {
            table["source_table"]: table["objects_deleted_before_write"]
            for table in data["tables"]
        }
        details = {"rows": rows, "objects_deleted": deleted}
    elif file_name == "gold_summary.json":
        details = {
            "output_counts": data["output_counts"],
            "objects_deleted": data["objects_deleted_before_write"],
            "reconciliation": data["reconciliation"],
        }
    else:
        details = {
            "input_count": data["input_count"],
            "accepted_count": data["accepted_count"],
            "quarantined_count": data["quarantined_count"],
            "objects_deleted": data["objects_deleted_before_write"],
            "reconciliation_passed": data["reconciliation_passed"],
        }

    print(
        f"{file_name}: status=SUCCEEDED "
        f"run_id={data['run_id']} details={json.dumps(details, sort_keys=True)}"
    )

print("\nWorkflow and reload validation completed successfully.")
PY
