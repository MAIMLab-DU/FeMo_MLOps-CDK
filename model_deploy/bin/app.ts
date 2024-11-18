#!/usr/bin/env node
// SPDX-License-Identifier: MIT-0

import { App } from 'aws-cdk-lib';
import { ModelDeploymentStack } from '../lib/modelDeploymentStack';

import projectConfig = require('../../configuration/projectConfig.json');

const app = new App();

new ModelDeploymentStack(app, `Deployment-${projectConfig.projectName}`, {
    ...projectConfig,
});
