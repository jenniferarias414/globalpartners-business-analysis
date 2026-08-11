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
: "${SECURITY_GROUP_ID:?Missing SECURITY_GROUP_ID in state file}"
: "${ACCESS_CIDR:?Missing ACCESS_CIDR in state file}"
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

printf 'Validating instance: %s\n' "$INSTANCE_ID"
printf 'Application URL: %s\n' "$APP_URL"

aws_cli ec2 describe-instances \
    --instance-ids "$INSTANCE_ID" \
    --query 'Reservations[0].Instances[0].{State:State.Name,Type:InstanceType,PublicIp:PublicIpAddress,Profile:IamInstanceProfile.Arn,Subnet:SubnetId,SecurityGroups:SecurityGroups[].GroupId}' \
    --output table

printf '\nSecurity-group ingress\n'
aws_cli ec2 describe-security-groups \
    --group-ids "$SECURITY_GROUP_ID" \
    --query 'SecurityGroups[0].IpPermissions[].{Protocol:IpProtocol,FromPort:FromPort,ToPort:ToPort,CIDRs:IpRanges[].CidrIp}' \
    --output table

ACTUAL_CIDR="$(
    aws_cli ec2 describe-security-groups \
        --group-ids "$SECURITY_GROUP_ID" \
        --query 'SecurityGroups[0].IpPermissions[?FromPort==`8501` && ToPort==`8501`].IpRanges[].CidrIp | [0]' \
        --output text
)"
if [[ "$ACTUAL_CIDR" != "$ACCESS_CIDR" ]]; then
    printf 'ERROR: Expected Streamlit CIDR %s but found %s.\n' \
        "$ACCESS_CIDR" "$ACTUAL_CIDR" >&2
    exit 1
fi

printf '\nWaiting for EC2 status checks...\n'
aws_cli ec2 wait instance-status-ok --instance-ids "$INSTANCE_ID"
printf 'EC2 status checks passed.\n'

printf '\nWaiting for Streamlit health endpoint...\n'
HEALTH_URL="${APP_URL}/_stcore/health"
for attempt in {1..45}; do
    if HEALTH_RESPONSE="$(
        curl --fail --silent --show-error \
            --connect-timeout 5 \
            --max-time 10 \
            "$HEALTH_URL" 2>/dev/null
    )"; then
        if [[ "$HEALTH_RESPONSE" == "ok" ]]; then
            printf 'Streamlit health check passed on attempt %s.\n' "$attempt"
            printf '\nDEPLOYMENT VALIDATION PASSED\n'
            printf 'Open: %s\n' "$APP_URL"
            printf 'Access is restricted to: %s\n' "$ACCESS_CIDR"
            exit 0
        fi
    fi

    INSTANCE_STATE="$(
        aws_cli ec2 describe-instances \
            --instance-ids "$INSTANCE_ID" \
            --query 'Reservations[0].Instances[0].State.Name' \
            --output text
    )"
    printf 'Attempt %s/45: instance=%s, dashboard not ready yet.\n' \
        "$attempt" "$INSTANCE_STATE"
    sleep 20
done

printf '\nERROR: Streamlit did not become healthy within 15 minutes.\n' >&2
printf 'Recent EC2 console output:\n' >&2
aws_cli ec2 get-console-output \
    --instance-id "$INSTANCE_ID" \
    --latest \
    --query 'Output' \
    --output text >&2 || true
exit 1

