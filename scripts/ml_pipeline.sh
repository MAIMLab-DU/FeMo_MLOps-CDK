#!/bin/bash
set -e

# Usage function
usage() {
    echo "Usage: $0 --codepipeline-name <codepipeline_name>"
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        -c|--codepipeline-name)
            codepipeline_name="$2"
            shift 2
            ;;
        *)
            usage
            exit 0
            ;;
    esac
done

# Check if required arguments are provided
if [[ -z "$codepipeline_name" ]]; then
    usage
    exit 1
fi

# Fetch trigger detail
trigger_detail=$(aws codepipeline list-pipeline-executions --pipeline-name "$codepipeline_name" --max-results 1 | jq -r ".pipelineExecutionSummaries[].trigger.triggerDetail")
echo "triggerDetail: $trigger_detail"

# shellcheck disable=SC2154
cd "$CODEBUILD_SRC_DIR_BuildOutputML"
case "$trigger_detail" in
    SourceDataBeltA)
        manifest_file="$CODEBUILD_SRC_DIR_BuildOutputML/configs/dataManifest_beltA.json"
        ;;
    SourceDataBeltB)
        manifest_file="$CODEBUILD_SRC_DIR_BuildOutputML/configs/dataManifest_beltB.json"
        ;;
    SourceDataBeltC)
        manifest_file="$CODEBUILD_SRC_DIR_BuildOutputML/configs/dataManifest_beltC.json"
        ;;
esac

if [[ "$trigger_detail" == "SourceDataBeltA" || "$trigger_detail" == "SourceDataBeltB" || "$trigger_detail" == "SourceDataBeltC" ]]; then
    items_count=$(jq '.items | length' "$manifest_file")
    if [[ "$items_count" -le 0 ]]; then
        echo "Items array is empty, stopping pipeline execution."
        execution_id=$(aws codepipeline list-pipeline-executions --pipeline-name "$codepipeline_name" --max-results 1 | jq -r ".pipelineExecutionSummaries[].pipelineExecutionId")
        aws codepipeline stop-pipeline-execution \
            --pipeline-name "$codepipeline_name" \
            --pipeline-execution-id "$execution_id" \
            --region "$AWS_DEFAULT_REGION" \
            --reason "Items array is empty in manifest."
        exit 0
    fi
    bash aws_sagemaker/run_pipeline.sh --manifest-file "$manifest_file"
    exit 0
fi

trigger_repository_id=$(echo "$trigger_detail" | jq -r ".repositoryId // empty")
if [[ -n $trigger_repository_id ]]; then
    echo "Pipeline triggered by code change in: $trigger_repository_id"
    belt_types=("A" "B" "C")

    # Loop through each belt type and execute the script
    for belt_type in "${belt_types[@]}"; do
        manifest_file="$CODEBUILD_SRC_DIR_BuildOutputML/configs/dataManifest_belt$belt_type.json"
        items_count=$(jq '.items | length' "$manifest_file")
        
        if [[ "$items_count" -le 0 ]]; then
            echo "Items array is empty, skipping pipeline run for Belt Type: $belt_type"
            output_file="aws_sagemaker/pipelineExecution_belt$belt_type.json"
            echo '{"arn": "NotTrained"}' > "$output_file"
            
            continue
        fi

        echo "Running sagemaker pipeline for Belt Type: $belt_type"
        bash aws_sagemaker/run_pipeline.sh --manifest-file "$manifest_file"
        if [[ $? -ne 0 ]]; then
            echo "Error occurred while running pipeline for Belt Type: $belt_type"
            exit 1
        fi
    done
    echo "Pipeline execution completed for all belt types."
fi
