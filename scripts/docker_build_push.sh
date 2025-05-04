#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

pipeline_name=""
ecr_repo_name=""
profile=""

# Usage information
usage() {
    echo "Usage: $0 -c <pipeline_name> -e <ecr_repo_name> [-p <profile>] [-h]"
    echo
    echo "Options:"
    echo "  -c, --pipeline-name   CodePipeline name (required)"
    echo "  -e, --ecr-repo        ECR repository name (required)"
    echo "  -p, --profile         AWS CLI profile (optional)"
    echo "  -h, --help            Show this help message"
    echo
    exit 1
}

# Parse command-line arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        -c|--pipeline-name)
            pipeline_name="$2"
            shift 2
            ;;
        -e|--ecr-repo)
            ecr_repo_name="$2"
            shift 2
            ;;
        -p|--profile)
            profile="$2"
            shift 2
            ;;
        -h|--help)
            usage
            ;;
        *)
            echo "❌ Invalid option: $1"
            usage
            ;;
    esac
done

# Validate required arguments
if [[ -z "$pipeline_name" || -z "$ecr_repo_name" ]]; then
    echo "❌ Error: Both pipeline name (-c) and ECR repo name (-e) are required."
    usage
fi

# Retrieve latest pipeline trigger details
echo "🔍 Fetching pipeline execution details for: $pipeline_name"
if [[ -n "$profile" ]]; then
    trigger_detail=$(aws codepipeline list-pipeline-executions \
        --pipeline-name "$pipeline_name" \
        --max-results 1 \
        --profile "$profile" \
        | jq -r ".pipelineExecutionSummaries[].trigger.triggerDetail // empty")
else
    trigger_detail=$(aws codepipeline list-pipeline-executions \
        --pipeline-name "$pipeline_name" \
        --max-results 1 \
        | jq -r ".pipelineExecutionSummaries[].trigger.triggerDetail // empty")
fi

echo "📄 trigger_detail: $trigger_detail"

if [[ -z "$trigger_detail" ]]; then
    echo "❌ Error: No pipeline execution found for $pipeline_name"
    exit 1
fi

# Parse repository ID and tag
trigger_repo_id=""
if echo "$trigger_detail" | jq empty 2>/dev/null; then
    trigger_repo_id=$(echo "$trigger_detail" | jq -r ".repositoryId // empty")
fi

if [[ -z "$trigger_repo_id" || "$trigger_repo_id" != "$ML_REPOSITORY_ID" ]]; then
    echo "⚠️ Pipeline not triggered by $ML_REPOSITORY_ID"
    exit 0
fi

trigger_tag=$(echo "$trigger_detail" | jq -r ".tagName // empty")
if [[ -z "$trigger_tag" ]]; then
    echo "⚠️ No tag found in pipeline execution"
    exit 0
fi

echo "✅ Pipeline triggered by change in $ML_REPOSITORY_ID. Proceeding with Docker build and push."

# Check if ECR repository exists
echo "🔍 Verifying ECR repository: $ecr_repo_name"
if [[ -n "$profile" ]]; then
    aws ecr describe-repositories --repository-names "$ecr_repo_name" --profile "$profile" > /dev/null 2>&1
else
    aws ecr describe-repositories --repository-names "$ecr_repo_name" > /dev/null 2>&1
fi

if [[ $? -ne 0 ]]; then
    echo "❌ Error: Docker repository '$ecr_repo_name' not found."
    exit 1
fi

pushd "$CODEBUILD_SRC_DIR_SourceMLCodeOutput" > /dev/null

version="${trigger_tag#v}"
fullname="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_DEFAULT_REGION}.amazonaws.com/${ecr_repo_name}:${version}"
latest_fullname="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_DEFAULT_REGION}.amazonaws.com/${ecr_repo_name}:latest"

echo "🔧 Building Docker image with tag: $version"
docker build -t "${ecr_repo_name}:${version}" -f aws_sagemaker/Dockerfile .

echo "🔖 Tagging image: $fullname and $latest_fullname"
docker tag "${ecr_repo_name}:${version}" "$fullname"
docker tag "${ecr_repo_name}:${version}" "$latest_fullname"

echo "📤 Pushing images to ECR..."
docker push "$fullname"
docker push "$latest_fullname"

popd > /dev/null
