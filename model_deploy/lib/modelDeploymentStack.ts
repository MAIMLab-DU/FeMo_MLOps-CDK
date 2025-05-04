// SPDX-License-Identifier: MIT-0
import { Construct } from 'constructs';
import { Stack, StackProps, CfnParameter, CustomResource, CfnOutput, Duration, RemovalPolicy } from 'aws-cdk-lib';
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
    customDomainName?: string;
    acmCertificateArn?: string;
    inferenceResultsTableArn?: string;
}

export class ModelDeploymentStack extends Stack {
    constructor(scope: Construct, id: string, props: ModelDeploymentStackProps) {
        super(scope, id, {
            ...props,
            env: {
                account: process.env.CDK_DEFAULT_ACCOUNT,
                region: process.env.CDK_DEFAULT_REGION,
            },
        });

        let inferenceResultTable: dynamodb.ITable;

        if (props.inferenceResultsTableArn) {
            inferenceResultTable = dynamodb.Table.fromTableArn(
                this,
                'InferenceResultTable',
                props.inferenceResultsTableArn
            );
        } else {
            const newTable = new dynamodb.Table(this, 'InferenceResultTable', {
                partitionKey: { name: 's3Key', type: dynamodb.AttributeType.STRING },
                sortKey: { name: 'timeStamp', type: dynamodb.AttributeType.STRING },
                billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
                encryption: dynamodb.TableEncryption.DEFAULT,
                pointInTimeRecovery: true,
                removalPolicy: RemovalPolicy.RETAIN,
            });

            newTable.addGlobalSecondaryIndex({
                indexName: 'JobIdIndex',
                partitionKey: { name: 'jobId', type: dynamodb.AttributeType.STRING },
                projectionType: dynamodb.ProjectionType.ALL,
            });

            inferenceResultTable = newTable;
        }

        const modelPackageName = new CfnParameter(this, 'modelPackageName', {
            type: 'String',
            default: 'NotTrained',
        });

        const executionRole = new iam.Role(this, 'SageMakerModelExecutionRole', {
            assumedBy: new iam.ServicePrincipal('sagemaker.amazonaws.com'),
            managedPolicies: [iam.ManagedPolicy.fromAwsManagedPolicyName('AmazonSageMakerFullAccess')],
        });

        executionRole.addToPolicy(
            new iam.PolicyStatement({
                effect: iam.Effect.ALLOW,
                actions: ['s3:GetObject', 's3:ListBucket'],
                resources: ['*'],
            })
        );

        if (props.inferenceResultsTableArn) {
            // Use wildcard or construct policy manually for imported tables
            executionRole.addToPolicy(
                new iam.PolicyStatement({
                    effect: iam.Effect.ALLOW,
                    actions: [
                        'dynamodb:PutItem',
                        'dynamodb:UpdateItem',
                        'dynamodb:GetItem',
                        'dynamodb:Query',
                        'dynamodb:Query*',
                    ],
                    resources: [props.inferenceResultsTableArn, `${props.inferenceResultsTableArn}/*`],
                })
            );
        } else {
            // Use direct references if table is owned by this stack
            executionRole.addToPolicy(
                new iam.PolicyStatement({
                    effect: iam.Effect.ALLOW,
                    actions: [
                        'dynamodb:PutItem',
                        'dynamodb:UpdateItem',
                        'dynamodb:GetItem',
                        'dynamodb:Query',
                        'dynamodb:Query*',
                    ],
                    resources: [
                        (inferenceResultTable as dynamodb.Table).tableArn,
                        `${(inferenceResultTable as dynamodb.Table).tableArn}/*`,
                    ],
                })
            );
        }

        executionRole.applyRemovalPolicy(RemovalPolicy.DESTROY);

        const inferenceModelFunctionRole = new iam.Role(this, 'InferenceModelFunctionRole', {
            assumedBy: new iam.ServicePrincipal('lambda.amazonaws.com'),
            managedPolicies: [iam.ManagedPolicy.fromAwsManagedPolicyName('service-role/AWSLambdaBasicExecutionRole')],
        });

        inferenceModelFunctionRole.addToPolicy(
            new iam.PolicyStatement({
                effect: iam.Effect.ALLOW,
                actions: ['sagemaker:CreateModel', 'sagemaker:DeleteModel', 'sagemaker:DescribeModelPackage'],
                resources: ['*'],
            })
        );

        inferenceModelFunctionRole.addToPolicy(
            new iam.PolicyStatement({
                effect: iam.Effect.ALLOW,
                actions: ['iam:PassRole'],
                resources: [executionRole.roleArn],
            })
        );

        inferenceModelFunctionRole.applyRemovalPolicy(RemovalPolicy.DESTROY);

        const inferenceModelFunction = new lambda.Function(this, 'InferenceModelFunction', {
            runtime: lambda.Runtime.PYTHON_3_10,
            handler: 'lambda_function.lambda_handler',
            code: lambda.Code.fromAsset(path.join(__dirname, '../customResources/inferenceModel'), {
                exclude: ['.venv', '.ruff_cache', '.pytest_cache', '*.pyc', '__pycache__'],
            }),
            timeout: Duration.minutes(10),
            role: inferenceModelFunctionRole,
        });

        inferenceModelFunction.applyRemovalPolicy(RemovalPolicy.DESTROY);

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

        inferenceModelCustomResource.applyRemovalPolicy(RemovalPolicy.DESTROY);
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

        const apiConstruct = new InferenceApiConstruct(this, 'InferenceAPIConstruct', {
            ipCIDRBlocks: props.ipPermitList,
            modelPackageName: modelPackageName.valueAsString,
            sageMakeEndpointArn: endpoint.ref,
            sageMakerEndpointName: endpoint.getAtt('EndpointName').toString(),
            inferenceResultTable: inferenceResultTable,
            customDomainName: props.customDomainName,
            acmCertificateArn: props.acmCertificateArn,
        });

        apiConstruct.node.addDependency(endpoint);

        new CfnOutput(this, 'InferenceApiUrlOutput', {
            value: apiConstruct.api.url,
            exportName: `${props.projectName}-InferenceApiUrl`,
        });
    }
}
