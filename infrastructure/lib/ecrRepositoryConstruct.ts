// SPDX-License-Identifier: MIT-0
import { Construct } from 'constructs';
import * as ecr from 'aws-cdk-lib/aws-ecr';
import * as iam from 'aws-cdk-lib/aws-iam';
import { RemovalPolicy } from 'aws-cdk-lib';

export interface EcrConstructProps {
    readonly repoProcessImage: string;
    readonly repoTrainImage: string;
}

/**
 * The CDK Construct provisions the ECR repository and an IAM role with necessary permissions.
 */
export class EcrConstruct extends Construct {
    readonly ecrRepositoryProcess: ecr.Repository;
    readonly ecrRepositoryTrain: ecr.Repository;
    readonly ecrExecutionRole: iam.Role;

    constructor(scope: Construct, id: string, props: EcrConstructProps) {
        super(scope, id);

        // Create an ECR repository
        this.ecrRepositoryProcess = new ecr.Repository(this, 'EcrProcessRepository', {
            repositoryName: props.repoProcessImage,
        });
        this.ecrRepositoryProcess.applyRemovalPolicy(RemovalPolicy.RETAIN);

        this.ecrRepositoryTrain = new ecr.Repository(this, 'EcrTrainRepository', {
            repositoryName: props.repoTrainImage,
        });
        this.ecrRepositoryTrain.applyRemovalPolicy(RemovalPolicy.RETAIN);

        // Create an IAM role for ECR interactions
        this.ecrExecutionRole = new iam.Role(this, 'EcrExecutionRole', {
            assumedBy: new iam.ServicePrincipal('ecs-tasks.amazonaws.com'),
            managedPolicies: [iam.ManagedPolicy.fromAwsManagedPolicyName('AmazonEC2ContainerRegistryFullAccess')],
        });

        // Grant permission for this role to pull/push images in this repository
        this.ecrExecutionRole.addToPolicy(
            new iam.PolicyStatement({
                effect: iam.Effect.ALLOW,
                actions: [
                    'ecr:GetDownloadUrlForLayer',
                    'ecr:BatchGetImage',
                    'ecr:BatchCheckLayerAvailability',
                    'ecr:PutImage',
                ],
                resources: [
                    this.ecrRepositoryProcess.repositoryArn,
                    this.ecrRepositoryTrain.repositoryArn,
                ],
            })
        );
    }
}
