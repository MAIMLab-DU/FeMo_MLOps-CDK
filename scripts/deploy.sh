#!/bin/bash

set -e

pipeline_name=""
profile=""
codebuild=false

# Usage function
usage() {
    echo "Usage: $0 -n|--pipeline-name <pipeline_name> [OPTIONS]"
    echo
    echo "Required:"
    echo "  -n, --pipeline-name   Specify CodePipeline name (required, supports wildcards)"
    echo
    echo "Options:"
    echo "  -p, --profile         Specify AWS CLI profile (optional)"
    echo "  --codebuild           Flag to indicate script is run by CodeBuild (optional)"
    echo "  -h, --help            Show this help message"
    echo
    echo "Examples:"
    echo "  $0 -n \"FeMo-*Pipeline*\"                    # GitHub/manual deployment"
    echo "  $0 -n \"FeMo-Pipeline\" --codebuild          # CodeBuild deployment"
    exit 0
}

# Parse CLI arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        -n|--pipeline-name) pipeline_name="$2"; shift 2 ;;
        -p|--profile)       profile="$2"; shift 2 ;;
        --codebuild)        codebuild=true; shift ;;
        -h|--help)          usage ;;
        *) echo "Invalid option: $1" >&2; usage ;;
    esac
done

# Validate required arguments
if [[ -z "$pipeline_name" ]]; then
    echo "❌ Error: Pipeline name is required."
    echo ""
    usage
fi

# Set environment variables to handle encoding and pagination
export AWS_PAGER=""
export PYTHONIOENCODING=utf-8

echo "🚀 Deployment Configuration:"
echo "   - Pipeline: $pipeline_name"
echo "   - CodeBuild: $codebuild"
echo "   - Profile: ${profile:-default}"

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

# Determine execution context and get execution ID
if [[ "$codebuild" == true ]]; then
    echo "🔎 CodeBuild context - getting current 'InProgress' execution..."
    # Running from CodeBuild - get current InProgress execution ID
    if [[ -n "$profile" ]]; then
        execution_id=$(aws codepipeline list-pipeline-executions --profile "$profile" \
            --pipeline-name "$pipeline_name" \
            --max-results 5 \
            --query "pipelineExecutionSummaries[?status=='InProgress'] | [0].pipelineExecutionId" \
            --output text)
    else
        execution_id=$(aws codepipeline list-pipeline-executions \
            --pipeline-name "$pipeline_name" \
            --max-results 5 \
            --query "pipelineExecutionSummaries[?status=='InProgress'] | [0].pipelineExecutionId" \
            --output text)
    fi
    
    echo "📄 InProgress Execution ID: $execution_id"
    
    # Get model package from CodeBuild output
    if [[ -f "${CODEBUILD_SRC_DIR_PipelineOutput}/pipelineExecution.json" ]]; then
        model_package_name=$(jq -r ".arn" < "${CODEBUILD_SRC_DIR_PipelineOutput}/pipelineExecution.json")
        echo "📌 MODEL_PACKAGE_NAME (from CodeBuild): ${model_package_name}"
    else
        echo "❌ CodeBuild pipeline output file not found"
        # exit 1
    fi
else
    echo "🔎 GitHub/manual context - getting latest 'Succeeded' execution..."
    # Running from GitHub/manual - get latest successful execution ID
    if [[ -n "$profile" ]]; then
        execution_id=$(aws codepipeline list-pipeline-executions --profile "$profile" \
            --pipeline-name "$pipeline_name" --query "pipelineExecutionSummaries[?status=='Succeeded'] | [0].pipelineExecutionId" --output text)
    else
        execution_id=$(aws codepipeline list-pipeline-executions \
            --pipeline-name "$pipeline_name" --query "pipelineExecutionSummaries[?status=='Succeeded'] | [0].pipelineExecutionId" --output text)
    fi

    if [[ -z "$execution_id" ]]; then
        echo "❌ No successful executions found for pipeline: $pipeline_name"
        exit 1
    fi

    echo "📄 Execution ID: $execution_id"

    # Fetch output artifact info for model package
    action_name="MLPipeline"
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
    echo "📌 MODEL_PACKAGE_NAME (from pipeline): ${model_package_name}"
fi

# Get Git commit ID using the same execution ID
echo "🔎 Fetching Git commit ID for execution: $execution_id"

if [[ -n "$execution_id" && "$execution_id" != "None" && "$execution_id" != "null" ]]; then
    if [[ -n "$profile" ]]; then
        git_commit_id=$(aws codepipeline get-pipeline-execution --profile "$profile" \
            --pipeline-name "$pipeline_name" \
            --pipeline-execution-id "$execution_id" \
            --query "pipelineExecution.artifactRevisions[?name=='SourceMLCodeOutput'] | [0].revisionId" \
            --output text)
    else
        git_commit_id=$(aws codepipeline get-pipeline-execution \
            --pipeline-name "$pipeline_name" \
            --pipeline-execution-id "$execution_id" \
            --query "pipelineExecution.artifactRevisions[?name=='SourceMLCodeOutput'] | [0].revisionId" \
            --output text)
    fi
fi

# Fallback to CodeBuild environment variable if pipeline query fails (CodeBuild only)
if [[ -z "$git_commit_id" || "$git_commit_id" == "None" || "$git_commit_id" == "null" ]]; then
    if [[ "$codebuild" == true ]]; then
        echo "🔄 Falling back to CodeBuild environment variable..."
        git_commit_id="${CODEBUILD_RESOLVED_SOURCE_VERSION:-unknown}"
    else
        git_commit_id="unknown"
        echo "⚠️  Could not determine Git commit ID, using: $git_commit_id"
    fi
else
    echo "📌 GIT_COMMIT_ID: $git_commit_id"
fi

if [[ "$model_package_name" == "NotTrained" ]]; then
    echo "⚠️ Model not trained yet. Skipping deployment."
    exit 1
fi

echo ""
echo "🚀 Deploying model to AWS..."
echo "📌 Deployment parameters:"
echo "   - MODEL_PACKAGE_NAME: $model_package_name"
echo "   - GIT_COMMIT_ID: $git_commit_id"
echo "   - CODEBUILD: $codebuild"

if [[ -n "$profile" ]]; then
    yarn cdk deploy --require-approval never \
        --parameters modelPackageName="$model_package_name" \
        --parameters gitCommitId="$git_commit_id" \
        --profile "$profile" \
        --app cdk.out/
else
    yarn cdk deploy --require-approval never \
        --parameters modelPackageName="$model_package_name" \
        --parameters gitCommitId="$git_commit_id" \
        --app cdk.out/
fi

popd > /dev/null

echo "✅ Deployment completed successfully!"