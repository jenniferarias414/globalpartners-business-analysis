#!/usr/bin/env bash
set -euo pipefail

AWS_PROFILE="${AWS_PROFILE:-retail-poc}"
AWS_REGION="${AWS_REGION:-us-east-2}"
EXPECTED_ACCOUNT="272987324508"
SUBNET_ID="${GP_EC2_SUBNET_ID:-subnet-0e78d42d928d510ed}"
VPC_ID="vpc-0a738a266d69140d4"
INSTANCE_TYPE="t3.micro"
AMI_PARAMETER="/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
ROLE_NAME="globalpartners-streamlit-ec2-role"
INSTANCE_PROFILE_NAME="globalpartners-streamlit-ec2-profile"
ROLE_POLICY_NAME="globalpartners-streamlit-athena-access"
SECURITY_GROUP_NAME="globalpartners-streamlit-sg"
INSTANCE_NAME="globalpartners-streamlit-dashboard"
PROJECT_BUCKET="globalpartners-data-jenny"
ATHENA_WORKGROUP="globalpartners-analysis"
GLUE_DATABASE="globalpartners_gold"
SSM_POLICY_ARN="arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPOSITORY_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
USER_DATA_FILE="$SCRIPT_DIR/streamlit-user-data.sh"
STATE_DIRECTORY="$REPOSITORY_ROOT/reports/generated/streamlit-ec2"
STATE_FILE="$STATE_DIRECTORY/deployment.env"

export AWS_PAGER=""

aws_cli() {
    aws "$@" \
        --profile "$AWS_PROFILE" \
        --region "$AWS_REGION" \
        --no-cli-pager
}

record_state() {
    printf '%s=%q\n' "$1" "$2" >>"$STATE_FILE"
}

resource_exists() {
    "$@" >/dev/null 2>&1
}

mkdir -p "$STATE_DIRECTORY"

ACCOUNT_ID="$(aws_cli sts get-caller-identity --query 'Account' --output text)"
IDENTITY_ARN="$(aws_cli sts get-caller-identity --query 'Arn' --output text)"

if [[ "$ACCOUNT_ID" != "$EXPECTED_ACCOUNT" ]]; then
    printf 'ERROR: Expected account %s but found %s.\n' \
        "$EXPECTED_ACCOUNT" "$ACCOUNT_ID" >&2
    exit 1
fi

ACCESS_IP="$(curl --fail --silent --show-error https://checkip.amazonaws.com | tr -d '[:space:]')"
if [[ ! "$ACCESS_IP" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]]; then
    printf 'ERROR: Could not resolve a valid public IPv4 address.\n' >&2
    exit 1
fi
ACCESS_CIDR="$ACCESS_IP/32"

AMI_ID="$(
    aws_cli ssm get-parameter \
        --name "$AMI_PARAMETER" \
        --query 'Parameter.Value' \
        --output text
)"

printf 'Verified profile: %s\n' "$AWS_PROFILE"
printf 'Verified account: %s\n' "$ACCOUNT_ID"
printf 'Verified identity: %s\n' "$IDENTITY_ARN"
printf 'Region: %s\n' "$AWS_REGION"
printf 'AMI: %s\n' "$AMI_ID"
printf 'Subnet: %s\n' "$SUBNET_ID"
printf 'Streamlit access: %s\n' "$ACCESS_CIDR"

ACTIVE_INSTANCE_ID="$(
    aws_cli ec2 describe-instances \
        --filters \
            "Name=tag:Name,Values=$INSTANCE_NAME" \
            'Name=instance-state-name,Values=pending,running,stopping,stopped' \
        --query 'Reservations[0].Instances[0].InstanceId' \
        --output text
)"
if [[ -n "$ACTIVE_INSTANCE_ID" && "$ACTIVE_INSTANCE_ID" != "None" ]]; then
    printf 'ERROR: Existing deployment instance found: %s\n' \
        "$ACTIVE_INSTANCE_ID" >&2
    printf 'Validate or destroy the existing deployment before creating another.\n' >&2
    exit 1
fi

: >"$STATE_FILE"
record_state AWS_PROFILE "$AWS_PROFILE"
record_state AWS_REGION "$AWS_REGION"
record_state EXPECTED_ACCOUNT "$EXPECTED_ACCOUNT"
record_state ACCESS_CIDR "$ACCESS_CIDR"
record_state VPC_ID "$VPC_ID"
record_state SUBNET_ID "$SUBNET_ID"
record_state ROLE_NAME "$ROLE_NAME"
record_state INSTANCE_PROFILE_NAME "$INSTANCE_PROFILE_NAME"
record_state ROLE_POLICY_NAME "$ROLE_POLICY_NAME"
record_state SECURITY_GROUP_NAME "$SECURITY_GROUP_NAME"
record_state INSTANCE_NAME "$INSTANCE_NAME"

TRUST_POLICY_FILE="$(mktemp)"
IAM_POLICY_FILE="$(mktemp)"
trap 'rm -f "$TRUST_POLICY_FILE" "$IAM_POLICY_FILE"' EXIT

cat >"$TRUST_POLICY_FILE" <<'JSON'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {"Service": "ec2.amazonaws.com"},
      "Action": "sts:AssumeRole"
    }
  ]
}
JSON

cat >"$IAM_POLICY_FILE" <<JSON
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AthenaQueries",
      "Effect": "Allow",
      "Action": [
        "athena:StartQueryExecution",
        "athena:GetQueryExecution",
        "athena:GetQueryResults",
        "athena:StopQueryExecution",
        "athena:GetWorkGroup"
      ],
      "Resource": "arn:aws:athena:${AWS_REGION}:${ACCOUNT_ID}:workgroup/${ATHENA_WORKGROUP}"
    },
    {
      "Sid": "GlueCatalogRead",
      "Effect": "Allow",
      "Action": [
        "glue:GetDatabase",
        "glue:GetDatabases",
        "glue:GetTable",
        "glue:GetTables",
        "glue:GetPartition",
        "glue:GetPartitions",
        "glue:BatchGetPartition"
      ],
      "Resource": [
        "arn:aws:glue:${AWS_REGION}:${ACCOUNT_ID}:catalog",
        "arn:aws:glue:${AWS_REGION}:${ACCOUNT_ID}:database/${GLUE_DATABASE}",
        "arn:aws:glue:${AWS_REGION}:${ACCOUNT_ID}:table/${GLUE_DATABASE}/*"
      ]
    },
    {
      "Sid": "ProjectBucketList",
      "Effect": "Allow",
      "Action": [
        "s3:GetBucketLocation",
        "s3:ListBucket"
      ],
      "Resource": "arn:aws:s3:::${PROJECT_BUCKET}"
    },
    {
      "Sid": "GoldDataRead",
      "Effect": "Allow",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::${PROJECT_BUCKET}/gold/*"
    },
    {
      "Sid": "AthenaResultAccess",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:AbortMultipartUpload"
      ],
      "Resource": "arn:aws:s3:::${PROJECT_BUCKET}/athena-results/*"
    }
  ]
}
JSON

printf '\nCreating IAM role and instance profile...\n'
if ! resource_exists aws_cli iam get-role --role-name "$ROLE_NAME"; then
    aws_cli iam create-role \
        --role-name "$ROLE_NAME" \
        --assume-role-policy-document "file://$TRUST_POLICY_FILE" \
        --description "Temporary EC2 role for the GlobalPartners Streamlit dashboard" \
        --tags Key=Project,Value=globalpartners-business-analysis Key=Purpose,Value=temporary-streamlit
fi

aws_cli iam put-role-policy \
    --role-name "$ROLE_NAME" \
    --policy-name "$ROLE_POLICY_NAME" \
    --policy-document "file://$IAM_POLICY_FILE"

aws_cli iam attach-role-policy \
    --role-name "$ROLE_NAME" \
    --policy-arn "$SSM_POLICY_ARN"

if ! resource_exists aws_cli iam get-instance-profile \
    --instance-profile-name "$INSTANCE_PROFILE_NAME"; then
    aws_cli iam create-instance-profile \
        --instance-profile-name "$INSTANCE_PROFILE_NAME" \
        --tags Key=Project,Value=globalpartners-business-analysis Key=Purpose,Value=temporary-streamlit
fi

PROFILE_ROLE_COUNT="$(
    aws_cli iam get-instance-profile \
        --instance-profile-name "$INSTANCE_PROFILE_NAME" \
        --query "length(InstanceProfile.Roles[?RoleName=='$ROLE_NAME'])" \
        --output text
)"
if [[ "$PROFILE_ROLE_COUNT" == "0" ]]; then
    aws_cli iam add-role-to-instance-profile \
        --instance-profile-name "$INSTANCE_PROFILE_NAME" \
        --role-name "$ROLE_NAME"
fi

printf '\nCreating IP-restricted security group...\n'
SECURITY_GROUP_ID="$(
    aws_cli ec2 describe-security-groups \
        --filters \
            "Name=vpc-id,Values=$VPC_ID" \
            "Name=group-name,Values=$SECURITY_GROUP_NAME" \
        --query 'SecurityGroups[0].GroupId' \
        --output text
)"

if [[ -z "$SECURITY_GROUP_ID" || "$SECURITY_GROUP_ID" == "None" ]]; then
    SECURITY_GROUP_ID="$(
        aws_cli ec2 create-security-group \
            --group-name "$SECURITY_GROUP_NAME" \
            --description "Temporary Streamlit access restricted to one public IP" \
            --vpc-id "$VPC_ID" \
            --tag-specifications \
                "ResourceType=security-group,Tags=[{Key=Name,Value=$SECURITY_GROUP_NAME},{Key=Project,Value=globalpartners-business-analysis},{Key=Purpose,Value=temporary-streamlit}]" \
            --query 'GroupId' \
            --output text
    )"
fi
record_state SECURITY_GROUP_ID "$SECURITY_GROUP_ID"

if ! aws_cli ec2 authorize-security-group-ingress \
    --group-id "$SECURITY_GROUP_ID" \
    --ip-permissions "IpProtocol=tcp,FromPort=8501,ToPort=8501,IpRanges=[{CidrIp=$ACCESS_CIDR,Description=Temporary-Streamlit-browser-access}]" \
    2>"$STATE_DIRECTORY/security-group-ingress-error.txt"; then
    if ! grep -q 'InvalidPermission.Duplicate' \
        "$STATE_DIRECTORY/security-group-ingress-error.txt"; then
        cat "$STATE_DIRECTORY/security-group-ingress-error.txt" >&2
        exit 1
    fi
fi
rm -f "$STATE_DIRECTORY/security-group-ingress-error.txt"

printf '\nLaunching encrypted %s instance...\n' "$INSTANCE_TYPE"
INSTANCE_ID=""
for attempt in {1..12}; do
    if INSTANCE_ID="$(
        aws_cli ec2 run-instances \
            --image-id "$AMI_ID" \
            --instance-type "$INSTANCE_TYPE" \
            --count 1 \
            --subnet-id "$SUBNET_ID" \
            --security-group-ids "$SECURITY_GROUP_ID" \
            --iam-instance-profile "Name=$INSTANCE_PROFILE_NAME" \
            --associate-public-ip-address \
            --metadata-options 'HttpEndpoint=enabled,HttpTokens=required,HttpPutResponseHopLimit=1' \
            --block-device-mappings '[{"DeviceName":"/dev/xvda","Ebs":{"VolumeSize":8,"VolumeType":"gp3","Encrypted":true,"DeleteOnTermination":true}}]' \
            --user-data "file://$USER_DATA_FILE" \
            --tag-specifications \
                "ResourceType=instance,Tags=[{Key=Name,Value=$INSTANCE_NAME},{Key=Project,Value=globalpartners-business-analysis},{Key=Purpose,Value=temporary-streamlit}]" \
                'ResourceType=volume,Tags=[{Key=Project,Value=globalpartners-business-analysis},{Key=Purpose,Value=temporary-streamlit}]' \
            --query 'Instances[0].InstanceId' \
            --output text 2>"$STATE_DIRECTORY/run-instances-error.txt"
    )"; then
        break
    fi

    if grep -q 'Invalid IAM Instance Profile' \
        "$STATE_DIRECTORY/run-instances-error.txt"; then
        printf 'Waiting for IAM instance-profile propagation (%s/12)...\n' \
            "$attempt"
        sleep 5
    else
        cat "$STATE_DIRECTORY/run-instances-error.txt" >&2
        exit 1
    fi
done
rm -f "$STATE_DIRECTORY/run-instances-error.txt"

if [[ -z "$INSTANCE_ID" || "$INSTANCE_ID" == "None" ]]; then
    printf 'ERROR: Instance launch did not return an instance ID.\n' >&2
    exit 1
fi
record_state INSTANCE_ID "$INSTANCE_ID"
record_state INSTANCE_TYPE "$INSTANCE_TYPE"
record_state AMI_ID "$AMI_ID"

printf 'Instance launched: %s\n' "$INSTANCE_ID"
printf 'Waiting for the instance to enter running state...\n'
aws_cli ec2 wait instance-running --instance-ids "$INSTANCE_ID"

PUBLIC_IP="$(
    aws_cli ec2 describe-instances \
        --instance-ids "$INSTANCE_ID" \
        --query 'Reservations[0].Instances[0].PublicIpAddress' \
        --output text
)"
PUBLIC_DNS="$(
    aws_cli ec2 describe-instances \
        --instance-ids "$INSTANCE_ID" \
        --query 'Reservations[0].Instances[0].PublicDnsName' \
        --output text
)"
APP_URL="http://${PUBLIC_IP}:8501"

record_state PUBLIC_IP "$PUBLIC_IP"
record_state PUBLIC_DNS "$PUBLIC_DNS"
record_state APP_URL "$APP_URL"
record_state DEPLOYED_AT_UTC "$(date -u +%Y-%m-%dT%H:%M:%SZ)"

printf '\nDeployment resources created.\n'
printf 'Instance ID: %s\n' "$INSTANCE_ID"
printf 'Public IP: %s\n' "$PUBLIC_IP"
printf 'Application URL: %s\n' "$APP_URL"
printf 'State file: %s\n' "$STATE_FILE"
printf '\nThe application is still installing. Run the validator next.\n'
printf 'Remember to run destroy_streamlit_ec2.sh after screenshots and the walkthrough.\n'
