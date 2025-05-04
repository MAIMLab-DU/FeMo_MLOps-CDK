#!/bin/bash

set -euo pipefail

echo "📁 Preparing to copy Data Manifest to ML Pipeline source folder..."

# Define source and destination paths
SOURCE_MANIFEST="${CODEBUILD_SRC_DIR_SourceDataOutput}/manifest.json"
DESTINATION_CONFIG="${CODEBUILD_SRC_DIR_SourceMLCodeOutput}/configs/dataManifest.json"

# Verify that the source manifest exists
if [[ ! -f "$SOURCE_MANIFEST" ]]; then
    echo "❌ Error: Source manifest file not found at '$SOURCE_MANIFEST'"
    exit 1
fi

# Create destination directory if it doesn't exist
mkdir -p "$(dirname "$DESTINATION_CONFIG")"

# Copy the file
cp "$SOURCE_MANIFEST" "$DESTINATION_CONFIG"
echo "✅ Data Manifest successfully copied to: $DESTINATION_CONFIG"
