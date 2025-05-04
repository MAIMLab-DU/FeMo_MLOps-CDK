#!/bin/bash

set -euo pipefail

echo "🧹 Cleaning up Infrastructure Stack..."

if ! command -v jq &>/dev/null; then
  echo "❌ 'jq' is required but not installed. Please install jq to proceed."
  exit 1
fi

if [[ ! -f "./configuration/projectConfig.json" ]]; then
  echo "❌ projectConfig.json not found in ./configuration/"
  exit 1
fi

# Cleanup Infrastructure Stack
pushd ./infrastructure > /dev/null
echo "📦 Installing dependencies for infrastructure..."
yarn install --frozen-lockfile

echo "🔥 Destroying infrastructure stack resources in AWS..."
yarn cdk destroy --force
popd > /dev/null

# Cleanup Model Deploy Stack
echo "🧹 Cleaning up Model Deploy Stack..."

pushd ./model_deploy > /dev/null
echo "📦 Installing dependencies for model_deploy..."
yarn install --frozen-lockfile

echo "🔥 Destroying model deployment stack resources in AWS..."
yarn cdk destroy --force
popd > /dev/null

# Delete SageMaker Pipeline
echo "🧹 Deleting SageMaker Pipeline..."

PROJECT_NAME=$(jq -r '.projectName' ./configuration/projectConfig.json)
if [[ -z "$PROJECT_NAME" ]]; then
  echo "❌ projectName is empty or missing in projectConfig.json"
  exit 1
fi

PIPELINE_ARN=$(aws sagemaker list-pipelines --pipeline-name-prefix "$PROJECT_NAME" \
  | jq -r ".PipelineSummaries[] | select(.PipelineName == \"$PROJECT_NAME\") | .PipelineArn")

echo "🔎 PIPELINE_ARN: ${PIPELINE_ARN:-Not found}"

if [[ -n "${PIPELINE_ARN:-}" ]]; then
  echo "🗑️ Deleting SageMaker Pipeline: $PIPELINE_ARN"
  aws sagemaker delete-pipeline --pipeline-name "$PROJECT_NAME"
else
  echo "⚠️ No SageMaker pipeline found for project: $PROJECT_NAME"
fi

echo "✅ Cleanup completed."
