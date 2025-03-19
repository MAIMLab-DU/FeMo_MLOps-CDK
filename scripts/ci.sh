#!/bin/bash

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_LOCAL_PATH="configuration/projectConfig.json"

UPLOAD_FLAG=false
CONFIG_S3_PATH=""
PROFILE=""

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

function upload_to_s3 {
  # Extract bucket name and object key from CONFIG_S3_PATH
  bucket_name=$(echo "$CONFIG_S3_PATH" | cut -d'/' -f3)
  object_key=$(echo "$CONFIG_S3_PATH" | cut -d'/' -f4-)
  # Get current ETag from S3
  if [[ -n "$PROFILE" ]]; then
    REMOTE_ETAG=$(aws s3api head-object --bucket "$bucket_name" --key "$object_key" --query "ETag" --profile "$PROFILE" --output text 2>/dev/null | tr -d '"')
  else
    REMOTE_ETAG=$(aws s3api head-object --bucket "$bucket_name" --key "$object_key" --query "ETag" --output text 2>/dev/null | tr -d '"')
  fi

  # Check if the file exists in S3
  if [[ -z "$REMOTE_ETAG" ]]; then
    echo "No existing object found in S3. Uploading..."
    if [[ -n "$PROFILE" ]]; then
      aws s3 cp --quiet "$CONFIG_LOCAL_PATH" "$CONFIG_S3_PATH" --profile "$PROFILE"
    else
      aws s3 cp --quiet "$CONFIG_LOCAL_PATH" "$CONFIG_S3_PATH"
    fi
    return
  fi

  # Calculate MD5 checksum of the local file
  LOCAL_MD5=$(md5sum "$CONFIG_LOCAL_PATH" | awk '{print $1}')

  # Compare and upload only if different
  if [[ "$REMOTE_ETAG" != "$LOCAL_MD5" ]]; then
    echo "Uploading modified object to S3..."
    if [[ -n "$PROFILE" ]]; then
      aws s3 cp --quiet "$CONFIG_LOCAL_PATH" "$CONFIG_S3_PATH" --profile "$PROFILE"
    else
      aws s3 cp --quiet "$CONFIG_LOCAL_PATH" "$CONFIG_S3_PATH"
    fi
  else
    echo "No changes detected. Skipping upload."
  fi
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

# Validate CONFIG_S3_PATH format
if [[ ! "$CONFIG_S3_PATH" =~ ^s3://[^/]+/.+\.json$ ]]; then
  echo "Error: CONFIG_S3_PATH must be in the format 's3://bucket/key.json'"
  exit 1
fi


# If upload flag is set, upload the $S3_KEY file to S3
if [[ "$UPLOAD_FLAG" == true ]]; then
  upload_to_s3
fi

# Download the configuration file from S3
echo "Downloading '$CONFIG_LOCAL_PATH' from S3 path '$CONFIG_S3_PATH'..."
if [[ -n "$PROFILE" ]]; then
  aws s3 cp --quiet "$CONFIG_S3_PATH" "$CONFIG_LOCAL_PATH" --profile "$PROFILE"
else
  aws s3 cp --quiet "$CONFIG_S3_PATH" "$CONFIG_LOCAL_PATH"
fi

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
if [[ -n "$PROFILE" ]]; then
  yarn cdk synth --parameter projectConfigPath="$CONFIG_S3_PATH" --profile "$PROFILE" --verbose > template.yml
else
  yarn cdk synth --parameter projectConfigPath="$CONFIG_S3_PATH" --verbose > template.yml
fi
popd
