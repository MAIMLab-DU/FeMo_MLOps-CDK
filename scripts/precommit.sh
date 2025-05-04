#!/bin/bash

set -euo pipefail

echo "🚀 Running pre-commit linting..."

# Define directories to lint
declare -a PROJECTS=("infrastructure" "model_deploy")

for dir in "${PROJECTS[@]}"; do
  if [[ -d "$dir" ]]; then
    echo "🔍 Linting: $dir"
    pushd "$dir" > /dev/null
    yarn lint:fix
    popd > /dev/null
  else
    echo "⚠️ Skipping '$dir' - Directory not found."
  fi
done

echo "✅ Pre-commit checks completed successfully."
