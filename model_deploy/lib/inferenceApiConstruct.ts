// SPDX-License-Identifier: MIT-0
import { Construct } from 'constructs';
import { Duration, Token } from 'aws-cdk-lib';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as apigateway from 'aws-cdk-lib/aws-apigateway';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as sns from 'aws-cdk-lib/aws-sns';
import * as snsSubscriptions from 'aws-cdk-lib/aws-sns-subscriptions';
import * as route53 from 'aws-cdk-lib/aws-route53';
import * as route53Targets from 'aws-cdk-lib/aws-route53-targets';
import * as certificatemanager from 'aws-cdk-lib/aws-certificatemanager';
import * as path from 'path';

export interface InferencApiConstructProps {
    readonly ipCIDRBlocks: string[];
    readonly modelPackageName: string;
    readonly sageMakeEndpointArn: string;
    readonly sageMakerEndpointName: string;
    readonly inferenceResultTable: dynamodb.ITable;
    readonly inferenceResultsBucket: s3.IBucket;
    readonly customDomainName?: string; // Optional custom domain name
    readonly acmCertificateArn?: string; // Optional ACM certificate ARN
    readonly asyncSuccessTopic: sns.ITopic; // SNS topic for successful async inference
    readonly asyncErrorTopic: sns.ITopic; // SNS topic for failed async inference
}

/**
 * The CDK Construct provisions the backend api resources.
 */
export class InferenceApiConstruct extends Construct {
    readonly api: apigateway.RestApi;

    constructor(scope: Construct, id: string, props: InferencApiConstructProps) {
        super(scope, id);

        const validationSchema: apigateway.JsonSchema = {
            type: apigateway.JsonSchemaType.OBJECT,
            properties: {
                s3Key: {
                    type: apigateway.JsonSchemaType.STRING,
                    pattern: '^s3://.*\\.dat$', // Regex for s3Key validation
                },
            },
            required: ['s3Key'], // Specify required properties
            additionalProperties: false,
        };

        const apigatewayPolicy = new iam.PolicyDocument({
            statements: [
                new iam.PolicyStatement({
                    effect: iam.Effect.ALLOW,
                    actions: ['execute-api:Invoke'],
                    resources: ['execute-api:/*/*/*'],
                    principals: [new iam.AnyPrincipal()],
                }),
                new iam.PolicyStatement({
                    effect: iam.Effect.DENY,
                    actions: ['execute-api:Invoke'],
                    resources: ['execute-api:/*/*/*'],
                    principals: [new iam.AnyPrincipal()],
                    conditions: {
                        NotIpAddress: {
                            'aws:SourceIp': props.ipCIDRBlocks,
                        },
                    },
                }),
            ],
        });

        this.api = new apigateway.RestApi(this, 'InferenceAPI', {
            defaultCorsPreflightOptions: {
                allowOrigins: apigateway.Cors.ALL_ORIGINS,
                allowMethods: apigateway.Cors.ALL_METHODS,
            },
            policy: apigatewayPolicy,
        });

        const model = this.api.addModel('InferenceRequestModel', {
            modelName: 'InferenceRequestModel',
            schema: validationSchema,
            contentType: 'application/json',
        });

        const inferenceApiFunctionRole = new iam.Role(this, 'InferenceApiFunctionRole', {
            assumedBy: new iam.ServicePrincipal('lambda.amazonaws.com'),
            managedPolicies: [iam.ManagedPolicy.fromAwsManagedPolicyName('service-role/AWSLambdaBasicExecutionRole')],
        });

        inferenceApiFunctionRole.addToPolicy(
            iam.PolicyStatement.fromJson({
                Effect: 'Allow',
                Action: [
                    'dynamodb:UpdateItem',
                    'dynamodb:PutItem',
                    'dynamodb:GetItem',
                    'dynamodb:Query',
                    'dynamodb:Scan',
                ],
                Resource: [props.inferenceResultTable.tableArn, `${props.inferenceResultTable.tableArn}/*`],
            })
        );

        inferenceApiFunctionRole.addToPolicy(
            iam.PolicyStatement.fromJson({
                Effect: 'Allow',
                Action: ['s3:GetObject', 's3:PutObject', 's3:DeleteObject', 's3:ListBucket'],
                Resource: [props.inferenceResultsBucket.bucketArn, `${props.inferenceResultsBucket.bucketArn}/*`],
            })
        );
        props.inferenceResultsBucket.grantReadWrite(inferenceApiFunctionRole);

        inferenceApiFunctionRole.addToPolicy(
            iam.PolicyStatement.fromJson({
                Effect: 'Allow',
                Action: ['sagemaker:InvokeEndpoint'],
                Resource: [props.sageMakeEndpointArn],
            })
        );

        const inferenceApiFunction = new lambda.Function(this, 'InferenceApiFunction', {
            runtime: lambda.Runtime.PYTHON_3_10, // Use Python 3.10 runtime
            handler: 'lambda_function.lambda_handler', // Python handler defined as 'filename.function_name'
            code: lambda.Code.fromAsset(path.join(__dirname, '../functions/invokeInference'), {
                exclude: ['.venv', '.ruff_cache', '.pytest_cache', '*.pyc', '__pycache__'],
            }),
            timeout: Duration.minutes(1),
            role: inferenceApiFunctionRole,
            environment: {
                MODEL_PACKAGE_NAME: props.modelPackageName,
                SAGEMAKER_ENDPOINT_NAME: props.sageMakerEndpointName,
                DYNAMODB_TABLE_NAME: props.inferenceResultTable.tableName,
                INFERENCE_RESULTS_BUCKET: props.inferenceResultsBucket.bucketName,
                ASYNC_SUCCESS_TOPIC_ARN: props.asyncSuccessTopic.topicArn,
                ASYNC_ERROR_TOPIC_ARN: props.asyncErrorTopic.topicArn,
            },
        });

        // Subscribe the Lambda function to SNS topics for async inference notifications
        props.asyncSuccessTopic.addSubscription(new snsSubscriptions.LambdaSubscription(inferenceApiFunction));
        props.asyncErrorTopic.addSubscription(new snsSubscriptions.LambdaSubscription(inferenceApiFunction));

        const inferenceIntegration = new apigateway.LambdaIntegration(inferenceApiFunction);

        const inferenceEndpoint = this.api.root.addResource('inference');

        // POST Method with Request Body Validation
        inferenceEndpoint.addMethod('POST', inferenceIntegration, {
            requestModels: {
                'application/json': model,
            },
            requestValidatorOptions: {
                validateRequestBody: true,
            },
            methodResponses: [
                {
                    statusCode: '200',
                    responseModels: {
                        'application/json': apigateway.Model.EMPTY_MODEL,
                    },
                },
                {
                    statusCode: '202',
                    responseModels: {
                        'application/json': apigateway.Model.EMPTY_MODEL,
                    },
                },
                {
                    statusCode: '400',
                    responseModels: {
                        'application/json': apigateway.Model.ERROR_MODEL,
                    },
                },
                {
                    statusCode: '405',
                    responseModels: {
                        'application/json': apigateway.Model.ERROR_MODEL,
                    },
                },
                {
                    statusCode: '500',
                    responseModels: {
                        'application/json': apigateway.Model.ERROR_MODEL,
                    },
                },
            ],
        });

        // GET Method with Query Parameter Validation
        inferenceEndpoint.addMethod('GET', inferenceIntegration, {
            requestParameters: {
                'method.request.querystring.jobId': true, // Require 'jobId' query parameter
            },
            requestValidator: new apigateway.RequestValidator(this, 'QueryValidator', {
                restApi: this.api,
                validateRequestParameters: true, // Enable request parameter validation
            }),
            methodResponses: [
                {
                    statusCode: '200',
                    responseModels: {
                        'application/json': apigateway.Model.EMPTY_MODEL,
                    },
                },
                {
                    statusCode: '400',
                    responseModels: {
                        'application/json': apigateway.Model.ERROR_MODEL,
                    },
                },
            ],
        });

        this.api.latestDeployment?.addToLogicalId(Token.asAny(apigatewayPolicy));

        this.api.addUsagePlan('InferenceApiUsagePlan', {
            name: 'InferenceApiUsagePlan',
            apiStages: [{ api: this.api, stage: this.api.deploymentStage }],
            throttle: { burstLimit: 500, rateLimit: 1000 },
            quota: { limit: 1000000, period: apigateway.Period.MONTH },
        });

        // Optional Custom Domain Configuration
        if (props.customDomainName && props.acmCertificateArn) {
            const certificate = certificatemanager.Certificate.fromCertificateArn(
                this,
                'ACMCertificate',
                props.acmCertificateArn
            );

            this.api.addDomainName('InferenceApiCustomDomain', {
                domainName: props.customDomainName,
                certificate: certificate,
            });

            // Lookup an existing Route 53 Hosted Zone for the custom domain
            const hostedZone = route53.HostedZone.fromLookup(this, 'HostedZone', {
                domainName: props.customDomainName.split('.').slice(1).join('.'), // Extract parent domain (e.g., "example.com")
            });

            // Create a Route 53 ARecord pointing to the API Gateway domain name
            new route53.ARecord(this, 'ApiGatewayAliasRecord', {
                zone: hostedZone,
                target: route53.RecordTarget.fromAlias(new route53Targets.ApiGateway(this.api)),
                recordName: props.customDomainName,
            });
        }
    }
}
