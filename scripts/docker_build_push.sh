#!/bin/bash
set -e

# Usage function
usage() {
    echo "Usage: $0 --trigger-repo <trigger_repo> --ml-repo <ml_repo> --trigger-tag <trigger_tag> --ecr-repo <ecr_rep>"
    exit 1
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --trigger-repo)
            trigger_repo="$2"
            shift 2
            ;;
        --ml-repo)
            ml_repo="$2"
            shift 2
            ;;
        --trigger-tag)
            trigger_tag="$2"
            shift 2
            ;;
        --ecr-repo)
            ecr_repo="$2"
            shift 2
            ;;
        *)
            usage
            ;;
    esac
done

# Check if required arguments are provided
if [[ -z "$trigger_repo" || -z "$ml_repo" || -z "$trigger_tag" || -z "$ecr_repo" ]]; then
    usage
fi

# Script logic
if [[ "$trigger_repo" == "$ml_repo" && -n "$trigger_tag" ]]; then
    echo "Pipeline is triggered by change in ML Repository. Building and pushing docker image..."
    aws ecr describe-repositories --repository-names "${ecr_repo}" > /dev/null 2>&1

    if [ $? -ne 0 ]; then
        echo "Error getting docker repository $ecr_repo"
        exit 1
    fi

    pushd "$CODEBUILD_SRC_DIR_SourceMLCodeOutput"
  
    version=$(echo "$trigger_tag" | cut -c2-)

    fullname="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_DEFAULT_REGION}.amazonaws.com/${ecr_repo}:${version}"
    latest_fullname="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_DEFAULT_REGION}.amazonaws.com/${ecr_repo}:latest"

    docker build -t "${ecr_repo}:${version}" -f aws_sagemaker/Dockerfile .
    docker tag "${ecr_repo}:${version}" "${fullname}"
    docker tag "${ecr_repo}:${version}" "${latest_fullname}"

    docker push "${fullname}"
    docker push "${latest_fullname}"

    popd
else
    echo "Pipeline is not triggered by ML Repository"
    exit 0
fi
