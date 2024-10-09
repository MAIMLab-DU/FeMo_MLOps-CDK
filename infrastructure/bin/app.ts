#!/usr/bin/env node
// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
import { App } from 'aws-cdk-lib';
import { InfrastractureStack } from '../lib/infrastractureStack';
import projectConfig = require('../../configuration/projectConfig.json');

const app = new App();
new InfrastractureStack(app, `${projectConfig.projectName}-MLOpsInfraStack`, {
    projectName: projectConfig.projectName,
    repoType: 'git',
    existingDataBucketName: projectConfig.dataBucketName,
    triggerPeriod: projectConfig.triggerPeriod,
    minNumberOfFiles: projectConfig.minNumberofFiles,
    gitML: projectConfig.gitML,
    gitCDK: projectConfig.gitCDK,
});
