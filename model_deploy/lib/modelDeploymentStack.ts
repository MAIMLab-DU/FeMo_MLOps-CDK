// SPDX-License-Identifier: MIT-0
import { Construct } from 'constructs';
import { Stack, StackProps, CfnParameter, CfnCondition, Fn, CustomResource, CfnOutput, Duration } from 'aws-cdk-lib';
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
}

export class ModelDeploymentStack extends Stack {
    constructor(scope: Construct, id: string, props: ModelDeploymentStackProps) {
        super(scope, id, {
            ...props,
            env: {
                account: process.env.CDK_DEFAULT_ACCOUNT, // Use the default AWS account
                region: process.env.CDK_DEFAULT_REGION, // Use the default AWS region
            },
        });

        const inferenceResultTable = new dynamodb.Table(this, 'InferenceResultTable', {
            partitionKey: { name: 's3Key', type: dynamodb.AttributeType.STRING },
            sortKey: { name: 'timeStamp', type: dynamodb.AttributeType.STRING },
            billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
            encryption: dynamodb.TableEncryption.DEFAULT,
            pointInTimeRecovery: true,
        });

        // Add a Global Secondary Index for jobId
        inferenceResultTable.addGlobalSecondaryIndex({
            indexName: 'JobIdIndex', // Name of the GSI
            partitionKey: { name: 'jobId', type: dynamodb.AttributeType.STRING }, // GSI partition key
            projectionType: dynamodb.ProjectionType.ALL, // Include all attributes in the index
        });

        const modelPackageNameBeltA = new CfnParameter(this, 'modelPackageNameBeltA', {
            type: 'String',
            default: 'None',
        });
        const modelPackageNameBeltB = new CfnParameter(this, 'modelPackageNameBeltB', {
            type: 'String',
            default: 'None',
        });
        const modelPackageNameBeltC = new CfnParameter(this, 'modelPackageNameBeltC', {
            type: 'String',
            default: 'None',
        });

        // Add a condition for each modelPackageName
        const modelPackageNameBeltACondition = new CfnCondition(this, 'ModelPackageNameBeltACondition', {
            expression: Fn.conditionNot(Fn.conditionEquals(modelPackageNameBeltA.valueAsString, 'None')),
        });
        const modelPackageNameBeltBCondition = new CfnCondition(this, 'ModelPackageNameBeltBCondition', {
            expression: Fn.conditionNot(Fn.conditionEquals(modelPackageNameBeltB.valueAsString, 'None')),
        });
        const modelPackageNameBeltCCondition = new CfnCondition(this, 'ModelPackageNameBeltCCondition', {
            expression: Fn.conditionNot(Fn.conditionEquals(modelPackageNameBeltC.valueAsString, 'None')),
        });

        const executionRole = new iam.Role(this, 'SageMakerModelExecutionRole', {
            assumedBy: new iam.ServicePrincipal('sagemaker.amazonaws.com'),
            managedPolicies: [iam.ManagedPolicy.fromAwsManagedPolicyName('AmazonSageMakerFullAccess')],
        });

        executionRole.addToPolicy(
            iam.PolicyStatement.fromJson({
                Effect: 'Allow',
                Action: ['s3:GetObject', 's3:ListBucket'],
                Resource: ['*'],
            })
        );

        executionRole.addToPolicy(
            iam.PolicyStatement.fromJson({
                Effect: 'Allow',
                Action: ['dynamodb:PutItem', 'dynamodb:UpdateItem', 'dynamodb:GetItem', 'dynamodb:Query*'],
                Resource: [inferenceResultTable.tableArn, `${inferenceResultTable.tableArn}/*`],
            })
        );

        const inferenceModelFunctionRole = new iam.Role(this, 'InferenceModelFunctionRole', {
            assumedBy: new iam.ServicePrincipal('lambda.amazonaws.com'),
            managedPolicies: [iam.ManagedPolicy.fromAwsManagedPolicyName('service-role/AWSLambdaBasicExecutionRole')],
        });

        const resources: string[] = [
            `arn:aws:sagemaker:${this.region}:${this.account}:model/${props.projectName}*`, // Base resource pattern
        ];

        if (modelPackageNameBeltA.valueAsString !== 'None') {
            resources.push(modelPackageNameBeltA.valueAsString);
        }
        if (modelPackageNameBeltB.valueAsString !== 'None') {
            resources.push(modelPackageNameBeltB.valueAsString);
        }
        if (modelPackageNameBeltC.valueAsString !== 'None') {
            resources.push(modelPackageNameBeltC.valueAsString);
        }

        inferenceModelFunctionRole.addToPolicy(
            iam.PolicyStatement.fromJson({
                Effect: 'Allow',
                Action: ['sagemaker:CreateModel', 'sagemaker:DeleteModel', 'sagemaker:DescribeModelPackage'],
                Resource: resources,
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
            timeout: Duration.minutes(10),
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

        const inferenceModelCustomResourceBeltA = new CustomResource(this, 'InferenceModelCustomResourceBeltA', {
            serviceToken: inferenceModelCustomResourceProvider.serviceToken,
            properties: {
                modelPackageName: modelPackageNameBeltA.valueAsString,
                sagemakerExecutionRole: executionRole.roleArn,
                projectName: props.projectName,
                inferenceResultTable: inferenceResultTable.tableName,
            },
        });
        const inferenceModelCustomResourceBeltB = new CustomResource(this, 'InferenceModelCustomResourceBeltB', {
            serviceToken: inferenceModelCustomResourceProvider.serviceToken,
            properties: {
                modelPackageName: modelPackageNameBeltB.valueAsString,
                sagemakerExecutionRole: executionRole.roleArn,
                projectName: props.projectName,
                inferenceResultTable: inferenceResultTable.tableName,
            },
        });
        const inferenceModelCustomResourceBeltC = new CustomResource(this, 'InferenceModelCustomResourceBeltC', {
            serviceToken: inferenceModelCustomResourceProvider.serviceToken,
            properties: {
                modelPackageName: modelPackageNameBeltC.valueAsString,
                sagemakerExecutionRole: executionRole.roleArn,
                projectName: props.projectName,
                inferenceResultTable: inferenceResultTable.tableName,
            },
        });

        inferenceModelCustomResourceBeltA.node.addDependency(executionRole);
        inferenceModelCustomResourceBeltB.node.addDependency(executionRole);
        inferenceModelCustomResourceBeltC.node.addDependency(executionRole);

        const endpointConfigBeltA = modelPackageNameBeltACondition.node.defaultChild
            ? new sagemaker.CfnEndpointConfig(this, 'SageMakerModelEndpointConfigBeltA', {
                  productionVariants: [
                      {
                          initialInstanceCount: props.endpointInstanceCount || 1,
                          initialVariantWeight: 1.0,
                          instanceType: props.endpointInstanceType || 'ml.c5.xlarge',
                          modelName: inferenceModelCustomResourceBeltA.ref,
                          variantName: 'AllTraffic',
                      },
                  ],
              })
            : undefined;

        const endpointConfigBeltB = modelPackageNameBeltBCondition.node.defaultChild
            ? new sagemaker.CfnEndpointConfig(this, 'SageMakerModelEndpointConfigBeltB', {
                  productionVariants: [
                      {
                          initialInstanceCount: props.endpointInstanceCount || 1,
                          initialVariantWeight: 1.0,
                          instanceType: props.endpointInstanceType || 'ml.c5.xlarge',
                          modelName: inferenceModelCustomResourceBeltB.ref,
                          variantName: 'AllTraffic',
                      },
                  ],
              })
            : undefined;

        const endpointConfigBeltC = modelPackageNameBeltCCondition.node.defaultChild
            ? new sagemaker.CfnEndpointConfig(this, 'SageMakerModelEndpointConfigBeltC', {
                  productionVariants: [
                      {
                          initialInstanceCount: props.endpointInstanceCount || 1,
                          initialVariantWeight: 1.0,
                          instanceType: props.endpointInstanceType || 'ml.c5.xlarge',
                          modelName: inferenceModelCustomResourceBeltC.ref,
                          variantName: 'AllTraffic',
                      },
                  ],
              })
            : undefined;

        if (endpointConfigBeltA) {
            endpointConfigBeltA.node.addDependency(inferenceModelCustomResourceBeltA);
        }
        if (endpointConfigBeltB) {
            endpointConfigBeltB.node.addDependency(inferenceModelCustomResourceBeltB);
        }
        if (endpointConfigBeltC) {
            endpointConfigBeltC.node.addDependency(inferenceModelCustomResourceBeltC);
        }

        const endpointBeltA = endpointConfigBeltA
            ? new sagemaker.CfnEndpoint(this, 'SageMakerModelEndpointBeltA', {
                  endpointConfigName: endpointConfigBeltA.getAtt('EndpointConfigName').toString(),
              })
            : undefined;

        const endpointBeltB = endpointConfigBeltB
            ? new sagemaker.CfnEndpoint(this, 'SageMakerModelEndpointBeltB', {
                  endpointConfigName: endpointConfigBeltB.getAtt('EndpointConfigName').toString(),
              })
            : undefined;

        const endpointBeltC = endpointConfigBeltC
            ? new sagemaker.CfnEndpoint(this, 'SageMakerModelEndpointBeltC', {
                  endpointConfigName: endpointConfigBeltC.getAtt('EndpointConfigName').toString(),
              })
            : undefined;

        if (endpointBeltA && endpointConfigBeltA) {
            endpointBeltA.node.addDependency(endpointConfigBeltA);
        }
        if (endpointBeltB && endpointConfigBeltB) {
            endpointBeltB.node.addDependency(endpointConfigBeltB);
        }
        if (endpointBeltC && endpointConfigBeltC) {
            endpointBeltC.node.addDependency(endpointConfigBeltC);
        }

        const apiConstruct = new InferenceApiConstruct(this, 'InferenceAPIConstruct', {
            ipCIDRBlocks: props.ipPermitList,
            sageMakerEndpointArnBeltA: endpointBeltA ? endpointBeltA.ref : 'None',
            sageMakerEndpointArnBeltB: endpointBeltB ? endpointBeltB.ref : 'None',
            sageMakerEndpointArnBeltC: endpointBeltC ? endpointBeltC.ref : 'None',
            sageMakerEndpointNameBeltA: endpointBeltA ? endpointBeltA.getAtt('EndpointName').toString() : 'None',
            sageMakerEndpointNameBeltB: endpointBeltB ? endpointBeltB.getAtt('EndpointName').toString() : 'None',
            sageMakerEndpointNameBeltC: endpointBeltC ? endpointBeltC.getAtt('EndpointName').toString() : 'None',
            inferenceResultTable: inferenceResultTable,
            customDomainName: props.customDomainName,
            acmCertificateArn: props.acmCertificateArn,
        });

        if (endpointBeltA) {
            apiConstruct.node.addDependency(endpointBeltA);
        }
        if (endpointBeltB) {
            apiConstruct.node.addDependency(endpointBeltB);
        }
        if (endpointBeltC) {
            apiConstruct.node.addDependency(endpointBeltC);
        }

        new CfnOutput(this, 'InferenceApiUrlOutput', {
            value: apiConstruct.api.url,
            exportName: `${props.projectName}-InferenceApiUrl`,
        });
    }
}
