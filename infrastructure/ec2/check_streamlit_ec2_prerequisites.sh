#!/usr/bin/env bash
set -euo pipefail

AWS_PROFILE="${AWS_PROFILE:-retail-poc}"
AWS_REGION="${AWS_REGION:-us-east-2}"
EXPECTED_ACCOUNT="272987324508"
PROJECT_BUCKET="globalpartners-data-jenny"
GLUE_DATABASE="globalpartners_gold"
ATHENA_WORKGROUP="globalpartners-analysis"
REPOSITORY_URL="https://github.com/jenniferarias414/globalpartners-business-analysis.git"
AMI_PARAMETER="/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
ROLE_NAME="globalpartners-streamlit-ec2-role"
INSTANCE_PROFILE_NAME="globalpartners-streamlit-ec2-profile"
SECURITY_GROUP_NAME="globalpartners-streamlit-sg"
INSTANCE_NAME="globalpartners-streamlit-dashboard"

export AWS_PAGER=""

heading() {
    printf '\n## %s\n' "$1"
}

aws_cli() {
    aws "$@" \
        --profile "$AWS_PROFILE" \
        --region "$AWS_REGION" \
        --no-cli-pager
}

heading "AWS identity"
ACCOUNT_ID="$(
    aws_cli sts get-caller-identity \
        --query 'Account' \
        --output text
)"
IDENTITY_ARN="$(
    aws_cli sts get-caller-identity \
        --query 'Arn' \
        --output text
)"

if [[ "$ACCOUNT_ID" != "$EXPECTED_ACCOUNT" ]]; then
    printf 'ERROR: Expected account %s but found %s.\n' \
        "$EXPECTED_ACCOUNT" "$ACCOUNT_ID" >&2
    exit 1
fi

printf 'Profile: %s\n' "$AWS_PROFILE"
printf 'Region: %s\n' "$AWS_REGION"
printf 'Account: %s\n' "$ACCOUNT_ID"
printf 'Identity: %s\n' "$IDENTITY_ARN"

heading "Current public IP"
PUBLIC_IP="$(curl --fail --silent --show-error https://checkip.amazonaws.com | tr -d '[:space:]')"
if [[ ! "$PUBLIC_IP" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]]; then
    printf 'ERROR: Could not resolve a valid public IPv4 address.\n' >&2
    exit 1
fi
printf 'Streamlit access CIDR: %s/32\n' "$PUBLIC_IP"

heading "Latest Amazon Linux 2023 AMI"
AMI_ID="$(
    aws_cli ssm get-parameter \
        --name "$AMI_PARAMETER" \
        --query 'Parameter.Value' \
        --output text
)"
printf 'AMI parameter: %s\n' "$AMI_PARAMETER"
printf 'AMI ID: %s\n' "$AMI_ID"

heading "Default VPC and public subnets"
VPC_ID="$(
    aws_cli ec2 describe-vpcs \
        --filters 'Name=is-default,Values=true' \
        --query 'Vpcs[0].VpcId' \
        --output text
)"

if [[ -z "$VPC_ID" || "$VPC_ID" == "None" ]]; then
    printf 'ERROR: No default VPC exists in %s.\n' "$AWS_REGION" >&2
    exit 1
fi

printf 'Default VPC: %s\n' "$VPC_ID"

aws_cli ec2 describe-subnets \
    --filters \
        "Name=vpc-id,Values=$VPC_ID" \
        'Name=state,Values=available' \
        'Name=map-public-ip-on-launch,Values=true' \
    --query 'Subnets[].{SubnetId:SubnetId,AvailabilityZone:AvailabilityZone,AvailableIPs:AvailableIpAddressCount,PublicIPOnLaunch:MapPublicIpOnLaunch}' \
    --output table

PUBLIC_SUBNET_COUNT="$(
    aws_cli ec2 describe-subnets \
        --filters \
            "Name=vpc-id,Values=$VPC_ID" \
            'Name=state,Values=available' \
            'Name=map-public-ip-on-launch,Values=true' \
        --query 'length(Subnets)' \
        --output text
)"

if [[ "$PUBLIC_SUBNET_COUNT" == "0" ]]; then
    printf 'ERROR: No public-IP-on-launch subnet is available.\n' >&2
    exit 1
fi

INTERNET_GATEWAY_COUNT="$(
    aws_cli ec2 describe-internet-gateways \
        --filters "Name=attachment.vpc-id,Values=$VPC_ID" \
        --query 'length(InternetGateways)' \
        --output text
)"

if [[ "$INTERNET_GATEWAY_COUNT" == "0" ]]; then
    printf 'ERROR: The default VPC has no attached internet gateway.\n' >&2
    exit 1
fi
printf 'Attached internet gateways: %s\n' "$INTERNET_GATEWAY_COUNT"

heading "Data and query dependencies"
aws_cli s3api head-bucket --bucket "$PROJECT_BUCKET"
printf 'S3 bucket accessible: s3://%s\n' "$PROJECT_BUCKET"

aws_cli glue get-database \
    --name "$GLUE_DATABASE" \
    --query 'Database.{Name:Name,Description:Description}' \
    --output table

aws_cli athena get-work-group \
    --work-group "$ATHENA_WORKGROUP" \
    --query 'WorkGroup.{Name:Name,State:State,OutputLocation:Configuration.ResultConfiguration.OutputLocation}' \
    --output table

heading "Public repository"
if curl --fail --silent --show-error --head \
    "${REPOSITORY_URL%.git}" >/dev/null; then
    printf 'Repository reachable without credentials: %s\n' "$REPOSITORY_URL"
else
    printf 'ERROR: EC2 user data cannot reach the public repository URL.\n' >&2
    exit 1
fi

heading "Existing deployment resources"
if aws_cli iam get-role --role-name "$ROLE_NAME" \
    --query 'Role.{RoleName:RoleName,Arn:Arn}' --output table 2>/dev/null; then
    printf 'Existing IAM role found.\n'
else
    printf 'IAM role does not exist yet: %s\n' "$ROLE_NAME"
fi

if aws_cli iam get-instance-profile \
    --instance-profile-name "$INSTANCE_PROFILE_NAME" \
    --query 'InstanceProfile.{Name:InstanceProfileName,Arn:Arn}' \
    --output table 2>/dev/null; then
    printf 'Existing instance profile found.\n'
else
    printf 'Instance profile does not exist yet: %s\n' \
        "$INSTANCE_PROFILE_NAME"
fi

aws_cli ec2 describe-security-groups \
    --filters \
        "Name=vpc-id,Values=$VPC_ID" \
        "Name=group-name,Values=$SECURITY_GROUP_NAME" \
    --query 'SecurityGroups[].{GroupId:GroupId,GroupName:GroupName,VpcId:VpcId}' \
    --output table

aws_cli ec2 describe-instances \
    --filters \
        "Name=tag:Name,Values=$INSTANCE_NAME" \
        'Name=instance-state-name,Values=pending,running,stopping,stopped' \
    --query 'Reservations[].Instances[].{InstanceId:InstanceId,State:State.Name,Type:InstanceType,PublicIp:PublicIpAddress,LaunchTime:LaunchTime}' \
    --output table

heading "Preflight result"
printf 'PASS: Required AWS identity, networking, data resources, AMI, and repository are available.\n'
printf 'No AWS resources were created or changed.\n'
printf 'Save this access CIDR for deployment: %s/32\n' "$PUBLIC_IP"
