// SPDX-License-Identifier: MIT-0
import { Stack, StackProps, CfnOutput } from 'aws-cdk-lib';
import { Construct } from 'constructs';
import { CodePipelineConstruct, CodePipelineConstructPropsBase } from './codePipelineConstruct';
import { DataSourceConstruct, DataSourceConstructProps } from './dataSourceConstruct';
import { EcrConstruct, EcrConstructProps } from './ecrRepositoryConstruct'
import { SageMakerConstruct } from './sageMakerConstruct';

export type InfrastractureStackProps = CodePipelineConstructPropsBase & StackProps & DataSourceConstructProps & EcrConstructProps;

export class InfrastractureStack extends Stack {
    constructor(scope: Construct, id: string, props: InfrastractureStackProps) {
        super(scope, id, props);

        const dataSource = new DataSourceConstruct(this, 'DataSource', {
            ...props,
        });

        const ecrRepos = new EcrConstruct(this, 'EcrRepository', {
            repositoryNameProcessImage: `${Stack.of(this).account}.dkr.ecr.${Stack.of(this).region}.amazonaws.com/${
                        props.projectName
                    }-processImage`,
            repositoryNameTrainImage: `${Stack.of(this).account}.dkr.ecr.${Stack.of(this).region}.amazonaws.com/${
                        props.projectName
                    }-trainImage`,
        });

        const sageMaker = new SageMakerConstruct(this, 'SageMakerConstruct', {
            dataBucket: dataSource.dataBucket,
        });

        const codePipeline = new CodePipelineConstruct(this, 'CodePipeline', {
            ...props,
            dataManifestBucket: dataSource.dataManifestBucket,
            processingImageUri: ecrRepos.ecrRepositoryProcess.repositoryName,
            trainingImageUri: ecrRepos.ecrRepositoryTrain.repositoryName,
            sageMakerArtifactBucket: sageMaker.sagemakerArtifactBucket,
            sageMakerExecutionRole: sageMaker.sagemakerExecutionRole,
            sageMakerForceExtractFeatures: props.sageMakerForceExtractFeatures,
        });

        new CfnOutput(this, 'CodePipelineOutput', {
            value: codePipeline.pipeline.pipelineName,
            exportName: 'FeMo-CodePipeline',
        });

        new CfnOutput(this, 'DataBucketOutput', {
            value: dataSource.dataBucket.bucketName,
            exportName: 'FeMo-DataBucket',
        });

        new CfnOutput(this, 'EcrExectionRoleOutput', {
            value: ecrRepos.ecrExecutionRole.roleArn,
            exportName: 'FeMo-EcrExecutionRole',
        }); 

        new CfnOutput(this, 'DataManifestBucketOutput', {
            value: dataSource.dataManifestBucket.bucketName,
            exportName: 'FeMo-DataManifestBucket',
        });

        new CfnOutput(this, 'SageMakerArtifactBucketOutput', {
            value: sageMaker.sagemakerArtifactBucket.bucketName,
            exportName: 'FeMo-SageMakerArtifactBucket',
        });

        new CfnOutput(this, 'SageMakerExecutionRoleOutput', {
            value: sageMaker.sagemakerExecutionRole.roleArn,
            exportName: 'FeMo-SageMakerExecutionRole',
        });
    }
}
