#!/bin/bash

set -e

# Build the Model deployment package

pushd model_deploy

pushd ./customResources/pipelineModel
yarn install --frozen-lockfile
popd
zip -r -q layers/PipelineModelFunctionLayer.zip layers/PipelineModelFunctionLayer/

yarn install --frozen-lockfile
yarn lint
yarn build
yarn cdk synth
popd
