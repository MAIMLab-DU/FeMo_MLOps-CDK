// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
import * as path from 'path';
import { Construct } from 'constructs';
import { Duration } from 'aws-cdk-lib';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as events from 'aws-cdk-lib/aws-events';
import * as targets from 'aws-cdk-lib/aws-events-targets';
import * as lambda from 'aws-cdk-lib/aws-lambda';

/**
 * The CDK Construct provisions the data source buckets and related resources.
 */
export interface DataSourceConstructProps {
    existingDataBucketName?: string;
    triggerPeriod: number;
    minNumberOfFiles: number;
}

export class DataSourceConstruct extends Construct {
    readonly dataBucket: s3.IBucket; // Change type to IBucket to accommodate both existing and new buckets
    readonly dataManifestBucket: s3.Bucket;

    constructor(scope: Construct, id: string, props: DataSourceConstructProps) {
        super(scope, id);

        const dataSourceMonitorFunctionRole = new iam.Role(this, 'DataFunctionRole', {
            assumedBy: new iam.ServicePrincipal('lambda.amazonaws.com'),
            managedPolicies: [iam.ManagedPolicy.fromAwsManagedPolicyName('service-role/AWSLambdaBasicExecutionRole')],
        });

        // Check if an existing bucket is passed; otherwise, create a new bucket
        if (props.existingDataBucketName) {
            this.dataBucket = s3.Bucket.fromBucketName(this, 'DataBucket', props.existingDataBucketName);
        } else {
            this.dataBucket = new s3.Bucket(this, 'DataBucket', {
                blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
                encryption: s3.BucketEncryption.S3_MANAGED,
                enforceSSL: true,
                versioned: true,
                publicReadAccess: false,
            });
        }

        this.dataBucket.grantRead(dataSourceMonitorFunctionRole);

        // Create a new manifest bucket
        this.dataManifestBucket = new s3.Bucket(this, 'DataManifestBucket', {
            blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
            enforceSSL: true,
            versioned: true,
            publicReadAccess: false,
        });

        this.dataManifestBucket.grantWrite(dataSourceMonitorFunctionRole);

        // Set up SNS Topic for new data
        // Set up a CloudWatch Event Rule to trigger the Lambda function periodically
        const rule = new events.Rule(this, 'PeriodicTrigger', {
            schedule: events.Schedule.rate(Duration.days(props.triggerPeriod))
        });

        // Lambda function to monitor the bucket - using Python 3.10 runtime
        const dataMonitorFunction = new lambda.Function(this, 'DataSourceMonitorFunction', {
            runtime: lambda.Runtime.PYTHON_3_10, // Use Python 3.10 runtime
            handler: 'index.handler', // Python handler defined as 'filename.function_name'
            code: lambda.Code.fromAsset(path.join(__dirname, '../functions/dataSourceMonitor')), // Path to Python code
            timeout: Duration.minutes(5),
            role: dataSourceMonitorFunctionRole,
            environment: {
                DATA_BUCKET_NAME: this.dataBucket.bucketName,
                DATA_MANIFEST_BUCKET_NAME: this.dataManifestBucket.bucketName,
                MIN_DIFF: props.minNumberOfFiles.toString(),
            },
        });

        // Add the Lambda function as the target of the CloudWatch event
        rule.addTarget(new targets.LambdaFunction(dataMonitorFunction));

    }
}
