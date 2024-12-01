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
        manifest_file="$CODEBUILD_SRC_DIR_SourceDataBeltAOutput/manifest-A.json"
        ;;
    B)
        manifest_file="$CODEBUILD_SRC_DIR_SourceDataBeltBOutput/manifest-B.json"
        ;;
    C)
        manifest_file="$CODEBUILD_SRC_DIR_SourceDataBeltCOutput/manifest-C.json"
        ;;
esac

# Check if manifest file exists
if [[ ! -f "$manifest_file" ]]; then
    echo "Error: Manifest file not found: $manifest_file"
    exit 1
fi

cat ${manifest_file} > ${CODEBUILD_SRC_DIR_SourceMLCodeOutput}/configs/dataManifest_belt${belt_type}.json
echo "Copied Data Manifest for beltType '$belt_type' to ML Pipeline Source folder"
