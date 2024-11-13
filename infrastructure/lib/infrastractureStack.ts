// SPDX-License-Identifier: MIT-0
import { Stack, StackProps, CfnOutput } from 'aws-cdk-lib';
import { Construct } from 'constructs';
import { CodePipelineConstruct, CodePipelineConstructPropsBase } from './codePipelineConstruct';
import { DataSourceConstruct, DataSourceConstructProps } from './dataSourceConstruct';
import { DynamoDBConstruct } from './dynamoDbConstruct';
import { EcrConstruct, EcrConstructProps } from './ecrRepositoryConstruct';
import { SageMakerConstruct } from './sageMakerConstruct';

export type InfrastractureStackProps = CodePipelineConstructPropsBase &
    StackProps &
    DataSourceConstructProps &
    EcrConstructProps;

export class InfrastractureStack extends Stack {
    constructor(scope: Construct, id: string, props: InfrastractureStackProps) {
        super(scope, id, props);

        const dataSource = new DataSourceConstruct(this, 'DataSource', {
            ...props,
        });

        const dynamodb = new DynamoDBConstruct(this, 'DynamoDbConstruct', {
            tableName: `${this.stackName}-inferenceJobResults`,
        });
        const ecrRepos = new EcrConstruct(this, 'EcrRepositoryConstruct', {
            repositoryName: `${props.projectName.toLowerCase()}/${props.repositoryName.toLowerCase()}`,
        });

        const sageMaker = new SageMakerConstruct(this, 'SageMakerConstruct', {
            dataBucket: dataSource.dataBucket,
            dynamoDbTable: dynamodb.dynamoDBTable,
        });

        const codePipeline = new CodePipelineConstruct(this, 'CodePipeline', {
            ...props,
            dataManifestBucket: dataSource.dataManifestBucket,
            dynamoDbTable: dynamodb.dynamoDBTable,
            ecrRepo: ecrRepos.ecrRepository,
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

        new CfnOutput(this, 'DynamoDbOutput', {
            value: dynamodb.dynamoDBTable.tableArn,
            exportName: 'FeMo-DynamoDbInferenceResults',
        });

        new CfnOutput(this, 'EcrRepositoryOutput', {
            value: ecrRepos.ecrRepository.repositoryArn,
            exportName: 'FeMo-EcrRepository',
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
