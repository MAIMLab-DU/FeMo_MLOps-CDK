#!/bin/bash

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

pipeline_name=""
ecr_repo_name=""
profile=""

# Usage function
function usage {
    echo "Usage: $0 -c <pipeline_name> -e <ecr_repo_name> [-p|--profile <profile>] [-h|--help]"
    echo
    echo "Options:"
    echo "  -c <pipeline_name>, --pipeline-name <pipeline_name>"
    echo "                         Specify codepipeline name."
    echo "  -e <ecr_repo_name>, --ecr-repo-name <ecr_repo_name>"
    echo "                         Specify codepipeline name."
    echo "  -p <profile>, --profile <profile>"
    echo "                         Specify the AWS profile to use (optional)."
    echo "  -h, --help             Show this help message and exit."
    echo
    exit 0
}

# Parse command-line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -c|--pipeline-name)
            pipeline_name="$2"
            shift 2 
            ;;
        -e|--ecr-repo)
            ecr_repo_name="$2"
            shift 2 
            ;;
        -p|--profile)
            profile="$2"  # Set PROFILE to the next argument
            shift 2
            ;;
        -h|--help)
            usage  # Display help and exit
            ;;
        *)
            echo "Invalid option: $1" >&2
            usage
            exit 1
            ;;
    esac
done

# Validate that CONFIG_S3_PATH and ENVIRONMENT are provided
if [[ -z "$pipeline_name" || -z "$ecr_repo_name" ]]; then
    usage
    exit 1
fi

if [[ -n "$profile" ]]; then
    trigger_detail=$(aws codepipeline list-pipeline-executions --pipeline-name $pipeline_name --profile "$profile" --max-results 1 | jq -r ".pipelineExecutionSummaries[].trigger.triggerDetail // empty")
else
    trigger_detail=$(aws codepipeline list-pipeline-executions --pipeline-name $pipeline_name --max-results 1 | jq -r ".pipelineExecutionSummaries[].trigger.triggerDetail // empty")
fi
echo "trigger_detail: $trigger_detail"

if [[ -z "$trigger_detail" ]]; then
    echo "Error: No pipeline execution found for $pipeline_name" >&2
    exit 1
fi

trigger_repo_id=""
if echo "$trigger_detail" | jq empty 2>/dev/null; then
    trigger_repo_id=$(echo "$trigger_detail" | jq -r ".repositoryId // empty")
fi

if [[ -z "$trigger_repo_id" || "$trigger_repo_id" != "$ML_REPOSITORY_ID"  ]]; then
    echo "Pipeline not triggered by $ML_REPOSITORY_ID"
    exit 0
else
    trigger_tag=$(echo "$trigger_detail" | jq -r ".tagName // empty")
    if [[ -z "$trigger_tag" ]]; then
        echo "No tag found in pipeline execution"
        exit 0
    fi
    echo "Pipeline triggered by change in $ML_REPOSITORY_ID. Buidling and pushing docker image..."
    if [[ -n "$profile" ]]; then
        aws ecr describe-repositories --repository-names "${ecr_repo_name}" --profile "$profile" > /dev/null 2>&1
    else
        aws ecr describe-repositories --repository-names "${ecr_repo_name}" > /dev/null 2>&1
    fi

    if [ $? -ne 0 ]; then
        echo "Error getting docker repository $ecr_repo_name"
        exit 1
    fi

    pushd "$CODEBUILD_SRC_DIR_SourceMLCodeOutput"
  
    version=$(echo "$trigger_tag" | cut -c2-)

    fullname="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_DEFAULT_REGION}.amazonaws.com/${ecr_repo_name}:${version}"
    latest_fullname="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_DEFAULT_REGION}.amazonaws.com/${ecr_repo_name}:latest"

    docker build -t "${ecr_repo_name}:${version}" -f aws_sagemaker/Dockerfile .
    docker tag "${ecr_repo_name}:${version}" "${fullname}"
    docker tag "${ecr_repo_name}:${version}" "${latest_fullname}"

    docker push "${fullname}"
    docker push "${latest_fullname}"
fi
