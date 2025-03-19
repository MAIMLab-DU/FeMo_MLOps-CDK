#!/bin/bash

set -e

pipeline_name=""
profile=""

# Usage function
function usage {
    echo "Usage: $0 [-c|--pipeline-name <pipeline_name>] [-p|--profile <profile>] [-h|--help]"
    echo
    echo "Options:"
    echo "  -c <pipeline_name>, --pipeline-name <pipeline_name>"
    echo "                         Specify codepipeline name (optional)."
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

# Resolve pipeline name if it contains a wildcard
if [[ "$pipeline_name" == *"*"* ]]; then    
    # Fetch the list of pipelines
    if [[ -n "$profile" ]]; then
        pipelines=$(aws codepipeline list-pipelines --profile "$profile" --query "pipelines[?contains(name, '${pipeline_name//\*/}')].name" --output text)
    else
        pipelines=$(aws codepipeline list-pipelines --query "pipelines[?contains(name, '${pipeline_name//\*/}')].name" --output text)
    fi
    
    if [[ -z "$pipelines" ]]; then
        echo "Error: No pipeline names match the pattern: $pipeline_name"
        exit 1
    fi
    
    # Check if there are multiple matches
    pipeline_count=$(echo "$pipelines" | wc -l)
    if [[ "$pipeline_count" -gt 1 ]]; then
        echo "Error: Multiple pipelines match the pattern: $pipeline_name"
        echo "Matched pipelines:"
        echo "$pipelines"
        exit 1
    fi
    
    # Use the resolved pipeline name
    pipeline_name="$pipelines"
    echo "Resolved pipeline name: $pipeline_name"
fi

pushd ./model_deploy
echo 'Installing dependencies'
yarn install --check-files

if [[ -z "$pipeline_name" ]]; then
    model_package_name=$(cat ${CODEBUILD_SRC_DIR_PipelineOutput}/pipelineExecution.json | jq ".arn" -r)
    echo MODEL_PACKAGE_NAME=${model_package_name}
else
    action_name="MLPipeline"
    
    # Get the latest execution ID of the pipeline
    if [[ -n "$profile" ]]; then
        execution_id=$(aws codepipeline list-pipeline-executions --profile "$profile" \
            --pipeline-name "$pipeline_name" \
            --max-results 1 | jq -r ".pipelineExecutionSummaries[].pipelineExecutionId // empty")
    else
        execution_id=$(aws codepipeline list-pipeline-executions \
            --pipeline-name "$pipeline_name" \
            --max-results 1 | jq -r ".pipelineExecutionSummaries[].pipelineExecutionId // empty")
    fi

    if [[ -z "$execution_id" ]]; then
        echo "No executions found for pipeline: $pipeline_name"
        exit 1
    fi

    # Get details of the stage's output artifacts for the latest execution
    if [[ -n "$profile" ]]; then
        output=$(aws codepipeline list-action-executions --profile "$profile" \
            --pipeline-name "$pipeline_name" \
            --filter pipelineExecutionId="$execution_id" \
            --no-paginate \
            --query "actionExecutionDetails[?actionName=='MLPipeline'].output[].outputArtifacts[]")
    else
        output=$(aws codepipeline list-action-executions \
            --pipeline-name "$pipeline_name" \
            --filter pipelineExecutionId="$execution_id" \
            --no-paginate \
            --query "actionExecutionDetails[?actionName=='MLPipeline'].output[].outputArtifacts[]")
    fi

    if [[ "$output" == "[]" ]]; then
        echo "No output artifacts found for stage: $action_name in execution: $execution_id"
        exit 1
    fi

    # Parse and download artifact
    artifact_s3_path=$(echo "$output" | jq -r '.[] | "s3://\(.s3location.bucket)/\(.s3location.key)"')
    if [[ -n "$profile" ]]; then
        aws s3 cp --quiet "$artifact_s3_path" artifact.zip --profile "$profile"
    else
        aws s3 cp --quiet "$artifact_s3_path" artifact.zip
    fi

    # Check if the file exists
    if [[ ! -f artifact.zip ]]; then
        echo "Error: Artifact zip file was not downloaded."
        exit 1
    fi
    unzip -o -q artifact.zip 'pipelineExecution.json'

    # Check for extraction errors
    if [[ $? -ne 0 ]]; then
        echo "Error: Failed to extract files from artifact.zip."
        exit 1
    fi
    rm artifact.zip

    model_package_name=$(cat pipelineExecution.json | jq ".arn" -r)
    echo MODEL_PACKAGE_NAME=${model_package_name}
fi

if [[ "$model_package_name" == "NotTrained" ]]; then
    echo "Model not trained yet..."
    exit 1
fi

echo 'Deploying Model in your AWS account'
if [[ -n "$profile" ]]; then
    yarn cdk deploy --require-approval never --parameters modelPackageName=${model_package_name} --profile "$profile" --app cdk.out/
else
    yarn cdk deploy --require-approval never --parameters modelPackageName=${model_package_name} --app cdk.out/
fi
popd
