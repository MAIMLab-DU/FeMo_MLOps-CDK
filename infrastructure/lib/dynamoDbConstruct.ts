// SPDX-License-Identifier: MIT-0
import { Construct } from 'constructs';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import { RemovalPolicy } from 'aws-cdk-lib';

export interface DynamoDBConstructProps {
    readonly tableName: string;
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
            partitionKey: { name: 's3_key', type: dynamodb.AttributeType.STRING },
            sortKey: { name: 'timeStamp', type: dynamodb.AttributeType.STRING },
            billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
            encryption: dynamodb.TableEncryption.DEFAULT,
            pointInTimeRecovery: true,
        });
        this.dynamoDBTable.applyRemovalPolicy(RemovalPolicy.RETAIN);
    }
}
