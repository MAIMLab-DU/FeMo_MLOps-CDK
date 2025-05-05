#!/bin/bash

set -euo pipefail

echo "🚀 Running pre-commit linting..."

# Define directories to lint
declare -a PROJECTS=("infrastructure" "model_deploy")

for dir in "${PROJECTS[@]}"; do
  if [[ -d "$dir" ]]; then
    echo "🔍 Linting: $dir"
    pushd "$dir" > /dev/null

    # Check if node_modules exists; install if missing
    if [[ ! -d "node_modules" ]]; then
      echo "📦 Installing dependencies in $dir..."
      yarn install --frozen-lockfile
    fi

    # Run lint fix if script exists
    if yarn run | grep -q "lint:fix"; then
      yarn lint:fix
    else
      echo "⚠️  No lint:fix script found in $dir/package.json. Skipping."
    fi

    popd > /dev/null
  else
    echo "⚠️ Skipping '$dir' - Directory not found."
  fi
done

echo "✅ Pre-commit checks completed successfully."
