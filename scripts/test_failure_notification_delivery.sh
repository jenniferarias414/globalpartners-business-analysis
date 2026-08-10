#!/usr/bin/env bash

set -euo pipefail

PROFILE="${GP_AWS_PROFILE:-retail-poc}"
REGION="${GP_AWS_REGION:-us-east-2}"
EXPECTED_ACCOUNT="${GP_EXPECTED_AWS_ACCOUNT:-272987324508}"

TOPIC_NAME="globalpartners-pipeline-alerts"
JOB_RULE_NAME="globalpartners-glue-job-failure"
FINAL_PATTERN_FILE="infrastructure/monitoring/glue-job-failure-event-pattern.json"
GENERATED_DIRECTORY="reports/generated/monitoring"
TEMP_PATTERN_FILE="${GENERATED_DIRECTORY}/temporary-job-failure-test-pattern.json"
TEST_ENTRY_FILE="${GENERATED_DIRECTORY}/synthetic-failure-test-entry.json"

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

topic_arn="$(aws sns list-topics \
    --profile "$PROFILE" \
    --region "$REGION" \
    --query "Topics[?ends_with(TopicArn, ':${TOPIC_NAME}')].TopicArn | [0]" \
    --output text \
    --no-cli-pager)"

if [[ -z "$topic_arn" || "$topic_arn" == "None" ]]; then
    echo "ERROR: SNS topic ${TOPIC_NAME} was not found." >&2
    exit 1
fi

confirmed_subscription_count="$(aws sns list-subscriptions-by-topic \
    --topic-arn "$topic_arn" \
    --profile "$PROFILE" \
    --region "$REGION" \
    --query "length(Subscriptions[?Protocol=='email' && SubscriptionArn!='PendingConfirmation'])" \
    --output text \
    --no-cli-pager)"

if [[ "$confirmed_subscription_count" -lt 1 ]]; then
    echo "ERROR: No confirmed email subscription was found for ${TOPIC_NAME}." >&2
    exit 1
fi

rule_state="$(aws events describe-rule \
    --name "$JOB_RULE_NAME" \
    --profile "$PROFILE" \
    --region "$REGION" \
    --query State \
    --output text \
    --no-cli-pager)"

if [[ "$rule_state" != "ENABLED" ]]; then
    echo "ERROR: EventBridge rule ${JOB_RULE_NAME} is not enabled." >&2
    exit 1
fi

target_count="$(aws events list-targets-by-rule \
    --rule "$JOB_RULE_NAME" \
    --profile "$PROFILE" \
    --region "$REGION" \
    --query "length(Targets[?Arn=='${topic_arn}'])" \
    --output text \
    --no-cli-pager)"

if [[ "$target_count" -ne 1 ]]; then
    echo "ERROR: The job-failure rule does not have the expected SNS target." >&2
    exit 1
fi

mkdir -p "$GENERATED_DIRECTORY"

python - \
    "$FINAL_PATTERN_FILE" \
    "$TEMP_PATTERN_FILE" \
    "$TEST_ENTRY_FILE" <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


final_pattern_path, temporary_pattern_path, test_entry_path = sys.argv[1:]

with Path(final_pattern_path).open(encoding="utf-8") as source:
    temporary_pattern = json.load(source)

temporary_pattern["source"].append("globalpartners.validation")

detail = {
    "jobName": "globalpartners-silver-order-items",
    "severity": "ERROR",
    "state": "FAILED",
    "jobRunId": "jr_synthetic_notification_validation",
    "message": (
        "Synthetic notification test only. No Glue job failed and no project "
        "data was changed."
    ),
}

entry = [
    {
        "Source": "globalpartners.validation",
        "DetailType": "Glue Job State Change",
        "Detail": json.dumps(detail),
        "EventBusName": "default",
        "Time": datetime.now(timezone.utc).isoformat(),
    }
]

Path(temporary_pattern_path).write_text(
    json.dumps(temporary_pattern, indent=2) + "\n"
)
Path(test_entry_path).write_text(json.dumps(entry, indent=2) + "\n")
PY

restore_final_pattern() {
    aws events put-rule \
        --name "$JOB_RULE_NAME" \
        --description "Alert when a GlobalPartners Glue job fails, times out, or stops" \
        --event-pattern "file://${FINAL_PATTERN_FILE}" \
        --state ENABLED \
        --profile "$PROFILE" \
        --region "$REGION" \
        --no-cli-pager \
        > /dev/null
    echo "Restored final AWS Glue-only event pattern."
}

trap restore_final_pattern EXIT

aws events put-rule \
    --name "$JOB_RULE_NAME" \
    --description "Temporary synthetic delivery validation in progress" \
    --event-pattern "file://${TEMP_PATTERN_FILE}" \
    --state ENABLED \
    --profile "$PROFILE" \
    --region "$REGION" \
    --no-cli-pager \
    > /dev/null

echo "Temporarily enabled the synthetic validation source."

sleep 3

echo "Publishing one synthetic job-failure event..."
aws events put-events \
    --entries "file://${TEST_ENTRY_FILE}" \
    --profile "$PROFILE" \
    --region "$REGION" \
    --query '{FailedEntryCount:FailedEntryCount,EventIds:Entries[].EventId,Errors:Entries[?ErrorCode!=null].{Code:ErrorCode,Message:ErrorMessage}}' \
    --output json \
    --no-cli-pager

echo "Waiting for EventBridge and SNS delivery..."
sleep 20

restore_final_pattern
trap - EXIT

echo
echo "Final rule validation"
aws events describe-rule \
    --name "$JOB_RULE_NAME" \
    --profile "$PROFILE" \
    --region "$REGION" \
    --query '{Name:Name,State:State,EventPattern:EventPattern}' \
    --output json \
    --no-cli-pager

echo
echo "Synthetic delivery test completed."
echo "Check the confirmed email inbox for the GlobalPartners Glue job alert."
echo "No Glue job was run or failed during this test."
