#!/usr/bin/env bash

set -euo pipefail

PROFILE="${GP_AWS_PROFILE:-retail-poc}"
REGION="${GP_AWS_REGION:-us-east-2}"
EXPECTED_ACCOUNT="${GP_EXPECTED_AWS_ACCOUNT:-272987324508}"
DATABASE="${GP_GLUE_DATABASE:-globalpartners_gold}"
WORKGROUP="${GP_ATHENA_WORKGROUP:-globalpartners-analysis}"
QUERY_DIRECTORY="${GP_QUERY_DIRECTORY:-sql/business}"
OUTPUT_DIRECTORY="${GP_OUTPUT_DIRECTORY:-reports/generated/athena-business}"
SUMMARY_FILE="${OUTPUT_DIRECTORY}/query_run_summary.csv"

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
echo "Athena database: ${DATABASE}"
echo "Athena workgroup: ${WORKGROUP}"

mkdir -p "$OUTPUT_DIRECTORY"
printf '%s\n' \
    'query_name,query_execution_id,status,data_scanned_bytes,execution_milliseconds,result_file' \
    > "$SUMMARY_FILE"

query_count=0

for query_file in "$QUERY_DIRECTORY"/[0-9][0-9]_*.sql; do
    query_count=$((query_count + 1))
    query_name="$(basename "$query_file" .sql)"

    echo
    echo "Starting ${query_name}..."

    query_id="$(aws athena start-query-execution \
        --query-string "file://${query_file}" \
        --query-execution-context "Database=${DATABASE},Catalog=AwsDataCatalog" \
        --work-group "$WORKGROUP" \
        --profile "$PROFILE" \
        --region "$REGION" \
        --query QueryExecutionId \
        --output text \
        --no-cli-pager)"

    while true; do
        state="$(aws athena get-query-execution \
            --query-execution-id "$query_id" \
            --profile "$PROFILE" \
            --region "$REGION" \
            --query 'QueryExecution.Status.State' \
            --output text \
            --no-cli-pager)"

        case "$state" in
            SUCCEEDED)
                break
                ;;
            FAILED|CANCELLED)
                reason="$(aws athena get-query-execution \
                    --query-execution-id "$query_id" \
                    --profile "$PROFILE" \
                    --region "$REGION" \
                    --query 'QueryExecution.Status.StateChangeReason' \
                    --output text \
                    --no-cli-pager)"
                echo "ERROR: ${query_name} ${state}: ${reason}" >&2
                exit 1
                ;;
            *)
                sleep 2
                ;;
        esac
    done

    result_location="$(aws athena get-query-execution \
        --query-execution-id "$query_id" \
        --profile "$PROFILE" \
        --region "$REGION" \
        --query 'QueryExecution.ResultConfiguration.OutputLocation' \
        --output text \
        --no-cli-pager)"

    data_scanned_bytes="$(aws athena get-query-execution \
        --query-execution-id "$query_id" \
        --profile "$PROFILE" \
        --region "$REGION" \
        --query 'QueryExecution.Statistics.DataScannedInBytes' \
        --output text \
        --no-cli-pager)"

    execution_milliseconds="$(aws athena get-query-execution \
        --query-execution-id "$query_id" \
        --profile "$PROFILE" \
        --region "$REGION" \
        --query 'QueryExecution.Statistics.EngineExecutionTimeInMillis' \
        --output text \
        --no-cli-pager)"

    result_file="${OUTPUT_DIRECTORY}/${query_name}.csv"

    aws s3 cp "$result_location" "$result_file" \
        --profile "$PROFILE" \
        --region "$REGION" \
        --no-progress

    printf '%s,%s,%s,%s,%s,%s\n' \
        "$query_name" \
        "$query_id" \
        "$state" \
        "$data_scanned_bytes" \
        "$execution_milliseconds" \
        "$result_file" \
        >> "$SUMMARY_FILE"

    echo "Succeeded: ${query_name}"
    echo "Result: ${result_file}"
done

echo
echo "Completed ${query_count} Athena business queries."
echo "Run summary: ${SUMMARY_FILE}"
