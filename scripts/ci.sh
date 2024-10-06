#!/bin/bash

set -e

# TODO: proper ci script

# bash ./scripts/test.sh

pushd ./infrastructure

pushd ./functions/dataSourceMonitor
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install pylint
pylint *.py
deactivate
popd

yarn install --frozen-lockfile
yarn lint
yarn build
yarn cdk synth
popd

# pushd ./model_deploy

# pushd ./customResources/pipelineModel
# yarn install --frozen-lockfile
# popd
# zip -r -q layers/PipelineModelFunctionLayer.zip layers/PipelineModelFunctionLayer/

# yarn install --frozen-lockfile
# yarn lint
# yarn build
# yarn cdk synth
# popd

# pushd ./consumers/online

# pushd ./packages/data-api
# yarn install --frozen-lockfile
# popd

# yarn install --frozen-lockfile
# yarn lint
# yarn build
# yarn cdk synth
# popd
