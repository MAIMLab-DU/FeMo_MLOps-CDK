#!/bin/bash
set -e


if [[ "$TRIGGER_CONNECTION" == "$ML_REPO_CONNECTION" && -n "$TRIGGER_TAG" ]]; then
    echo "Pipeline is triggered by change in ML Repository. Building and pushing docker image..."
    aws ecr describe-repositories --repository-names "${ECR_REPOSITORY_NAME}" > /dev/null 2>&1

    if [ $? -ne 0 ]
    then
        echo "Error getting docker repository $ECR_REPOSITORY_NAME"
        exit 1
    fi

    VIRTUAL_ENV=.venv
    pushd $CODEBUILD_SRC_DIR_SourceMLCodeOutput
  
    version=`echo $TRIGGER_TAG | cut -c2-`

    fullname="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_DEFAULT_REGION}.amazonaws.com/${ECR_REPOSITORY_NAME}:${version}"
    latest_fullname="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_DEFAULT_REGION}.amazonaws.com/${ECR_REPOSITORY_NAME}:latest"

    docker build  -t "${ECR_REPOSITORY_NAME}:${version}" -f aws_sagemaker/Dockerfile .
    docker tag "${ECR_REPOSITORY_NAME}:${version}" ${fullname}
    docker tag "${ECR_REPOSITORY_NAME}:${version}" ${latest_fullname}

    docker push ${fullname}
    docker push ${latest_fullname}

else
    echo "Pipeline is not triggered by ML Repository"
    exit 0
fi
