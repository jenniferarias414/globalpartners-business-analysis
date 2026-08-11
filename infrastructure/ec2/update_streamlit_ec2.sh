#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPOSITORY_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
STATE_FILE="$REPOSITORY_ROOT/reports/generated/streamlit-ec2/deployment.env"

if [[ ! -f "$STATE_FILE" ]]; then
    printf 'ERROR: Deployment state file not found: %s\n' "$STATE_FILE" >&2
    exit 1
fi

# shellcheck disable=SC1090
source "$STATE_FILE"

: "${AWS_PROFILE:?Missing AWS_PROFILE in state file}"
: "${AWS_REGION:?Missing AWS_REGION in state file}"
: "${EXPECTED_ACCOUNT:?Missing EXPECTED_ACCOUNT in state file}"
: "${INSTANCE_ID:?Missing INSTANCE_ID in state file}"
: "${APP_URL:?Missing APP_URL in state file}"

export AWS_PAGER=""

aws_cli() {
    aws "$@" \
        --profile "$AWS_PROFILE" \
        --region "$AWS_REGION" \
        --no-cli-pager
}

ACCOUNT_ID="$(aws_cli sts get-caller-identity --query 'Account' --output text)"
if [[ "$ACCOUNT_ID" != "$EXPECTED_ACCOUNT" ]]; then
    printf 'ERROR: Expected account %s but found %s.\n' \
        "$EXPECTED_ACCOUNT" "$ACCOUNT_ID" >&2
    exit 1
fi

DEPLOY_COMMIT="$(git -C "$REPOSITORY_ROOT" rev-parse HEAD)"
REMOTE_COMMIT="$(
    git -C "$REPOSITORY_ROOT" ls-remote origin \
        "refs/heads/$(git -C "$REPOSITORY_ROOT" branch --show-current)" \
        | awk '{print $1}'
)"

if [[ -z "$REMOTE_COMMIT" || "$REMOTE_COMMIT" != "$DEPLOY_COMMIT" ]]; then
    printf 'ERROR: Local HEAD %s is not the commit currently pushed for this branch.\n' \
        "$DEPLOY_COMMIT" >&2
    printf 'Commit and push the hotfix, then run this script again.\n' >&2
    exit 1
fi

printf 'Updating instance: %s\n' "$INSTANCE_ID"
printf 'Deploying commit: %s\n' "$DEPLOY_COMMIT"

SSM_STATUS="$(
    aws_cli ssm describe-instance-information \
        --filters "Key=InstanceIds,Values=$INSTANCE_ID" \
        --query 'InstanceInformationList[0].PingStatus' \
        --output text
)"
if [[ "$SSM_STATUS" != "Online" ]]; then
    printf 'ERROR: Instance is not online in Systems Manager (status: %s).\n' \
        "$SSM_STATUS" >&2
    exit 1
fi

COMMAND_PARAMETERS_FILE="$(mktemp)"
trap 'rm -f "$COMMAND_PARAMETERS_FILE"' EXIT

cat >"$COMMAND_PARAMETERS_FILE" <<JSON
{
  "commands": [
    "set -euo pipefail",
    "sudo -u ec2-user git -C /opt/globalpartners-business-analysis fetch origin",
    "sudo -u ec2-user git -C /opt/globalpartners-business-analysis checkout --detach $DEPLOY_COMMIT",
    "/opt/globalpartners-business-analysis/.venv/bin/python -m pip install -r /opt/globalpartners-business-analysis/streamlit/requirements-streamlit.txt",
    "systemctl restart globalpartners-streamlit.service",
    "systemctl is-active globalpartners-streamlit.service",
    "/opt/globalpartners-business-analysis/.venv/bin/python -m pip show streamlit",
    "git -C /opt/globalpartners-business-analysis rev-parse HEAD"
  ]
}
JSON

COMMAND_ID="$(
    aws_cli ssm send-command \
        --instance-ids "$INSTANCE_ID" \
        --document-name AWS-RunShellScript \
        --comment "Deploy Streamlit compatibility hotfix" \
        --parameters "file://$COMMAND_PARAMETERS_FILE" \
        --query 'Command.CommandId' \
        --output text
)"

printf 'SSM command: %s\n' "$COMMAND_ID"
if ! aws_cli ssm wait command-executed \
    --command-id "$COMMAND_ID" \
    --instance-id "$INSTANCE_ID"; then
    printf 'SSM waiter reported a non-success state; retrieving command details.\n'
fi

COMMAND_STATUS="$(
    aws_cli ssm get-command-invocation \
        --command-id "$COMMAND_ID" \
        --instance-id "$INSTANCE_ID" \
        --query 'Status' \
        --output text
)"

aws_cli ssm get-command-invocation \
    --command-id "$COMMAND_ID" \
    --instance-id "$INSTANCE_ID" \
    --query '{Status:Status,Output:StandardOutputContent,Errors:StandardErrorContent}' \
    --output table

if [[ "$COMMAND_STATUS" != "Success" ]]; then
    printf 'ERROR: EC2 update command finished with status %s.\n' \
        "$COMMAND_STATUS" >&2
    exit 1
fi

printf '\nWaiting for Streamlit health endpoint...\n'
HEALTH_URL="${APP_URL}/_stcore/health"
for attempt in {1..30}; do
    if [[ "$(
        curl --fail --silent --show-error \
            --connect-timeout 5 \
            --max-time 10 \
            "$HEALTH_URL" 2>/dev/null || true
    )" == "ok" ]]; then
        printf 'STREAMLIT UPDATE PASSED\n'
        printf 'Open: %s\n' "$APP_URL"
        exit 0
    fi
    printf 'Attempt %s/30: dashboard is restarting.\n' "$attempt"
    sleep 5
done

printf 'ERROR: Streamlit health endpoint did not recover.\n' >&2
exit 1
