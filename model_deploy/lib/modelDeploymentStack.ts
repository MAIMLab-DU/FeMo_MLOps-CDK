// SPDX-License-Identifier: MIT-0
import { Construct } from 'constructs';
import { Stack, StackProps, CfnParameter, CustomResource, Fn, CfnOutput, Duration, CfnCondition } from 'aws-cdk-lib';
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

        inferenceResultTable.addGlobalSecondaryIndex({
            indexName: 'JobIdIndex',
            partitionKey: { name: 'jobId', type: dynamodb.AttributeType.STRING },
            projectionType: dynamodb.ProjectionType.ALL,
        });

        const modelPackageNameBeltA = new CfnParameter(this, 'modelPackageNameBeltA', {
            type: 'String',
            default: 'NotTrained',
        });
        const modelPackageNameBeltB = new CfnParameter(this, 'modelPackageNameBeltB', {
            type: 'String',
            default: 'NotTrained',
        });
        const modelPackageNameBeltC = new CfnParameter(this, 'modelPackageNameBeltC', {
            type: 'String',
            default: 'NotTrained',
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

        inferenceModelFunctionRole.addToPolicy(
            iam.PolicyStatement.fromJson({
                Effect: 'Allow',
                Action: ['sagemaker:CreateModel', 'sagemaker:DeleteModel', 'sagemaker:DescribeModelPackage'],
                Resource: ['*'],
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
            runtime: lambda.Runtime.PYTHON_3_10,
            handler: 'lambda_function.lambda_handler',
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

        const endpoints: { [key: string]: sagemaker.CfnEndpoint | undefined } = {};

        const createEndpointForBelt = (belt: string, modelPackageName: CfnParameter) => {
            const customResource = new CustomResource(this, `InferenceModelBelt${belt}`, {
                serviceToken: inferenceModelCustomResourceProvider.serviceToken,
                properties: {
                    modelPackageName: modelPackageName.valueAsString,
                    sagemakerExecutionRole: executionRole.roleArn,
                    projectName: props.projectName,
                    beltType: belt,
                    inferenceResultTable: inferenceResultTable.tableName,
                },
            });

            const isModelTrained = new CfnCondition(this, `IsModelTrainedBelt${belt}`, {
                expression: Fn.conditionNot(Fn.conditionEquals(modelPackageName.valueAsString, 'NotTrained')),
            });

            const endpointConfig = new sagemaker.CfnEndpointConfig(this, `EndpointConfigBelt${belt}`, {
                productionVariants: [
                    {
                        initialInstanceCount: props.endpointInstanceCount || 1,
                        initialVariantWeight: 1.0,
                        instanceType: props.endpointInstanceType || 'ml.c5.xlarge',
                        modelName: customResource.ref,
                        variantName: 'AllTraffic',
                    },
                ],
            });
            endpointConfig.cfnOptions.condition = isModelTrained;

            const endpoint = new sagemaker.CfnEndpoint(this, `SageMakerModelEndpointBelt${belt}`, {
                endpointConfigName: endpointConfig.getAtt('EndpointConfigName').toString(),
            });
            endpoint.cfnOptions.condition = isModelTrained;

            const endpointArn = Fn.conditionIf(isModelTrained.logicalId, endpoint.ref, 'NotTrained').toString();
            const endpointName = Fn.conditionIf(
                isModelTrained.logicalId,
                endpoint.getAtt('EndpointName'),
                'NotTrained'
            ).toString();

            return { arn: endpointArn, name: endpointName, cfnOutput: customResource.ref };
        };

        // Create endpoints conditionally based on the modelPackageName parameters
        const endpointA = createEndpointForBelt('A', modelPackageNameBeltA);
        const endpointB = createEndpointForBelt('B', modelPackageNameBeltB);
        const endpointC = createEndpointForBelt('C', modelPackageNameBeltC);

        // Create the API construct with references to conditionally created endpoints
        const apiConstruct = new InferenceApiConstruct(this, 'InferenceAPIConstruct', {
            ipCIDRBlocks: props.ipPermitList,
            sageMakerEndpointArnBeltA: endpointA.arn,
            sageMakerEndpointArnBeltB: endpointB.arn,
            sageMakerEndpointArnBeltC: endpointC.arn,
            sageMakerEndpointNameBeltA: endpointA.name,
            sageMakerEndpointNameBeltB: endpointB.name,
            sageMakerEndpointNameBeltC: endpointC.name,
            inferenceResultTable: inferenceResultTable,
            customDomainName: props.customDomainName,
            acmCertificateArn: props.acmCertificateArn,
        });

        // Add dependencies to the API construct only for created endpoints
        if (endpoints['A']) {
            apiConstruct.node.addDependency(endpoints['A']);
        }
        if (endpoints['B']) {
            apiConstruct.node.addDependency(endpoints['B']);
        }
        if (endpoints['C']) {
            apiConstruct.node.addDependency(endpoints['C']);
        }

        new CfnOutput(this, 'InferenceApiUrlOutput', {
            value: apiConstruct.api.url,
            exportName: `${props.projectName}-InferenceApiUrl`,
        });
    }
}
