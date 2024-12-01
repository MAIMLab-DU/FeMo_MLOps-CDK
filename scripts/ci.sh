#!/bin/bash

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
config_local_path="configuration/projectConfig.json"

upload_flag=false
config_s3_path=""
profile=""

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
  bucket_name=$(echo "$config_s3_path" | cut -d'/' -f3)
  object_key=$(echo "$config_s3_path" | cut -d'/' -f4-)
  # Get current ETag from S3
  if [[ -n "$profile" ]]; then
    remote_tag=$(aws s3api head-object --bucket "$bucket_name" --key "$object_key" --query "ETag" --profile "$profile" --output text 2>/dev/null | tr -d '"')
  else
    remote_tag=$(aws s3api head-object --bucket "$bucket_name" --key "$object_key" --query "ETag" --output text 2>/dev/null | tr -d '"')
  fi

  # Check if the file exists in S3
  if [[ -z "$remote_tag" ]]; then
    echo "No existing object found in S3. Uploading..."
    if [[ -n "$profile" ]]; then
      aws s3 cp --quiet "$config_local_path" "$config_s3_path" --profile "$profile"
    else
      aws s3 cp --quiet "$config_local_path" "$config_s3_path"
    fi
    return
  fi

  # Calculate MD5 checksum of the local file
  local_md5=$(md5sum "$config_local_path" | awk '{print $1}')

  # Compare and upload only if different
  if [[ "$remote_tag" != "$local_md5" ]]; then
    echo "Uploading modified object to S3..."
    if [[ -n "$profile" ]]; then
      aws s3 cp --quiet "$config_local_path" "$config_s3_path" --profile "$profile"
    else
      aws s3 cp --quiet "$config_local_path" "$config_s3_path"
    fi
  else
    echo "No changes detected. Skipping upload."
  fi
}

# Parse command-line arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    -u|--upload)
      upload_flag=true  # Set the upload flag to true
      shift
      ;;
    -c|--config-s3-path)
      config_s3_path="$2"  # Set CONFIG_S3_PATH to the next argument
      shift
      shift
      ;;
    -p|--profile)
      profile="$2"  # Set PROFILE to the next argument
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
if [[ -z "$config_s3_path" ]]; then
  echo "Error: CONFIG_S3_PATH must be specified with -c or --config-s3-path." >&2
  echo "Use -h or --help for usage information."
  exit 1
fi

# Validate CONFIG_S3_PATH format
if [[ ! "$config_s3_path" =~ ^s3://[^/]+/.+\.json$ ]]; then
  echo "Error: CONFIG_S3_PATH must be in the format 's3://bucket/key.json'"
  exit 1
fi

# If upload flag is set, upload the $S3_KEY file to S3
if [[ "$upload_flag" == true ]]; then
  upload_to_s3
fi

# Download the configuration file from S3
echo "Downloading '$config_local_path' from S3 path '$config_s3_path'..."
if [[ -n "$profile" ]]; then
  aws s3 cp --quiet "$config_s3_path" "$config_local_path" --profile "$profile"
else
  aws s3 cp --quiet "$config_s3_path" "$config_local_path"
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
if [[ -n "$profile" ]]; then
  yarn cdk synth --parameter projectConfigPath="$config_s3_path" --profile "$profile" --verbose > template.yml
else
  yarn cdk synth --parameter projectConfigPath="$config_s3_path" --verbose > template.yml
fi
popd
