#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

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
            exit
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

# Handle trigger details
if [[ "$trigger_detail" == "SourceDataBeltA" ]]; then
    bash $SCRIPT_DIR/copy_data_manifest.sh --belt-type "A"

elif [[ "$trigger_detail" == "SourceDataBeltB" ]]; then
    bash $SCRIPT_DIR/run_pipeline.sh --belt-type "B"

elif [[ "$trigger_detail" == "SourceDataBeltC" ]]; then
    bash $SCRIPT_DIR/copy_data_manifest.sh --belt-type "C"

else
    trigger_repository_id=$(echo "$trigger_detail" | jq -r ".repositoryId")
    echo "Pipeline triggered by code change in: $trigger_repository_id"
    # Array of belt types
    belt_types=("A" "B" "C")

    # Loop through each belt type and execute the script
    for belt_type in "${belt_types[@]}"; do
        bash $SCRIPT_DIR/copy_data_manifest.sh --belt-type "$belt_type"
    done
fi
