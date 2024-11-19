// SPDX-License-Identifier: MIT-0
import { Construct } from 'constructs';
import { Fn, Stack, StackProps, CfnParameter, CustomResource, CfnOutput, Duration } from 'aws-cdk-lib';
import { InferenceApiConstruct } from './inferenceApiConstruct';
import * as path from 'path';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import * as sagemaker from 'aws-cdk-lib/aws-sagemaker';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as customResource from 'aws-cdk-lib/custom-resources';
import * as logs from 'aws-cdk-lib/aws-logs';

export interface ModelDeploymentStackProps extends StackProps {
    modelEndpointExportNamePrefix: string;
    endpointInstanceType?: string;
    endpointInstanceCount?: number;
    ipPermitList: string[];
    projectName: string;
}

export class ModelDeploymentStack extends Stack {
    constructor(scope: Construct, id: string, props: ModelDeploymentStackProps) {
        super(scope, id, props);

        const sagemakerArtifactBucketArn = Fn.importValue(`${props.projectName}-SagemakerArtifactBucket`);

        const inferenceResultTable = new dynamodb.Table(this, 'InferenceResultTable', {
            partitionKey: { name: 's3Key', type: dynamodb.AttributeType.STRING },
            sortKey: { name: 'timeStamp', type: dynamodb.AttributeType.STRING },
            billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
            encryption: dynamodb.TableEncryption.DEFAULT,
            pointInTimeRecovery: true,
        });

        const modelPackageName = new CfnParameter(this, 'modelPackageName', {
            type: 'String',
        });

        const executionRole = new iam.Role(this, 'SageMakerModelExecutionRole', {
            assumedBy: new iam.ServicePrincipal('sagemaker.amazonaws.com'),
            managedPolicies: [iam.ManagedPolicy.fromAwsManagedPolicyName('AmazonSageMakerFullAccess')],
        });

        executionRole.addToPolicy(
            iam.PolicyStatement.fromJson({
                Effect: 'Allow',
                Action: ['s3:GetObject', 's3:ListBucket'],
                Resource: [sagemakerArtifactBucketArn, `${sagemakerArtifactBucketArn}/*`],
            })
        );

        executionRole.addToPolicy(
            iam.PolicyStatement.fromJson({
                Effect: 'Allow',
                Action: ['dynamodb:PutItem', 'dynamodb:UpdateItem', 'dynamodb:GetItem'],
                Resource: [inferenceResultTable.tableArn, `${inferenceResultTable.tableArn}/*`],
            })
        );

        const inferenceModelFunctionRole = new iam.Role(this, 'InferenceModelFunctionRole', {
            assumedBy: new iam.ServicePrincipal('lambda.amazonaws.com'),
            managedPolicies: [iam.ManagedPolicy.fromAwsManagedPolicyName('service-role/AWSLambdaBasicExecutionRole')],
        });

        inferenceModelFunctionRole.addToPolicy(
            iam.PolicyStatement.fromJson({
                Effect: 'Allow',
                Action: ['sagemaker:CreateModel', 'sagemaker:DeleteModel', 'sagemaker:DescribeModelPackage'],
                Resource: [
                    `arn:aws:sagemaker:${this.region}:${this.account}:model/${props.projectName}*`,
                    modelPackageName.valueAsString,
                ],
            })
        );

        inferenceModelFunctionRole.addToPolicy(
            iam.PolicyStatement.fromJson({
                Effect: 'Allow',
                Action: ['iam:PassRole'],
                Resource: [executionRole.roleArn],
            })
        );

        const inferenceModelFunction = new lambda.Function(this, 'InferenceModelFunction', {
            runtime: lambda.Runtime.PYTHON_3_10, // Use Python 3.10 runtime
            handler: 'lambda_function.lambda_handler', // Python handler defined as 'filename.function_name'
            code: lambda.Code.fromAsset(path.join(__dirname, '../customResources/inferenceModel'), {
                exclude: ['.venv', '.ruff_cache', '.pytest_cache', '*.pyc', '__pycache__'],
            }),
            timeout: Duration.minutes(2),
            role: inferenceModelFunctionRole,
        });

        const inferenceModelCustomResourceProvider = new customResource.Provider(
            this,
            'InferenceModelCustomResourceProvider',
            {
                onEventHandler: inferenceModelFunction,
                logRetention: logs.RetentionDays.ONE_DAY,
            }
        );

        const inferenceModelCustomResource = new CustomResource(this, 'InferenceModelCustomResource', {
            serviceToken: inferenceModelCustomResourceProvider.serviceToken,
            properties: {
                modelPackageName: modelPackageName.valueAsString,
                sagemakerExecutionRole: executionRole.roleArn,
                projectName: props.projectName,
                inferenceResultTable: inferenceResultTable.tableName,
            },
        });

        inferenceModelCustomResource.node.addDependency(executionRole);

        const endpointConfig = new sagemaker.CfnEndpointConfig(this, 'SageMakerModelEndpointConfig', {
            productionVariants: [
                {
                    initialInstanceCount: props.endpointInstanceCount || 1,
                    initialVariantWeight: 1.0,
                    instanceType: props.endpointInstanceType || 'ml.c5.xlarge',
                    modelName: inferenceModelCustomResource.ref,
                    variantName: 'AllTraffic',
                },
            ],
        });

        endpointConfig.node.addDependency(inferenceModelCustomResource);

        const endpoint = new sagemaker.CfnEndpoint(this, 'SageMakerModelEndpoint', {
            endpointConfigName: endpointConfig.getAtt('EndpointConfigName').toString(),
        });

        endpoint.node.addDependency(endpointConfig);

        const apiConstruct = new InferenceApiConstruct(this, 'WebsiteAPIConstruct', {
            ipCIDRBlocks: props.ipPermitList,
            sageMakeEndpointArn: endpoint.ref,
            sageMakerEndpointName: endpoint.getAtt('EndpointName').toString(),
            inferenceResultTable: inferenceResultTable,
        });

        apiConstruct.node.addDependency(endpoint);

        new CfnOutput(this, 'InferenceApiEndpointOutput', {
            value: apiConstruct.api.url,
            exportName: `${props.projectName}-InferenceApiEndpoint`,
        });
    }
}
