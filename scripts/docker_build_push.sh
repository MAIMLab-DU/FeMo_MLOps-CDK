#!/bin/bash
set -e

if [[ "$TRIGGER_REPO" == "$ML_REPO_NAME" ]]; then
    echo "Pipeline is triggered by $ML_REPO_NAME. Building and pushing docker image..."
    aws ecr describe-repositories --repository-names "${ALGORITHM_NAME}" > /dev/null 2>&1

    if [ $? -ne 0 ]
    then
        echo "Error getting docker repository $ALGORITHM_NAME"
        exit 1
    fi

    VIRTUAL_ENV=.venv
    pushd $CODEBUILD_SRC_DIR_SourceMLCodeOutput/aws_sagemaker/

    # Get the latest version of 'feme' package
    virtualenv -p python3 $VIRTUAL_ENV
    . $VIRTUAL_ENV/bin/activate
    pip install $CODEBUILD_SRC_DIR_SourceMLCodeOutput/aws_sagemaker/.. -q
    version=$(pip show "femo" | grep "Version" | awk '{print $2}')
    deactivate

    fullname="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_DEFAULT_REGION}.amazonaws.com/${ALGORITHM_NAME}:${version}"
    latest_fullname="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_DEFAULT_REGION}.amazonaws.com/${ALGORITHM_NAME}:latest"

    # Build the docker image locally with the image name and then push it to ECR
    # with the full name.

    docker build  -t "${ALGORITHM_NAME}:${version}" -f Dockerfile $CODEBUILD_SRC_DIR_SourceMLCodeOutput/aws_sagemaker/..
    docker tag "${ALGORITHM_NAME}:${version}" ${fullname}
    docker tag "${ALGORITHM_NAME}:${version}" ${latest_fullname}

    docker push ${fullname}
    docker push ${latest_fullname}

else
    echo "Pipeline is not triggered by $ML_REPO_NAME"
    exit 0
fi
