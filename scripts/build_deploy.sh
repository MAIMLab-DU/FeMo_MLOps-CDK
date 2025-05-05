#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_LOCAL_PATH="$SCRIPT_DIR/../configuration/projectConfig.json"
CONFIG_S3_PATH=""
profile=""

# Detect OS
case "$OSTYPE" in
  msys*|cygwin*|win32*) VENV_ACTIVATE=".venv/Scripts/activate" ;;
  *) VENV_ACTIVATE=".venv/bin/activate" ;;
esac

# Usage
function usage {
    echo "Usage: $0 -c <CONFIG_S3_PATH> [-p|--profile <profile>] [-h|--help]"
    echo
    echo "Options:"
    echo "  -c, --config-s3-path   S3 path for the configuration file (e.g., s3://bucket/key.json)"
    echo "  -p <profile>, --profile <profile>   AWS profile to use (optional)."
    echo "  -h, --help                          Show this help message."
    exit 0
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -c|--config-s3-path) CONFIG_S3_PATH="$2"; shift 2 ;;
        -p|--profile) profile="$2"; shift 2 ;;
        -h|--help) usage ;;
        *) echo "Invalid option: $1"; usage; exit 1 ;;
    esac
done

# Validation
if [[ -z "$CONFIG_S3_PATH" ]]; then
  echo "❌ Error: CONFIG_S3_PATH must be specified with -c or --config-s3-path."
  exit 1
fi

if [[ ! "$CONFIG_S3_PATH" =~ ^s3://[^/]+/.+\.json$ ]]; then
  echo "❌ Error: CONFIG_S3_PATH must be in the format 's3://bucket/key.json'"
  exit 1
fi

# Check tools
for tool in python3 pip yarn; do
  command -v $tool >/dev/null 2>&1 || { echo "❌ $tool is required but not installed."; exit 1; }
done

# Download configuration
echo "⬇️  Downloading '$CONFIG_LOCAL_PATH' from '$CONFIG_S3_PATH'..."
[[ -n "$profile" ]] && aws s3 cp --quiet "$CONFIG_S3_PATH" "$CONFIG_LOCAL_PATH" --profile "$profile" || \
                      aws s3 cp --quiet "$CONFIG_S3_PATH" "$CONFIG_LOCAL_PATH"

pushd "$SCRIPT_DIR/../model_deploy"

# Python venv setup
if [ ! -d .venv ]; then
  python3 -m venv .venv
fi

source "$VENV_ACTIVATE"
pip install ruff==0.6.4

if ! ruff check ***/**/*.py; then
  echo "❌ Python linting failed."
  deactivate
  exit 1
fi

deactivate

# Node/Yarn Build
echo "📦 Installing Node.js dependencies and building..."
yarn install --frozen-lockfile
yarn lint || { echo "❌ Yarn lint failed"; exit 1; }
yarn build || { echo "❌ Yarn build failed"; exit 1; }

# CDK Synth
echo "📐 Synthesizing CDK app..."
if [[ -n "$profile" ]]; then
    yarn cdk synth --profile "$profile" --verbose > template.yml
else
    yarn cdk synth --verbose > template.yml
fi

popd
