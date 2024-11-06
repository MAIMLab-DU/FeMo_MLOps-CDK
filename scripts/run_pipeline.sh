#!/bin/bash

set -e

LOCAL_MODE=false

# Parse command-line arguments
while getopts ":l" opt; do
  case ${opt} in
    l )
      LOCAL_MODE=true  # Set the flag to true if -l is provided
      ;;
    \? )
      echo "Invalid option: -$OPTARG" >&2
      exit 1
      ;;
  esac
done
echo "Local mode: $LOCAL_MODE"
# Create/Update the SageMaker Pipeline and wait for the execution to be completed

VIRTUAL_ENV=.venv

pushd ${CODEBUILD_SRC_DIR_BuildOutputML}/aws_sagemaker

# Set up virtual env
virtualenv -p python3 $VIRTUAL_ENV
. $VIRTUAL_ENV/bin/activate 

#Install requirements
pip install -r requirements.txt

echo "Starting Pipeline Execution"
export PYTHONUNBUFFERED=TRUE
python run_pipeline.py --module-name pipeline \
        --role-arn $SAGEMAKER_PIPELINE_ROLE_ARN \
        --tags "[{\"Key\":\"sagemaker:project-name\", \"Value\":\"${SAGEMAKER_PROJECT_NAME}\"}]" \
        --kwargs "{\"region\":\"${AWS_DEFAULT_REGION}\",\"role\":\"${SAGEMAKER_PIPELINE_ROLE_ARN}\",\"default_bucket\":\"${SAGEMAKER_ARTIFACT_BUCKET}\",\"pipeline_name\":\"${SAGEMAKER_PROJECT_NAME}\",\"model_package_group_name\":\"${SAGEMAKER_PROJECT_NAME}\",\"base_job_prefix\":\"${SAGEMAKER_PROJECT_NAME}\",\"local_mode\":\"${LOCAL_MODE}\"}"

echo "Create/Update of the SageMaker Pipeline and execution Completed."

# Deactivate virtual envs
deactivate
