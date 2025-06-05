// SPDX-License-Identifier: MIT-0
import { Construct } from 'constructs';
import { Stack, StackProps, CfnParameter, CustomResource, CfnOutput, Duration, RemovalPolicy } from 'aws-cdk-lib';
import { InferenceApiConstruct } from './inferenceApiConstruct';
import * as path from 'path';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import * as sagemaker from 'aws-cdk-lib/aws-sagemaker';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as customResource from 'aws-cdk-lib/custom-resources';
import * as logs from 'aws-cdk-lib/aws-logs';
import * as sns from 'aws-cdk-lib/aws-sns';
import * as applicationautoscaling from 'aws-cdk-lib/aws-applicationautoscaling';
import * as cloudwatch from 'aws-cdk-lib/aws-cloudwatch';

export interface ModelDeploymentStackProps extends StackProps {
    modelEndpointExportNamePrefix: string;
    endpointInstanceType?: string;
    endpointInstanceCount?: number;
    ipPermitList: string[];
    projectName: string;
    customDomainName?: string;
    acmCertificateArn?: string;
    inferenceResultsTableArn?: string;
    inferenceResultsBucketName?: string;
    // Auto scaling configuration from projectConfig
    autoScaling?: {
        enabled?: boolean;
        minCapacity?: number;
        maxCapacity?: number;
        backlogSizePerInstanceTarget?: number;
        scaleOutCooldown?: number;
        scaleInCooldown?: number;
        maxConcurrentInvocationsPerInstance?: number;
    };
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
        let inferenceResultsBucket: s3.IBucket;

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
        const gitCommitId = new CfnParameter(this, 'gitCommitId', {
            type: 'String',
            default: 'Unknown',
        });

        // Check if an existing bucket is passed; otherwise, create a new bucket
        if (props.inferenceResultsBucketName) {
            inferenceResultsBucket = s3.Bucket.fromBucketName(
                this,
                'InferenceResultsBucket',
                props.inferenceResultsBucketName
            );
        } else {
            inferenceResultsBucket = new s3.Bucket(this, 'InferenceResultsBucket', {
                blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
                encryption: s3.BucketEncryption.S3_MANAGED,
                enforceSSL: true,
                versioned: true,
                publicReadAccess: false,
            });
        }

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
        executionRole.addToPolicy(
            new iam.PolicyStatement({
                effect: iam.Effect.ALLOW,
                actions: ['s3:GetObject', 's3:PutObject', 's3:DeleteObject', 's3:ListBucket'],
                resources: [inferenceResultsBucket.bucketArn, `${inferenceResultsBucket.bucketArn}/*`],
            })
        );

        executionRole.applyRemovalPolicy(RemovalPolicy.DESTROY);

        // Create SNS topics for async inference notifications
        const asyncSuccessTopic = new sns.Topic(this, 'AsyncInferenceSuccessTopic', {
            topicName: `${props.projectName}-async-inference-success`,
        });

        const asyncErrorTopic = new sns.Topic(this, 'AsyncInferenceErrorTopic', {
            topicName: `${props.projectName}-async-inference-error`,
        });

        // Grant SageMaker permissions for async inference
        inferenceResultsBucket.grantReadWrite(executionRole);
        asyncSuccessTopic.grantPublish(executionRole);
        asyncErrorTopic.grantPublish(executionRole);

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
            },
        });

        inferenceModelCustomResource.applyRemovalPolicy(RemovalPolicy.DESTROY);
        inferenceModelCustomResource.node.addDependency(executionRole);

        const endpointConfig = new sagemaker.CfnEndpointConfig(this, 'SageMakerModelEndpointConfig', {
            productionVariants: [
                {
                    initialInstanceCount: props.endpointInstanceCount || 1,
                    initialVariantWeight: 1.0,
                    instanceType: props.endpointInstanceType || 'ml.m5.2xlarge',
                    modelName: inferenceModelCustomResource.ref,
                    variantName: 'AllTraffic',
                },
            ],
            asyncInferenceConfig: {
                outputConfig: {
                    s3OutputPath: `s3://${inferenceResultsBucket.bucketName}/output/`,
                    s3FailurePath: `s3://${inferenceResultsBucket.bucketName}/failure/`,
                    notificationConfig: {
                        successTopic: asyncSuccessTopic.topicArn,
                        errorTopic: asyncErrorTopic.topicArn,
                    },
                },
                clientConfig: {
                    maxConcurrentInvocationsPerInstance: props.autoScaling?.maxConcurrentInvocationsPerInstance || 2,
                },
            },
        });

        endpointConfig.node.addDependency(inferenceModelCustomResource);

        const endpoint = new sagemaker.CfnEndpoint(this, 'SageMakerModelEndpoint', {
            endpointConfigName: endpointConfig.getAtt('EndpointConfigName').toString(),
        });

        endpoint.node.addDependency(endpointConfig);

        // Add auto scaling for the endpoint if enabled
        if (props.autoScaling?.enabled !== false) {
            const autoScalingConfig = props.autoScaling || {};

            const scalingTarget = new applicationautoscaling.ScalableTarget(this, 'SageMakerEndpointScalingTarget', {
                serviceNamespace: applicationautoscaling.ServiceNamespace.SAGEMAKER,
                resourceId: `endpoint/${endpoint.getAtt('EndpointName').toString()}/variant/AllTraffic`,
                scalableDimension: 'sagemaker:variant:DesiredInstanceCount',
                minCapacity: autoScalingConfig.minCapacity || 0, // default scale down to zero instance
                maxCapacity: autoScalingConfig.maxCapacity || 2,
            });

            scalingTarget.node.addDependency(endpoint);

            // 2. Scale based on approximate backlog size per instance (for async inference)
            const backlogMetric = new cloudwatch.Metric({
                namespace: 'AWS/SageMaker',
                metricName: 'ApproximateBacklogSizePerInstance',
                dimensionsMap: {
                    EndpointName: endpoint.getAtt('EndpointName').toString(),
                },
                statistic: cloudwatch.Statistic.AVERAGE,
                period: Duration.minutes(1),
            });

            new applicationautoscaling.TargetTrackingScalingPolicy(this, 'BacklogScalingPolicy', {
                scalingTarget: scalingTarget,
                targetValue: autoScalingConfig.backlogSizePerInstanceTarget || 0.5,
                customMetric: backlogMetric,
                scaleInCooldown: Duration.seconds(autoScalingConfig.scaleInCooldown || 600), // 10 minutes
                scaleOutCooldown: Duration.seconds(autoScalingConfig.scaleOutCooldown || 60), // 1 minute
            });
        }

        const apiConstruct = new InferenceApiConstruct(this, 'InferenceAPIConstruct', {
            ipCIDRBlocks: props.ipPermitList,
            modelPackageName: modelPackageName.valueAsString,
            gitCommitId: gitCommitId.valueAsString,
            sageMakeEndpointArn: endpoint.ref,
            sageMakerEndpointName: endpoint.getAtt('EndpointName').toString(),
            inferenceResultTable: inferenceResultTable,
            inferenceResultsBucket: inferenceResultsBucket,
            customDomainName: props.customDomainName,
            acmCertificateArn: props.acmCertificateArn,
            asyncSuccessTopic: asyncSuccessTopic,
            asyncErrorTopic: asyncErrorTopic,
        });

        apiConstruct.node.addDependency(endpoint);

        new CfnOutput(this, 'InferenceApiUrlOutput', {
            value: apiConstruct.api.url,
            exportName: `${props.projectName}-InferenceApiUrl`,
        });
    }
}
