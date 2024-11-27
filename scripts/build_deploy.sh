#!/bin/bash

set -e

# Build the Model deployment package

pushd model_deploy

python3 -m venv .venv
source .venv/bin/activate
pip install ruff==0.6.4
ruff check ***/**/*.py
deactivate

yarn install --frozen-lockfile
yarn lint
yarn build
yarn cdk synth --verbose > template.yml
popd
