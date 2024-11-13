// SPDX-License-Identifier: MIT-0
import { Construct } from 'constructs';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import * as iam from 'aws-cdk-lib/aws-iam';

export interface DynamoDBConstructProps {
    readonly tableName: string; // The name of the DynamoDB table to create
}

/**
 * The CDK Construct provisions DynamoDB related resources.
 */
export class DynamoDBConstruct extends Construct {
    readonly dynamoDBTable: dynamodb.Table;
    readonly dynamoDBExecutionRole: iam.Role;

    constructor(scope: Construct, id: string, props: DynamoDBConstructProps) {
        super(scope, id);

        // Create a DynamoDB table
        this.dynamoDBTable = new dynamodb.Table(this, 'DynamoDBTable', {
            tableName: props.tableName,
            partitionKey: { name: 'job_id', type: dynamodb.AttributeType.STRING }, // You can adjust the key schema as needed
            billingMode: dynamodb.BillingMode.PAY_PER_REQUEST, // Adjust based on your needs (PAY_PER_REQUEST or PROVISIONED)
        });

        // Create an IAM role for DynamoDB interactions
        this.dynamoDBExecutionRole = new iam.Role(this, 'DynamoDBExecutionRole', {
            assumedBy: new iam.ServicePrincipal('lambda.amazonaws.com'), // Adjust the service principal based on your use case
            managedPolicies: [iam.ManagedPolicy.fromAwsManagedPolicyName('AmazonDynamoDBFullAccess')],
        });

        // Grant the role permissions to interact with the DynamoDB table
        this.dynamoDBExecutionRole.addToPolicy(
            new iam.PolicyStatement({
                effect: iam.Effect.ALLOW,
                actions: [
                    'dynamodb:GetItem',
                    'dynamodb:PutItem',
                    'dynamodb:Query',
                    'dynamodb:Scan',
                    'dynamodb:UpdateItem',
                ],
                resources: [this.dynamoDBTable.tableArn],
            })
        );
    }
}
