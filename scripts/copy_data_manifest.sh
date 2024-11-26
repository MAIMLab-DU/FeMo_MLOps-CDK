#!/bin/bash

set -e

belt_type=""

function usage {
    echo "Usage: $0 -b <belt_type> [-h|--help]"
    echo
    echo "Options:"
    echo "  -b <belt_type>, --belt-type <belt_type>"
    echo "                         Specify the FeMo belt type (A, B, or C)."
    echo "  -h, --help             Show this help message and exit."
    echo
}

# Parse command-line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -b|--belt-type)
            belt_type="$2"
            shift 2 
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Invalid option: $1" >&2
            usage
            exit 1
            ;;
    esac
done

# Validate belt type
if [[ -z "$belt_type" ]]; then
    echo "Error: Belt type must be specified."
    usage
    exit 1
fi

if [[ ! "$belt_type" =~ ^[ABC]$ ]]; then
    echo "Error: Belt type must be one of 'A', 'B', or 'C'."
    exit 1
fi

# Set CODEBUILD_SRC_DIR_<source-name> based on belt_type
case "$belt_type" in
    A)
        manifest_file="$CODEBUILD_SRC_DIR_SourceDataOutputBeltA/manifest-A.json"
        ;;
    B)
        manifest_file="$CODEBUILD_SRC_DIR_SourceDataOutputBeltB/manifest-B.json"
        ;;
    C)
        manifest_file="$CODEBUILD_SRC_DIR_SourceDataOutputBeltC/manifest-C.json"
        ;;
esac

# Check if manifest file exists
if [[ ! -f "$manifest_file" ]]; then
    echo "Error: Manifest file not found: $manifest_file"
    exit 1
fi

# Check if 'items' array in the manifest file has a length greater than 0
items_count=$(jq '.items | length' "$manifest_file")
export ITEMS_COUNT="$items_count"

echo "The 'items' array in the manifest file contains $items_count items."

cat ${manifest_file} > ${CODEBUILD_SRC_DIR_SourceMLCodeOutput}/configs/dataManifest.json
echo "Copied Data Manifest for beltType '$belt_type' to ML Pipeline Source folder"
