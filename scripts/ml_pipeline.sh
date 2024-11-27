#!/bin/bash
set -e

# Usage function
usage() {
    echo "Usage: $0 --codepipeline-name <codepipeline_name>"
    exit 1
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --codepipeline-name)
            codepipeline_name="$2"
            shift 2
            ;;
        *)
            usage
            ;;
    esac
done

# Check if required arguments are provided
if [[ -z "$codepipeline_name" ]]; then
    usage
fi

# Fetch trigger detail
trigger_detail=$(aws codepipeline list-pipeline-executions --pipeline-name "$codepipeline_name" --max-results 1 | jq -r ".pipelineExecutionSummaries[].trigger.triggerDetail")
echo "triggerDetail: $trigger_detail"

cd $CODEBUILD_SRC_DIR_BuildOutputML/aws_sagemaker/
# Handle trigger details
if [[ "$trigger_detail" == "SourceDataBeltA" ]]; then
    echo "Running sagemaker pipeline for Belt Type A ....."
    bash run_pipeline.sh --belt-type "A"

elif [[ "$trigger_detail" == "SourceDataBeltB" ]]; then
    echo "Running sagemaker pipeline for Belt Type B ....."
    bash run_pipeline.sh --belt-type "B"

elif [[ "$trigger_detail" == "SourceDataBeltC" ]]; then
    echo "Running sagemaker pipeline for Belt Type C ....."
    bash run_pipeline.sh --belt-type "C"

else
    trigger_repository_id=$(echo "$trigger_detail" | jq -r ".repositoryId")
    echo "Pipeline triggered by code change in: $trigger_repository_id"
    # Array of belt types
    belt_types=("A" "B" "C")

    # Loop through each belt type and execute the script
    for belt_type in "${belt_types[@]}"; do
        echo "Running sagemaker pipeline for Belt Type: $belt_type"
        bash run_pipeline.sh --belt-type "$belt_type"
        if [[ $? -ne 0 ]]; then
            echo "Error occurred while running pipeline for Belt Type: $belt_type"
            exit 1
        fi
    done
    echo "Pipeline execution completed for all belt types."
fi
