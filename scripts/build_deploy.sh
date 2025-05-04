#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
profile=""

# Detect OS
case "$OSTYPE" in
  msys*|cygwin*|win32*) VENV_ACTIVATE=".venv/Scripts/activate" ;;
  *) VENV_ACTIVATE=".venv/bin/activate" ;;
esac

# Usage
function usage {
    echo "Usage: $0 [-p|--profile <profile>] [-h|--help]"
    echo
    echo "Options:"
    echo "  -p <profile>, --profile <profile>   AWS profile to use (optional)."
    echo "  -h, --help                          Show this help message."
    exit 0
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -p|--profile) profile="$2"; shift 2 ;;
        -h|--help) usage ;;
        *) echo "Invalid option: $1"; usage; exit 1 ;;
    esac
done

# Check tools
for tool in python3 pip yarn; do
  command -v $tool >/dev/null 2>&1 || { echo "❌ $tool is required but not installed."; exit 1; }
done

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
