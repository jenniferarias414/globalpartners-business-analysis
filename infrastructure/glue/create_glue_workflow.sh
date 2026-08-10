#!/usr/bin/env bash

set -euo pipefail

PROFILE="${GP_AWS_PROFILE:-retail-poc}"
REGION="${GP_AWS_REGION:-us-east-2}"
EXPECTED_ACCOUNT="${GP_EXPECTED_AWS_ACCOUNT:-272987324508}"

WORKFLOW_NAME="${GP_WORKFLOW_NAME:-globalpartners-daily-pipeline}"
BRONZE_JOB="${GP_BRONZE_JOB:-globalpartners-bronze-ingest}"
SILVER_DATE_JOB="${GP_SILVER_DATE_JOB:-globalpartners-silver-date-dim}"
SILVER_ITEMS_JOB="${GP_SILVER_ITEMS_JOB:-globalpartners-silver-order-items}"
SILVER_OPTIONS_JOB="${GP_SILVER_OPTIONS_JOB:-globalpartners-silver-order-item-options}"
GOLD_JOB="${GP_GOLD_JOB:-globalpartners-gold-business-metrics}"
GOLD_CRAWLER="${GP_GOLD_CRAWLER:-globalpartners-gold-crawler}"

OBSOLETE_ON_DEMAND_TRIGGER="globalpartners-start-on-demand"
SCHEDULED_TRIGGER="globalpartners-start-daily"
AFTER_BRONZE_TRIGGER="globalpartners-after-bronze"
AFTER_DATE_TRIGGER="globalpartners-after-silver-date"
AFTER_ITEMS_TRIGGER="globalpartners-after-silver-order-items"
AFTER_OPTIONS_TRIGGER="globalpartners-after-silver-options"
AFTER_GOLD_TRIGGER="globalpartners-after-gold"

SCHEDULE="${GP_WORKFLOW_SCHEDULE:-cron(0 11 * * ? *)}"
TAGS="Project=globalpartners-business-analysis,Environment=portfolio,ManagedBy=aws-cli"

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

for job_name in \
    "$BRONZE_JOB" \
    "$SILVER_DATE_JOB" \
    "$SILVER_ITEMS_JOB" \
    "$SILVER_OPTIONS_JOB" \
    "$GOLD_JOB"; do
    aws glue get-job \
        --job-name "$job_name" \
        --profile "$PROFILE" \
        --region "$REGION" \
        --query 'Job.Name' \
        --output text \
        --no-cli-pager \
        > /dev/null
    echo "Verified Glue job: ${job_name}"
done

aws glue get-crawler \
    --name "$GOLD_CRAWLER" \
    --profile "$PROFILE" \
    --region "$REGION" \
    --query 'Crawler.Name' \
    --output text \
    --no-cli-pager \
    > /dev/null
echo "Verified Glue crawler: ${GOLD_CRAWLER}"

if aws glue get-workflow \
    --name "$WORKFLOW_NAME" \
    --profile "$PROFILE" \
    --region "$REGION" \
    --no-cli-pager \
    > /dev/null 2>&1; then
    echo "Workflow already exists: ${WORKFLOW_NAME}"
else
    aws glue create-workflow \
        --name "$WORKFLOW_NAME" \
        --description "Scheduled GlobalPartners SQL Server Bronze, Silver, Gold, and catalog pipeline" \
        --tags "$TAGS" \
        --profile "$PROFILE" \
        --region "$REGION" \
        --no-cli-pager \
        > /dev/null
    echo "Created workflow: ${WORKFLOW_NAME}"
fi

trigger_exists() {
    aws glue get-trigger \
        --name "$1" \
        --profile "$PROFILE" \
        --region "$REGION" \
        --no-cli-pager \
        > /dev/null 2>&1
}

if trigger_exists "$OBSOLETE_ON_DEMAND_TRIGGER"; then
    aws glue delete-trigger \
        --name "$OBSOLETE_ON_DEMAND_TRIGGER" \
        --profile "$PROFILE" \
        --region "$REGION" \
        --no-cli-pager \
        > /dev/null
    echo "Removed obsolete trigger: ${OBSOLETE_ON_DEMAND_TRIGGER}"
fi

if trigger_exists "$SCHEDULED_TRIGGER"; then
    echo "Trigger already exists: ${SCHEDULED_TRIGGER}"
else
    aws glue create-trigger \
        --name "$SCHEDULED_TRIGGER" \
        --workflow-name "$WORKFLOW_NAME" \
        --type SCHEDULED \
        --schedule "$SCHEDULE" \
        --actions "[{\"JobName\":\"${BRONZE_JOB}\"}]" \
        --description "Daily 11:00 UTC schedule; intentionally inactive during portfolio build" \
        --tags "$TAGS" \
        --profile "$PROFILE" \
        --region "$REGION" \
        --no-cli-pager \
        > /dev/null
    echo "Created inactive scheduled trigger: ${SCHEDULED_TRIGGER}"
fi

create_success_trigger() {
    local trigger_name="$1"
    local upstream_job="$2"
    local downstream_job="$3"

    if trigger_exists "$trigger_name"; then
        echo "Trigger already exists: ${trigger_name}"
        return
    fi

    aws glue create-trigger \
        --name "$trigger_name" \
        --workflow-name "$WORKFLOW_NAME" \
        --type CONDITIONAL \
        --predicate "{\"Logical\":\"AND\",\"Conditions\":[{\"LogicalOperator\":\"EQUALS\",\"JobName\":\"${upstream_job}\",\"State\":\"SUCCEEDED\"}]}" \
        --actions "[{\"JobName\":\"${downstream_job}\"}]" \
        --description "Start ${downstream_job} after ${upstream_job} succeeds" \
        --start-on-creation \
        --tags "$TAGS" \
        --profile "$PROFILE" \
        --region "$REGION" \
        --no-cli-pager \
        > /dev/null
    echo "Created and activated trigger: ${trigger_name}"
}

create_success_trigger \
    "$AFTER_BRONZE_TRIGGER" \
    "$BRONZE_JOB" \
    "$SILVER_DATE_JOB"

create_success_trigger \
    "$AFTER_DATE_TRIGGER" \
    "$SILVER_DATE_JOB" \
    "$SILVER_ITEMS_JOB"

create_success_trigger \
    "$AFTER_ITEMS_TRIGGER" \
    "$SILVER_ITEMS_JOB" \
    "$SILVER_OPTIONS_JOB"

create_success_trigger \
    "$AFTER_OPTIONS_TRIGGER" \
    "$SILVER_OPTIONS_JOB" \
    "$GOLD_JOB"

if trigger_exists "$AFTER_GOLD_TRIGGER"; then
    echo "Trigger already exists: ${AFTER_GOLD_TRIGGER}"
else
    aws glue create-trigger \
        --name "$AFTER_GOLD_TRIGGER" \
        --workflow-name "$WORKFLOW_NAME" \
        --type CONDITIONAL \
        --predicate "{\"Logical\":\"AND\",\"Conditions\":[{\"LogicalOperator\":\"EQUALS\",\"JobName\":\"${GOLD_JOB}\",\"State\":\"SUCCEEDED\"}]}" \
        --actions "[{\"CrawlerName\":\"${GOLD_CRAWLER}\"}]" \
        --description "Start the Gold crawler after the Gold job succeeds" \
        --start-on-creation \
        --tags "$TAGS" \
        --profile "$PROFILE" \
        --region "$REGION" \
        --no-cli-pager \
        > /dev/null
    echo "Created and activated trigger: ${AFTER_GOLD_TRIGGER}"
fi

echo
echo "Workflow configuration"
aws glue get-workflow \
    --name "$WORKFLOW_NAME" \
    --include-graph \
    --profile "$PROFILE" \
    --region "$REGION" \
    --query 'Workflow.{Name:Name,Description:Description,NodeCount:length(Graph.Nodes),EdgeCount:length(Graph.Edges)}' \
    --output table \
    --no-cli-pager

echo
echo "Workflow triggers"
aws glue get-triggers \
    --profile "$PROFILE" \
    --region "$REGION" \
    --query "Triggers[?WorkflowName=='${WORKFLOW_NAME}'].{Name:Name,Type:Type,State:State,Schedule:Schedule,JobAction:Actions[0].JobName,CrawlerAction:Actions[0].CrawlerName}" \
    --output table \
    --no-cli-pager

echo
echo "Workflow created. The daily schedule is configured but inactive."
echo "Use aws glue start-workflow-run for the first end-to-end validation run."
