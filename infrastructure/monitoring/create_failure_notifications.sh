#!/usr/bin/env bash

set -euo pipefail

PROFILE="${GP_AWS_PROFILE:-retail-poc}"
REGION="${GP_AWS_REGION:-us-east-2}"
EXPECTED_ACCOUNT="${GP_EXPECTED_AWS_ACCOUNT:-272987324508}"
ALERT_EMAIL="${GP_ALERT_EMAIL:-}"

TOPIC_NAME="globalpartners-pipeline-alerts"
JOB_RULE_NAME="globalpartners-glue-job-failure"
CRAWLER_RULE_NAME="globalpartners-glue-crawler-failure"

JOB_PATTERN_FILE="infrastructure/monitoring/glue-job-failure-event-pattern.json"
CRAWLER_PATTERN_FILE="infrastructure/monitoring/glue-crawler-failure-event-pattern.json"
SAMPLE_JOB_EVENT_FILE="tests/events/sample-glue-job-failed-event.json"
SAMPLE_CRAWLER_EVENT_FILE="tests/events/sample-glue-crawler-failed-event.json"
GENERATED_DIRECTORY="reports/generated/monitoring"

if [[ -z "$ALERT_EMAIL" ]]; then
    echo "ERROR: Set GP_ALERT_EMAIL to the email address that should receive pipeline alerts." >&2
    exit 1
fi

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

mkdir -p "$GENERATED_DIRECTORY"

topic_arn="$(aws sns create-topic \
    --name "$TOPIC_NAME" \
    --tags \
        Key=Project,Value=globalpartners-business-analysis \
        Key=Environment,Value=portfolio \
        Key=ManagedBy,Value=aws-cli \
    --profile "$PROFILE" \
    --region "$REGION" \
    --query TopicArn \
    --output text \
    --no-cli-pager)"

echo "Created or found SNS topic: ${topic_arn}"

job_rule_arn="$(aws events put-rule \
    --name "$JOB_RULE_NAME" \
    --description "Alert when a GlobalPartners Glue job fails, times out, or stops" \
    --event-pattern "file://${JOB_PATTERN_FILE}" \
    --state ENABLED \
    --tags \
        Key=Project,Value=globalpartners-business-analysis \
        Key=Environment,Value=portfolio \
        Key=ManagedBy,Value=aws-cli \
    --profile "$PROFILE" \
    --region "$REGION" \
    --query RuleArn \
    --output text \
    --no-cli-pager)"

crawler_rule_arn="$(aws events put-rule \
    --name "$CRAWLER_RULE_NAME" \
    --description "Alert when the GlobalPartners Gold crawler fails" \
    --event-pattern "file://${CRAWLER_PATTERN_FILE}" \
    --state ENABLED \
    --tags \
        Key=Project,Value=globalpartners-business-analysis \
        Key=Environment,Value=portfolio \
        Key=ManagedBy,Value=aws-cli \
    --profile "$PROFILE" \
    --region "$REGION" \
    --query RuleArn \
    --output text \
    --no-cli-pager)"

echo "Created or updated EventBridge rule: ${job_rule_arn}"
echo "Created or updated EventBridge rule: ${crawler_rule_arn}"

topic_policy_file="${GENERATED_DIRECTORY}/sns-topic-policy.json"
job_target_file="${GENERATED_DIRECTORY}/job-failure-target.json"
crawler_target_file="${GENERATED_DIRECTORY}/crawler-failure-target.json"

python - \
    "$topic_arn" \
    "$actual_account" \
    "$job_rule_arn" \
    "$crawler_rule_arn" \
    "$topic_policy_file" \
    "$job_target_file" \
    "$crawler_target_file" <<'PY'
import json
import sys
from pathlib import Path


(
    topic_arn,
    account_id,
    job_rule_arn,
    crawler_rule_arn,
    policy_path,
    job_target_path,
    crawler_target_path,
) = sys.argv[1:]

policy = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "AllowAccountOwnerManagement",
            "Effect": "Allow",
            "Principal": {"AWS": "*"},
            "Action": [
                "SNS:GetTopicAttributes",
                "SNS:SetTopicAttributes",
                "SNS:AddPermission",
                "SNS:RemovePermission",
                "SNS:DeleteTopic",
                "SNS:Subscribe",
                "SNS:ListSubscriptionsByTopic",
                "SNS:Publish",
            ],
            "Resource": topic_arn,
            "Condition": {"StringEquals": {"AWS:SourceOwner": account_id}},
        },
        {
            "Sid": "AllowEventBridgeJobRulePublish",
            "Effect": "Allow",
            "Principal": {"Service": "events.amazonaws.com"},
            "Action": "sns:Publish",
            "Resource": topic_arn,
            "Condition": {"ArnEquals": {"aws:SourceArn": job_rule_arn}},
        },
        {
            "Sid": "AllowEventBridgeCrawlerRulePublish",
            "Effect": "Allow",
            "Principal": {"Service": "events.amazonaws.com"},
            "Action": "sns:Publish",
            "Resource": topic_arn,
            "Condition": {"ArnEquals": {"aws:SourceArn": crawler_rule_arn}},
        },
    ],
}

job_message = {
    "alert": "GlobalPartners Glue job failure",
    "project": "globalpartners-business-analysis",
    "job": "<job>",
    "state": "<state>",
    "job_run_id": "<run_id>",
    "message": "<message>",
    "time": "<time>",
    "region": "<region>",
    "aws_account": "<account>",
}

crawler_message = {
    "alert": "GlobalPartners Glue crawler failure",
    "project": "globalpartners-business-analysis",
    "crawler": "<crawler>",
    "state": "<state>",
    "time": "<time>",
    "region": "<region>",
    "aws_account": "<account>",
}

job_target = [
    {
        "Id": "globalpartners-job-failure-sns",
        "Arn": topic_arn,
        "InputTransformer": {
            "InputPathsMap": {
                "account": "$.account",
                "job": "$.detail.jobName",
                "message": "$.detail.message",
                "region": "$.region",
                "run_id": "$.detail.jobRunId",
                "state": "$.detail.state",
                "time": "$.time",
            },
            "InputTemplate": json.dumps(job_message, indent=2),
        },
    }
]

crawler_target = [
    {
        "Id": "globalpartners-crawler-failure-sns",
        "Arn": topic_arn,
        "InputTransformer": {
            "InputPathsMap": {
                "account": "$.account",
                "crawler": "$.detail.crawlerName",
                "region": "$.region",
                "state": "$.detail.state",
                "time": "$.time",
            },
            "InputTemplate": json.dumps(crawler_message, indent=2),
        },
    }
]

Path(policy_path).write_text(json.dumps(policy, indent=2) + "\n")
Path(job_target_path).write_text(json.dumps(job_target, indent=2) + "\n")
Path(crawler_target_path).write_text(
    json.dumps(crawler_target, indent=2) + "\n"
)
PY

aws sns set-topic-attributes \
    --topic-arn "$topic_arn" \
    --attribute-name Policy \
    --attribute-value "file://${topic_policy_file}" \
    --profile "$PROFILE" \
    --region "$REGION" \
    --no-cli-pager

aws events put-targets \
    --rule "$JOB_RULE_NAME" \
    --targets "file://${job_target_file}" \
    --profile "$PROFILE" \
    --region "$REGION" \
    --no-cli-pager \
    > /dev/null

aws events put-targets \
    --rule "$CRAWLER_RULE_NAME" \
    --targets "file://${crawler_target_file}" \
    --profile "$PROFILE" \
    --region "$REGION" \
    --no-cli-pager \
    > /dev/null

existing_subscription="$(aws sns list-subscriptions-by-topic \
    --topic-arn "$topic_arn" \
    --profile "$PROFILE" \
    --region "$REGION" \
    --query "Subscriptions[?Endpoint=='${ALERT_EMAIL}'].SubscriptionArn | [0]" \
    --output text \
    --no-cli-pager)"

if [[ -z "$existing_subscription" || "$existing_subscription" == "None" ]]; then
    aws sns subscribe \
        --topic-arn "$topic_arn" \
        --protocol email \
        --notification-endpoint "$ALERT_EMAIL" \
        --profile "$PROFILE" \
        --region "$REGION" \
        --no-cli-pager \
        > /dev/null
    echo "Sent SNS subscription confirmation to: ${ALERT_EMAIL}"
else
    echo "SNS subscription already exists for: ${ALERT_EMAIL}"
fi

echo
echo "Event-pattern tests"
aws events test-event-pattern \
    --event-pattern "file://${JOB_PATTERN_FILE}" \
    --event "file://${SAMPLE_JOB_EVENT_FILE}" \
    --profile "$PROFILE" \
    --region "$REGION" \
    --no-cli-pager

aws events test-event-pattern \
    --event-pattern "file://${CRAWLER_PATTERN_FILE}" \
    --event "file://${SAMPLE_CRAWLER_EVENT_FILE}" \
    --profile "$PROFILE" \
    --region "$REGION" \
    --no-cli-pager

echo
echo "EventBridge rules"
aws events describe-rule \
    --name "$JOB_RULE_NAME" \
    --profile "$PROFILE" \
    --region "$REGION" \
    --query '{Name:Name,State:State,Arn:Arn}' \
    --output table \
    --no-cli-pager

aws events describe-rule \
    --name "$CRAWLER_RULE_NAME" \
    --profile "$PROFILE" \
    --region "$REGION" \
    --query '{Name:Name,State:State,Arn:Arn}' \
    --output table \
    --no-cli-pager

echo
echo "SNS subscription"
aws sns list-subscriptions-by-topic \
    --topic-arn "$topic_arn" \
    --profile "$PROFILE" \
    --region "$REGION" \
    --query 'Subscriptions[].{Protocol:Protocol,Endpoint:Endpoint,Status:SubscriptionArn}' \
    --output table \
    --no-cli-pager

echo
echo "Failure-notification resources are configured."
echo "Confirm the AWS Notification subscription email before sending a test alert."
echo "SNS topic ARN: ${topic_arn}"
