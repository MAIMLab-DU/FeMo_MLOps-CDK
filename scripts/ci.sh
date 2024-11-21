#!/bin/bash

set -e

UPLOAD_FLAG=false

# Parse command-line arguments
while getopts ":U" opt; do
  case ${opt} in
    U )
      UPLOAD_FLAG=true  # Set the flag to true if -U is provided
      ;;
    \? )
      echo "Invalid option: -$OPTARG" >&2
      exit 1
      ;;
  esac
done

S3_KEY="configuration/projectConfig.json"

aws configure set aws_access_key_id $AWS_ACCESS_KEY_ID && \
aws configure set aws_secret_access_key $AWS_SECRET_ACCESS_KEY && \
aws configure set default.region $AWS_DEFAULT_REGION

# If upload flag is set, upload the $S3_KEY file to S3
if [ "$UPLOAD_FLAG" = true ]; then
    echo "Uploading '$S3_KEY' to S3..."
    aws s3 cp $S3_KEY s3://$S3_CIBUCKET/$S3_KEY
fi

echo "Downloading '$S3_KEY' from S3..."
aws s3 cp s3://$S3_CIBUCKET/$S3_KEY $S3_KEY

pushd ./infrastructure

pushd ./functions/dataSourceMonitor
python3 -m venv .venv
source .venv/bin/activate
pip install ruff==0.6.4
ruff check *.py
deactivate
popd

yarn install --frozen-lockfile
yarn lint
yarn build
yarn cdk synth
popd
