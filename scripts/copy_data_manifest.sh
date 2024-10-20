#!/bin/bash

set -e

# Copy the Data Manifest file to the main folder

echo "Copying Data Manifest to ML Pipeline Source folder"
cat ${CODEBUILD_SRC_DIR_SourceDataOutput}/manifest.json > ${CODEBUILD_SRC_DIR_SourceMLCodeOutput}/configs/dataManifest.json
