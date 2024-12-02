import os
import boto3
import datetime
import json

sagemaker = boto3.client('sagemaker', region_name=os.environ['AWS_REGION'])

def create_model(project_name, model_package_name, belt_type, dyanmodb_table_name, execution_role_arn):

    if model_package_name == "NotTrained":
        return {
            "PhysicalResourceId": model_package_name
        }

    now = datetime.datetime.now(datetime.timezone.utc)
    model_name = f"{project_name}-{belt_type}-{now.year}-{now.month}-{now.day}-{now.hour}-{now.minute}-{now.second}-{now.microsecond}"
    print(f"Creating model {model_name} for modelPackageName: {model_package_name} with role {execution_role_arn}")

    model_package = sagemaker.describe_model_package(
        ModelPackageName=model_package_name
    )
    additional_environment = {
        "DYNAMODB_TABLE": dyanmodb_table_name
    }

    containers = [
        {
            "Image": container["Image"],
            "ModelDataUrl": container.get("ModelDataUrl"),
            "Environment": {
                **container.get("Environment", {}),  # Merge existing env vars (if any)
                **additional_environment  # Add new custom env vars
            }
        }
        for container in model_package["InferenceSpecification"]["Containers"]
    ]

    sagemaker.create_model(
        ModelName=model_name,
        Containers=containers,
        ExecutionRoleArn=execution_role_arn
    )

    return {
        "PhysicalResourceId": model_name
    }

def delete_model(model_name):
    if model_name == "NotTrained":
        return {}
    print(f"Deleting model: {model_name}")
    sagemaker.delete_model(
        ModelName=model_name
    )
    print(f"Deleted model: {model_name}")
    return {}

def dispatch(event, request_type):
    props = event["ResourceProperties"]
    resource_id = event.get("PhysicalResourceId")

    if request_type in ["Create", "Update"]:
        return create_model(
            props["projectName"],
            props["modelPackageName"],
            props["beltType"],
            props["inferenceResultTable"],
            props["sagemakerExecutionRole"]
        )
    elif request_type == "Delete":
        return delete_model(resource_id)
    else:
        raise ValueError("Unsupported RequestType")

def lambda_handler(event, context):
    print(f"Event:\n{json.dumps(event, indent=2)}")
    try:
        request_type = event["RequestType"]
        data = dispatch(event, request_type)
        print("Response", data)
        return data
    except Exception as e:
        print("Error", e)
        raise e
