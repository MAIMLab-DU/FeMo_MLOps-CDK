#!/bin/bash

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILENAME="configuration/projectConfig.json"

UPLOAD_FLAG=false
CONFIG_S3_PATH=""
PROFILE="default"

# Function to display help
function show_help {
  echo "Usage: $0 [-u|--upload] -c <CONFIG_S3_PATH> [-p|--profile <PROFILE>] [-h|--help]"
  echo
  echo "Options:"
  echo "  -u, --upload           Upload the configuration file to S3 before downloading it."
  echo "  -c <CONFIG_S3_PATH>, --config-s3-path <CONFIG_S3_PATH>"
  echo "                         Specify the S3 path for the configuration file."
  echo "  -p <PROFILE>, --profile <PROFILE>"
  echo "                         Specify the AWS profile to use (optional)."
  echo "  -h, --help             Show this help message and exit."
  echo
  exit 0
}

# Parse command-line arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    -u|--upload)
      UPLOAD_FLAG=true  # Set the upload flag to true
      shift
      ;;
    -c|--config-s3-path)
      CONFIG_S3_PATH="$2"  # Set CONFIG_S3_PATH to the next argument
      shift
      shift
      ;;
    -p|--profile)
      PROFILE="$2"  # Set PROFILE to the next argument
      shift
      shift
      ;;
    -h|--help)
      show_help  # Display help and exit
      ;;
    *)
      echo "Invalid option: $1" >&2
      echo "Use -h or --help for usage information."
      exit 1
      ;;
  esac
done

# Validate that CONFIG_S3_PATH and ENVIRONMENT are provided
if [[ -z "$CONFIG_S3_PATH" ]]; then
  echo "Error: CONFIG_S3_PATH must be specified with -c or --config-s3-path." >&2
  echo "Use -h or --help for usage information."
  exit 1
fi

# If upload flag is set, upload the $S3_KEY file to S3
if [[ "$UPLOAD_FLAG" == true ]]; then
    echo "Uploading '$CONFIG_FILENAME' to S3 path '$CONFIG_S3_PATH'..."
    aws s3 cp "$CONFIG_FILENAME" "$CONFIG_S3_PATH" --profile "$PROFILE"
fi

# Download the configuration file from S3
echo "Downloading '$CONFIG_FILENAME' from S3 path '$CONFIG_S3_PATH'..."
aws s3 cp "$CONFIG_S3_PATH" "$CONFIG_FILENAME" --profile "$PROFILE"

# Navigate to the infrastructure directory
pushd $SCRIPT_DIR/../infrastructure

# Run checks and setup for the dataSourceMonitor function
pushd ./functions/dataSourceMonitor
python3 -m venv .venv
source .venv/bin/activate
pip install ruff==0.6.4
ruff check *.py
deactivate
popd

# Run Yarn commands
yarn install --frozen-lockfile
yarn lint
yarn build
yarn cdk synth --parameter projectConfigPath="$CONFIG_S3_PATH" --profile "$PROFILE" --verbose > template.yml
popd
