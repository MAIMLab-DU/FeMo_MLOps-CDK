#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_LOCAL_PATH="$SCRIPT_DIR/../configuration/projectConfig.json"

UPLOAD_FLAG=false
CONFIG_S3_PATH=""
PROFILE=""

# Detect OS (for venv path differences)
OS_TYPE="$(uname | tr '[:upper:]' '[:lower:]')"

# Display help
show_help() {
  echo "Usage: $0 [-u|--upload] -c <CONFIG_S3_PATH> [-p|--profile <PROFILE>] [-h|--help]"
  echo
  echo "Options:"
  echo "  -u, --upload           Upload the configuration file to S3 before downloading it."
  echo "  -c, --config-s3-path   S3 path for the configuration file (e.g., s3://bucket/key.json)"
  echo "  -p, --profile          AWS profile to use (optional)."
  echo "  -h, --help             Show this help message and exit."
  echo
  exit 0
}

upload_to_s3() {
  echo "🔼 Uploading config to S3 if modified..."
  local bucket_name object_key REMOTE_ETAG LOCAL_MD5

  bucket_name=$(echo "$CONFIG_S3_PATH" | cut -d'/' -f3)
  object_key=$(echo "$CONFIG_S3_PATH" | cut -d'/' -f4-)

  # Fetch ETag from S3
  if [[ -n "$PROFILE" ]]; then
    REMOTE_ETAG=$(aws s3api head-object --bucket "$bucket_name" --key "$object_key" \
                  --profile "$PROFILE" --query "ETag" --output text 2>/dev/null | tr -d '"')
  else
    REMOTE_ETAG=$(aws s3api head-object --bucket "$bucket_name" --key "$object_key" \
                  --query "ETag" --output text 2>/dev/null | tr -d '"')
  fi

  # Upload if not present or changed
  if [[ -z "$REMOTE_ETAG" ]]; then
    echo "🆕 No existing object found in S3. Uploading new file..."
    [[ -n "$PROFILE" ]] && aws s3 cp --quiet "$CONFIG_LOCAL_PATH" "$CONFIG_S3_PATH" --profile "$PROFILE" || \
                          aws s3 cp --quiet "$CONFIG_LOCAL_PATH" "$CONFIG_S3_PATH"
    return
  fi

  LOCAL_MD5=$(md5sum "$CONFIG_LOCAL_PATH" | awk '{print $1}')

  if [[ "$REMOTE_ETAG" != "$LOCAL_MD5" ]]; then
    echo "♻️  Detected change in config. Uploading updated file..."
    [[ -n "$PROFILE" ]] && aws s3 cp --quiet "$CONFIG_LOCAL_PATH" "$CONFIG_S3_PATH" --profile "$PROFILE" || \
                          aws s3 cp --quiet "$CONFIG_LOCAL_PATH" "$CONFIG_S3_PATH"
  else
    echo "✅ No changes detected in config. Skipping upload."
  fi
}

# Parse command-line arguments
while [[ $# -gt 0 ]]; do
  case "$1" in
    -u|--upload)
      UPLOAD_FLAG=true
      shift
      ;;
    -c|--config-s3-path)
      CONFIG_S3_PATH="$2"
      shift 2
      ;;
    -p|--profile)
      PROFILE="$2"
      shift 2
      ;;
    -h|--help)
      show_help
      ;;
    *)
      echo "❌ Invalid option: $1"
      echo "Use -h or --help for usage information."
      exit 1
      ;;
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

# Upload if flagged
if [[ "$UPLOAD_FLAG" == true ]]; then
  upload_to_s3
fi

# Download configuration
echo "⬇️  Downloading '$CONFIG_LOCAL_PATH' from '$CONFIG_S3_PATH'..."
[[ -n "$PROFILE" ]] && aws s3 cp --quiet "$CONFIG_S3_PATH" "$CONFIG_LOCAL_PATH" --profile "$PROFILE" || \
                      aws s3 cp --quiet "$CONFIG_S3_PATH" "$CONFIG_LOCAL_PATH"

# Navigate to infrastructure directory
pushd "$SCRIPT_DIR/../infrastructure" > /dev/null

# Python linting in function folder
pushd ./functions/dataSourceMonitor > /dev/null
echo "🐍 Setting up Python venv for ruff..."
python3 -m venv .venv
if [[ "$OS_TYPE" == "mingw"* || "$OS_TYPE" == "msys"* || "$OS_TYPE" == "windows_nt" ]]; then
  source .venv/Scripts/activate
else
  source .venv/bin/activate
fi

pip install ruff==0.6.4
ruff check *.py
deactivate
popd > /dev/null

# Run Yarn commands
echo "📦 Installing Node.js dependencies and building..."
yarn install --frozen-lockfile
yarn lint
yarn build

# Synthesize CDK
echo "📐 Synthesizing CDK app..."
if [[ -n "$PROFILE" ]]; then
  yarn cdk synth --parameter projectConfigPath="$CONFIG_S3_PATH" --profile "$PROFILE" --verbose > template.yml
else
  yarn cdk synth --parameter projectConfigPath="$CONFIG_S3_PATH" --verbose > template.yml
fi

popd > /dev/null
