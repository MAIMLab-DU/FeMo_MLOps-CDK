// SPDX-License-Identifier: MIT-0
import { Construct } from 'constructs';
import * as ecr from 'aws-cdk-lib/aws-ecr';
import { RemovalPolicy } from 'aws-cdk-lib';

/**
 * The CDK Construct provisions the ECR repository and an IAM role with necessary permissions.
 */
export class EcrConstruct extends Construct {
    readonly ecrRepository: ecr.Repository;

    constructor(scope: Construct, id: string) {
        super(scope, id);

        // Create an ECR repository
        this.ecrRepository = new ecr.Repository(this, 'EcrRepository', {});
        this.ecrRepository.applyRemovalPolicy(RemovalPolicy.RETAIN);
    }
}
