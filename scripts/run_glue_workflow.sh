#!/usr/bin/env bash

set -euo pipefail

PROFILE="${GP_AWS_PROFILE:-retail-poc}"
REGION="${GP_AWS_REGION:-us-east-2}"
EXPECTED_ACCOUNT="${GP_EXPECTED_AWS_ACCOUNT:-272987324508}"
WORKFLOW_NAME="${GP_WORKFLOW_NAME:-globalpartners-daily-pipeline}"
BRONZE_JOB="${GP_BRONZE_JOB:-globalpartners-bronze-ingest}"
SCHEDULED_TRIGGER="globalpartners-start-daily"
VALIDATION_TRIGGER="globalpartners-start-validation"
DAILY_SCHEDULE="${GP_WORKFLOW_SCHEDULE:-cron(0 11 * * ? *)}"
POLL_SECONDS="${GP_WORKFLOW_POLL_SECONDS:-15}"
TAGS="Project=globalpartners-business-analysis,Environment=portfolio,ManagedBy=aws-cli"

trigger_exists() {
    aws glue get-trigger \
        --name "$1" \
        --profile "$PROFILE" \
        --region "$REGION" \
        --no-cli-pager \
        > /dev/null 2>&1
}

delete_trigger_if_present() {
    local trigger_name="$1"

    if ! trigger_exists "$trigger_name"; then
        return
    fi

    local trigger_state
    trigger_state="$(aws glue get-trigger \
        --name "$trigger_name" \
        --profile "$PROFILE" \
        --region "$REGION" \
        --query 'Trigger.State' \
        --output text \
        --no-cli-pager)"

    if [[ "$trigger_state" == "ACTIVATED" ]]; then
        aws glue stop-trigger \
            --name "$trigger_name" \
            --profile "$PROFILE" \
            --region "$REGION" \
            --no-cli-pager \
            > /dev/null

        while true; do
            trigger_state="$(aws glue get-trigger \
                --name "$trigger_name" \
                --profile "$PROFILE" \
                --region "$REGION" \
                --query 'Trigger.State' \
                --output text \
                --no-cli-pager)"

            if [[ "$trigger_state" == "DEACTIVATED" ]]; then
                break
            fi
            sleep 2
        done
    fi

    if [[ "$trigger_state" != "DELETING" ]]; then
        aws glue delete-trigger \
            --name "$trigger_name" \
            --profile "$PROFILE" \
            --region "$REGION" \
            --no-cli-pager \
            > /dev/null
        echo "Requested trigger deletion: ${trigger_name}"
    fi

    while trigger_exists "$trigger_name"; do
        echo "Waiting for trigger deletion: ${trigger_name}"
        sleep 2
    done

    sleep 5
    echo "Confirmed trigger deleted: ${trigger_name}"
}

restore_daily_schedule() {
    delete_trigger_if_present "$VALIDATION_TRIGGER"

    if trigger_exists "$SCHEDULED_TRIGGER"; then
        echo "Daily scheduled trigger already restored: ${SCHEDULED_TRIGGER}"
        return
    fi

    aws glue create-trigger \
        --name "$SCHEDULED_TRIGGER" \
        --workflow-name "$WORKFLOW_NAME" \
        --type SCHEDULED \
        --schedule "$DAILY_SCHEDULE" \
        --actions "[{\"JobName\":\"${BRONZE_JOB}\"}]" \
        --description "Daily 11:00 UTC schedule; intentionally inactive during portfolio build" \
        --tags "$TAGS" \
        --profile "$PROFILE" \
        --region "$REGION" \
        --no-cli-pager \
        > /dev/null
    echo "Restored inactive daily trigger: ${SCHEDULED_TRIGGER}"
}

actual_account="$(aws sts get-caller-identity \
    --profile "$PROFILE" \
    --region "$REGION" \
    --query Account \
    --output text \
    --no-cli-pager)"

actual_arn="$(aws sts get-caller-identity \
    --profile "$PROFILE" \
    --region "$REGION" \
    --query Arn \
    --output text \
    --no-cli-pager)"

if [[ "$actual_account" != "$EXPECTED_ACCOUNT" ]]; then
    echo "ERROR: Expected AWS account ${EXPECTED_ACCOUNT}, but found ${actual_account}." >&2
    exit 1
fi

echo "Verified AWS profile: ${PROFILE}"
echo "Verified AWS account: ${actual_account}"
echo "Verified AWS identity: ${actual_arn}"

delete_trigger_if_present "$SCHEDULED_TRIGGER"
delete_trigger_if_present "$VALIDATION_TRIGGER"

aws glue create-trigger \
    --name "$VALIDATION_TRIGGER" \
    --workflow-name "$WORKFLOW_NAME" \
    --type ON_DEMAND \
    --actions "[{\"JobName\":\"${BRONZE_JOB}\"}]" \
    --description "Temporary on-demand root for end-to-end workflow validation" \
    --tags "$TAGS" \
    --profile "$PROFILE" \
    --region "$REGION" \
    --no-cli-pager \
    > /dev/null

echo "Created temporary validation trigger: ${VALIDATION_TRIGGER}"

trap restore_daily_schedule EXIT

sleep 3

echo "Starting workflow: ${WORKFLOW_NAME}"
workflow_run_id="$(aws glue start-workflow-run \
    --name "$WORKFLOW_NAME" \
    --profile "$PROFILE" \
    --region "$REGION" \
    --query RunId \
    --output text \
    --no-cli-pager)"

echo "Workflow run ID: ${workflow_run_id}"

while true; do
    status="$(aws glue get-workflow-run \
        --name "$WORKFLOW_NAME" \
        --run-id "$workflow_run_id" \
        --include-graph \
        --profile "$PROFILE" \
        --region "$REGION" \
        --query 'Run.Status' \
        --output text \
        --no-cli-pager)"

    statistics="$(aws glue get-workflow-run \
        --name "$WORKFLOW_NAME" \
        --run-id "$workflow_run_id" \
        --include-graph \
        --profile "$PROFILE" \
        --region "$REGION" \
        --query 'Run.Statistics' \
        --output json \
        --no-cli-pager)"

    echo "Workflow status: ${status} | Statistics: ${statistics}"

    if [[ "$status" != "RUNNING" ]]; then
        break
    fi

    sleep "$POLL_SECONDS"
done

echo
echo "Final workflow summary"
aws glue get-workflow-run \
    --name "$WORKFLOW_NAME" \
    --run-id "$workflow_run_id" \
    --include-graph \
    --profile "$PROFILE" \
    --region "$REGION" \
    --query 'Run.{Workflow:Name,RunId:WorkflowRunId,Status:Status,Started:StartedOn,Completed:CompletedOn,Statistics:Statistics,Error:ErrorMessage}' \
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

succeeded_actions="$(aws glue get-workflow-run \
    --name "$WORKFLOW_NAME" \
    --run-id "$workflow_run_id" \
    --profile "$PROFILE" \
    --region "$REGION" \
    --query 'Run.Statistics.SucceededActions' \
    --output text \
    --no-cli-pager)"

failed_actions="$(aws glue get-workflow-run \
    --name "$WORKFLOW_NAME" \
    --run-id "$workflow_run_id" \
    --profile "$PROFILE" \
    --region "$REGION" \
    --query 'Run.Statistics.FailedActions' \
    --output text \
    --no-cli-pager)"

if [[ "$status" != "COMPLETED" ]] \
    || [[ "$succeeded_actions" -ne 6 ]] \
    || [[ "$failed_actions" -ne 0 ]]; then
    echo "ERROR: Expected 6 successful actions and 0 failed actions." >&2
    exit 1
fi

restore_daily_schedule
trap - EXIT

echo
echo "Workflow validation succeeded."
echo "Validated workflow run ID: ${workflow_run_id}"
echo "The inactive daily schedule has been restored."
