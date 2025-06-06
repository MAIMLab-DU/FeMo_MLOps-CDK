import os
import boto3
import json
import traceback
from datetime import datetime
from typing import Optional, Literal
from dataclasses import dataclass, asdict
from utils import (
    convert_decimals,
    upload_json_to_s3,
    extract_s3_details,
    update_item_in_dynamodb,
    query_table_with_keys,
    MODEL_PACKAGE_GROUP,
    MODEL_VERSION,
    GIT_COMMIT_ID,
    RESULTS_BUCKET,
    TABLE_NAME,
    SM_ENDPOINT_NAME,
    SUCCESS_TOPIC_ARN,
    FAILURE_TOPIC_ARN
)

@dataclass
class RequestData:
    s3Key: str

    def __post_init__(self):
        """
        Validate the fields after the dataclass is initialized.
        """
        # Validate field types
        if not isinstance(self.s3Key, str):
            raise ValueError(f"'s3Key' must be a string, got {type(self.s3Key).__name__}")


# Initialize SageMaker runtime client and SageMaker client
s3_client = boto3.client('s3')
sagemaker_runtime = boto3.client('sagemaker-runtime')
sagemaker_client = boto3.client('sagemaker')
dynamodb = boto3.resource('dynamodb', region_name=os.environ['AWS_REGION'])
table = dynamodb.Table(TABLE_NAME)


def process_response(item):
    """
    Process a DynamoDB item response and return formatted response.

    Args:
        item: The DynamoDB item to process.

    Returns:
        dict: Formatted HTTP response.
    """
    status_map = {
        "InProgress": 202,
        "Completed": 200,
        "Failed": 500,
        "Unknown": 400
    }
    
    body = {
        "jobId": item.get('jobId'),
        "s3Key": item.get('s3Key'),
        "requestTime": item.get('timeStamp'),
        "completionTime": item.get('completionTime'),
        "status": item.get('status', "Unknown"),
        "modelPackageGroup": item.get('modelPackageGroup'),
        "modelVersion": item.get('modelVersion'),
        "gitCommitIdMLCode": item.get('gitCommitIdMLCode'),
        "result": item.get('result')
    }
    body = convert_decimals(body)
    
    return {
        "statusCode": status_map.get(item.get('status', "Unknown"), 400),
        "body": json.dumps(body, indent=2, default=str)
    }


def get_endpoint_status():
    """
    Get SageMaker endpoint status and health information.
    Returns endpoint status, instance counts, and deployment tracking info.
    """
    try:
        # Describe the SageMaker endpoint
        response = sagemaker_client.describe_endpoint(EndpointName=SM_ENDPOINT_NAME)
        
        endpoint_status = response.get('EndpointStatus', 'Unknown')
        production_variants = response.get('ProductionVariants', [])
        
        # Calculate total instances and current capacity
        total_instances = 0
        current_capacity = 0
        
        for variant in production_variants:
            desired_instance_count = variant.get('DesiredInstanceCount', 0)
            current_instance_count = variant.get('CurrentInstanceCount', 0)            
            total_instances += desired_instance_count
            current_capacity += current_instance_count
        
        ready = endpoint_status == "InService" and current_capacity > 0
        # Determine warnings
        warnings = []
        if current_capacity == 0:
            warnings.append("No active instances. Cold start expected.")
        
        if endpoint_status != 'InService':
            warnings.append(f"Endpoint is not in service. Current status: {endpoint_status}")
        
        # Build response
        status_response = {
            "endpointName": SM_ENDPOINT_NAME,
            "endpointStatus": endpoint_status,
            "ready": ready,
            "currentActiveInstances": current_capacity,
            "totalDesiredInstances": total_instances,
            "modelPackageGroup": MODEL_PACKAGE_GROUP,
            "modelVersion": MODEL_VERSION,
            "gitCommitIdMLCode": GIT_COMMIT_ID,
            "successTopicArn": SUCCESS_TOPIC_ARN,
            "failureTopicArn": FAILURE_TOPIC_ARN,
            "warnings": warnings if warnings else None
        }
        
        return {
            "statusCode": 200,
            "body": status_response
        }
        
    except Exception as e:
        print(f"Error getting endpoint status: {e}")
        print(traceback.format_exc())
        return {
            "statusCode": 500,
            "body": {
                "error": "Failed to retrieve endpoint status",
                "message": str(e)
            }
        }


def get_inference(
    request_id: str,
    method: Literal['POST', 'GET'],
    body: Optional[dict] = None,
    query_params: Optional[dict] = None
):
    """
    Processes the inference logic based on the HTTP method.
    """
    if method == "POST":
        if not body:
            raise ValueError("POST request missing body.")

        data = RequestData(**body)
        try:
            # Validate InferenceId length (SageMaker limit: 63 chars)
            inference_id = request_id
            if len(inference_id) > 63:
                # Truncate but keep uniqueness
                inference_id = inference_id[:63]
                print(f"Warning: Truncated InferenceId from {len(request_id)} to 63 chars")

            # Query the DynamoDB table based on `s3Key`
            response = query_table_with_keys(table, data.s3Key)
            # Check if cached results exist
            if 'Items' in response and response['Items']:
                item = response['Items'][0]
                existing_version = f"{item.get('modelPackageGroup', 'Unknown')}/{item.get('modelVersion', 'Unknown')}"
                if existing_version == f"{MODEL_PACKAGE_GROUP}/{MODEL_VERSION}":
                    return process_response(item)

            # If no cached results, invoke SageMaker endpoint
            payload = asdict(data)
            payload['jobId'] = request_id  # Keep original request_id for DynamoDB
            payload['requestTime'] = datetime.utcnow().isoformat() + 'Z'            
            
            # Upload input data for Sagemaker request
            input_bucket, filename = extract_s3_details(data.s3Key)
            input_s3_key = f"input/{input_bucket}/{filename.removesuffix('.dat')}/{request_id}.json"
            input_s3_url = upload_json_to_s3(
                s3_client=s3_client,
                bucket_name=RESULTS_BUCKET,
                key=input_s3_key,
                data=payload
            )

            sm_response = sagemaker_runtime.invoke_endpoint_async(
                EndpointName=SM_ENDPOINT_NAME,
                InputLocation=input_s3_url,
                InvocationTimeoutSeconds=3600,
                InferenceId=inference_id,
                ContentType="application/json"
            )

            update_data = {
                "jobId": payload["jobId"],
                "status": "InProgress",
                "modelPackageGroup": MODEL_PACKAGE_GROUP,
                "modelVersion": MODEL_VERSION,
                "gitCommitIdMLCode": GIT_COMMIT_ID,
                "result": {
                        "resultS3Url": input_s3_url.replace("/input/", "/result/", 1)
                }
            }            
            update_item_in_dynamodb(
                table, 
                data.s3Key, 
                payload['requestTime'],
                update_data
            )

            response_body = {
                **update_data,
                "s3Key": payload["s3Key"],
                "requestTime": payload["requestTime"]
            }
            
            return {                
                "statusCode": sm_response["ResponseMetadata"]["HTTPStatusCode"],
                "body": response_body
            }

        except Exception as e:
            print(f"Error invoking SageMaker endpoint: {e}\t{traceback.format_exc()}")
            return {
                "statusCode": 500,
                "body": {"message": str(e)}
            }

    elif method == "GET":
        if not query_params or "jobId" not in query_params:
            return {
                "statusCode": 400,
                "body": {"message": "Missing required query parameter: jobId"}
            }

        job_id = query_params["jobId"]
        try:
            response = query_table_with_keys(table, None, job_id=job_id)
            if "Items" in response and response["Items"]:
                item = response["Items"][0]
                return process_response(item)

            return {
                "statusCode": 404,
                "body": {"message": f"Job ID {job_id} not found."}
            }

        except Exception as e:
            print(f"Error getting response for Job ID {job_id}: {e}\t{traceback.format_exc()}")
            return {
                "statusCode": 500,
                "body": {"message": str(e)}
            }

    else:
        return {
            "statusCode": 405,
            "body": {"message": "Method Not Allowed"}
        }
