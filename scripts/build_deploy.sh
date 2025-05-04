#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
profile=""

# Detect OS (for venv path differences)
OS_TYPE="$(uname | tr '[:upper:]' '[:lower:]')"

# Usage function
function usage {
    echo "Usage: $0 [-p|--profile <profile>] [-h|--help]"
    echo
    echo "Options:"
    echo "  -p <profile>, --profile <profile>"
    echo "                         Specify the AWS profile to use (optional)."
    echo "  -h, --help             Show this help message and exit."
    echo
    exit 0
}

# Parse command-line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -p|--profile)
            profile="$2"  # Set PROFILE to the next argument
            shift 2
            ;;
        -h|--help)
            usage  # Display help and exit
            ;;
        *)
            echo "Invalid option: $1" >&2
            usage
            exit 1
            ;;
    esac
done

# Build the Model deployment package

pushd $SCRIPT_DIR/../model_deploy

python3 -m venv .venv
# Detect platform-specific venv activation
if [[ "$OS_TYPE" == "mingw"* || "$OS_TYPE" == "msys"* || "$OS_TYPE" == "windows_nt" ]]; then
  source .venv/Scripts/activate
else
  source .venv/bin/activate
fi
pip install ruff==0.6.4
ruff check ***/**/*.py
deactivate

yarn install --frozen-lockfile
yarn lint
yarn build
if [[ -n "$profile" ]]; then
    yarn cdk synth --profile "$profile" --verbose > template.yml
else
    yarn cdk synth --verbose > template.yml
fi
popd
