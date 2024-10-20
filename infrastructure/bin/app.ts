#!/usr/bin/env node
// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
import { App } from 'aws-cdk-lib';
import { InfrastractureStack } from '../lib/infrastractureStack';
import projectConfig = require('../../configuration/projectConfig.json');

const desc: string = "CloudFormation template used for provisioning all the necessary resources for the MLOps insfrastructure, " + 
"for Fetal Movement Analysis project. Resources include: S3 buckets, Lambda functions, Codepipeline pipeline, CodeBuild project, and" + 
"IAM roles with necessary permissions."

const app = new App();
new InfrastractureStack(app, `${projectConfig.projectName}-MLOpsInfraStack`, {
    projectName: projectConfig.projectName,
    repoType: 'git',
    existingDataBucketName: projectConfig.dataBucketName,
    ciBucketName: projectConfig.ciBucketName,
    triggerPeriod: projectConfig.triggerPeriod,
    minNumberOfFiles: projectConfig.minNumberofFiles,
    gitML: projectConfig.gitML,
    gitCDK: projectConfig.gitCDK,
    description: desc,
});
