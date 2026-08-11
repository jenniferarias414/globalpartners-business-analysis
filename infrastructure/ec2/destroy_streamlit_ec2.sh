#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPOSITORY_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
STATE_DIRECTORY="$REPOSITORY_ROOT/reports/generated/streamlit-ec2"
STATE_FILE="$STATE_DIRECTORY/deployment.env"
SSM_POLICY_ARN="arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"

if [[ ! -f "$STATE_FILE" ]]; then
    printf 'ERROR: Deployment state file not found: %s\n' "$STATE_FILE" >&2
    exit 1
fi

# shellcheck disable=SC1090
source "$STATE_FILE"

AWS_PROFILE="${AWS_PROFILE:-retail-poc}"
AWS_REGION="${AWS_REGION:-us-east-2}"
EXPECTED_ACCOUNT="${EXPECTED_ACCOUNT:-272987324508}"

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

if [[ -n "${INSTANCE_ID:-}" && "$INSTANCE_ID" =~ ^i-[0-9a-f]+$ ]]; then
    INSTANCE_STATE="$(
        aws_cli ec2 describe-instances \
            --instance-ids "$INSTANCE_ID" \
            --query 'Reservations[0].Instances[0].State.Name' \
            --output text 2>/dev/null || printf 'not-found'
    )"
    if [[ "$INSTANCE_STATE" != "terminated" && "$INSTANCE_STATE" != "not-found" ]]; then
        printf 'Terminating instance %s...\n' "$INSTANCE_ID"
        aws_cli ec2 terminate-instances \
            --instance-ids "$INSTANCE_ID" \
            --query 'TerminatingInstances[].{InstanceId:InstanceId,Previous:PreviousState.Name,Current:CurrentState.Name}' \
            --output table
        aws_cli ec2 wait instance-terminated --instance-ids "$INSTANCE_ID"
        printf 'Instance terminated.\n'
    else
        printf 'Instance already absent or terminated: %s\n' "$INSTANCE_ID"
    fi
fi

if [[ -n "${SECURITY_GROUP_ID:-}" && "$SECURITY_GROUP_ID" =~ ^sg-[0-9a-f]+$ ]]; then
    printf 'Deleting security group %s...\n' "$SECURITY_GROUP_ID"
    for attempt in {1..12}; do
        if aws_cli ec2 delete-security-group \
            --group-id "$SECURITY_GROUP_ID" 2>/dev/null; then
            printf 'Security group deleted.\n'
            break
        fi
        if [[ "$attempt" == "12" ]]; then
            printf 'ERROR: Security group could not be deleted.\n' >&2
            exit 1
        fi
        sleep 5
    done
fi

if [[ -n "${INSTANCE_PROFILE_NAME:-}" ]]; then
    if aws_cli iam get-instance-profile \
        --instance-profile-name "$INSTANCE_PROFILE_NAME" \
        >/dev/null 2>&1; then
        if [[ -n "${ROLE_NAME:-}" ]]; then
            aws_cli iam remove-role-from-instance-profile \
                --instance-profile-name "$INSTANCE_PROFILE_NAME" \
                --role-name "$ROLE_NAME" 2>/dev/null || true
        fi
        aws_cli iam delete-instance-profile \
            --instance-profile-name "$INSTANCE_PROFILE_NAME"
        printf 'Instance profile deleted.\n'
    fi
fi

if [[ -n "${ROLE_NAME:-}" ]]; then
    if aws_cli iam get-role --role-name "$ROLE_NAME" >/dev/null 2>&1; then
        if [[ -n "${ROLE_POLICY_NAME:-}" ]]; then
            aws_cli iam delete-role-policy \
                --role-name "$ROLE_NAME" \
                --policy-name "$ROLE_POLICY_NAME" 2>/dev/null || true
        fi
        aws_cli iam detach-role-policy \
            --role-name "$ROLE_NAME" \
            --policy-arn "$SSM_POLICY_ARN" 2>/dev/null || true
        aws_cli iam delete-role --role-name "$ROLE_NAME"
        printf 'IAM role deleted.\n'
    fi
fi

DESTROYED_STATE_FILE="$STATE_DIRECTORY/deployment-destroyed-$(date -u +%Y%m%dT%H%M%SZ).env"
mv "$STATE_FILE" "$DESTROYED_STATE_FILE"

printf '\nSTREAMLIT EC2 CLEANUP COMPLETED\n'
printf 'Preserved teardown record: %s\n' "$DESTROYED_STATE_FILE"

