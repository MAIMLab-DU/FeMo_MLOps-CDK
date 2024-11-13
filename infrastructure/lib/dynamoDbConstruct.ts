// SPDX-License-Identifier: MIT-0
import { Construct } from 'constructs';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import { RemovalPolicy } from 'aws-cdk-lib';

export interface DynamoDBConstructProps {
    readonly tableName: string; // The name of the DynamoDB table to create
}

/**
 * The CDK Construct provisions DynamoDB related resources.
 */
export class DynamoDBConstruct extends Construct {
    readonly dynamoDBTable: dynamodb.Table;

    constructor(scope: Construct, id: string, props: DynamoDBConstructProps) {
        super(scope, id);

        // Create a DynamoDB table
        this.dynamoDBTable = new dynamodb.Table(this, 'DynamoDBTable', {
            tableName: props.tableName,
            partitionKey: { name: 'job_id', type: dynamodb.AttributeType.STRING }, // You can adjust the key schema as needed
            billingMode: dynamodb.BillingMode.PAY_PER_REQUEST, // Adjust based on your needs (PAY_PER_REQUEST or PROVISIONED)
        });
        this.dynamoDBTable.applyRemovalPolicy(RemovalPolicy.RETAIN);
    }
}
