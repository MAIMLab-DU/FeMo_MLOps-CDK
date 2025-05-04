#!/bin/bash

set -e

pipeline_name=""
profile=""

# Usage function
usage() {
    echo "Usage: $0 [-c|--pipeline-name <pipeline_name>] [-p|--profile <profile>] [-h|--help]"
    echo
    echo "Options:"
    echo "  -c, --pipeline-name   Specify CodePipeline name (optional, supports wildcards)"
    echo "  -p, --profile         Specify AWS CLI profile (optional)"
    echo "  -h, --help            Show this help message"
    exit 0
}

# Parse CLI arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        -c|--pipeline-name) pipeline_name="$2"; shift 2 ;;
        -p|--profile)       profile="$2"; shift 2 ;;
        -h|--help)          usage ;;
        *) echo "Invalid option: $1" >&2; usage ;;
    esac
done

# Ensure required tools are installed
for tool in aws jq yarn unzip; do
    if ! command -v "$tool" &>/dev/null; then
        echo "❌ Required tool '$tool' is not installed. Exiting."
        exit 1
    fi
done

# Resolve wildcard pipeline name if needed
if [[ "$pipeline_name" == *"*"* ]]; then
    echo "🔍 Resolving wildcard pipeline name..."
    query_string="pipelines[?contains(name, '${pipeline_name//\*/}')].name"
    if [[ -n "$profile" ]]; then
        pipelines=$(aws codepipeline list-pipelines --profile "$profile" --query "$query_string" --output text)
    else
        pipelines=$(aws codepipeline list-pipelines --query "$query_string" --output text)
    fi

    if [[ -z "$pipelines" ]]; then
        echo "❌ No pipeline names match the pattern: $pipeline_name"
        exit 1
    fi

    pipeline_count=$(echo "$pipelines" | wc -l)
    if [[ "$pipeline_count" -gt 1 ]]; then
        echo "❌ Multiple pipelines match the pattern: $pipeline_name"
        echo "Matched pipelines:"
        echo "$pipelines"
        exit 1
    fi

    pipeline_name="$pipelines"
    echo "✅ Resolved pipeline name: $pipeline_name"
fi

pushd ./model_deploy > /dev/null

echo "📦 Installing dependencies..."
yarn install --check-files

if [[ -z "$pipeline_name" ]]; then
    model_package_name=$(jq -r ".arn" < "${CODEBUILD_SRC_DIR_PipelineOutput}/pipelineExecution.json")
    echo "📌 MODEL_PACKAGE_NAME=${model_package_name}"
else
    echo "🔎 Fetching latest successful execution for pipeline: $pipeline_name"
    action_name="MLPipeline"

    query_execution_id="pipelineExecutionSummaries[?status=='Succeeded'] | [0].pipelineExecutionId"
    if [[ -n "$profile" ]]; then
        execution_id=$(aws codepipeline list-pipeline-executions --profile "$profile" \
            --pipeline-name "$pipeline_name" --query "$query_execution_id" --output text)
    else
        execution_id=$(aws codepipeline list-pipeline-executions \
            --pipeline-name "$pipeline_name" --query "$query_execution_id" --output text)
    fi

    if [[ -z "$execution_id" ]]; then
        echo "❌ No successful executions found for pipeline: $pipeline_name"
        exit 1
    fi

    echo "📄 Execution ID: $execution_id"

    # Fetch output artifact info
    if [[ -n "$profile" ]]; then
        output=$(aws codepipeline list-action-executions --profile "$profile" \
            --pipeline-name "$pipeline_name" \
            --filter pipelineExecutionId="$execution_id" \
            --no-paginate \
            --query "actionExecutionDetails[?actionName=='$action_name'].output[].outputArtifacts[]")
    else
        output=$(aws codepipeline list-action-executions \
            --pipeline-name "$pipeline_name" \
            --filter pipelineExecutionId="$execution_id" \
            --no-paginate \
            --query "actionExecutionDetails[?actionName=='$action_name'].output[].outputArtifacts[]")
    fi

    if [[ "$output" == "[]" ]]; then
        echo "❌ No output artifacts found for stage: $action_name in execution: $execution_id"
        exit 1
    fi

    artifact_s3_path=$(echo "$output" | jq -r '.[] | "s3://\(.s3location.bucket)/\(.s3location.key)"')
    echo "⬇️  Downloading artifact: $artifact_s3_path"

    if [[ -n "$profile" ]]; then
        aws s3 cp --quiet "$artifact_s3_path" artifact.zip --profile "$profile"
    else
        aws s3 cp --quiet "$artifact_s3_path" artifact.zip
    fi

    if [[ ! -f artifact.zip ]]; then
        echo "❌ Artifact zip file was not downloaded."
        exit 1
    fi

    echo "📂 Extracting pipelineExecution.json..."
    unzip -o -q artifact.zip 'pipelineExecution.json' || {
        echo "❌ Failed to extract pipelineExecution.json"
        exit 1
    }

    rm artifact.zip

    model_package_name=$(jq -r ".arn" < pipelineExecution.json)
    echo "📌 MODEL_PACKAGE_NAME=${model_package_name}"
fi

if [[ "$model_package_name" == "NotTrained" ]]; then
    echo "⚠️ Model not trained yet. Skipping deployment."
    exit 1
fi

echo "🚀 Deploying model to AWS..."
if [[ -n "$profile" ]]; then
    yarn cdk deploy --require-approval never --parameters modelPackageName="$model_package_name" --profile "$profile" --app cdk.out/
else
    yarn cdk deploy --require-approval never --parameters modelPackageName="$model_package_name" --app cdk.out/
fi

popd > /dev/null
