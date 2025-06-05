import boto3
import json
import os
import traceback
from datetime import datetime
from typing import Optional, Literal
from dataclasses import dataclass, asdict
from utils import (
    upload_to_s3,
    extract_s3_details,
    update_item_in_dynamodb,
    query_table_with_keys
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


# Initialize SageMaker runtime client
sagemaker_runtime = boto3.client('sagemaker-runtime')
# Retrieve endpoint name from environment variables
model_package_group = os.getenv('MODEL_PACKAGE_NAME').split('/')[-2]
model_version = f"Version {os.getenv('MODEL_PACKAGE_NAME').split('/')[-1]}"
endpoint_name = os.getenv('SAGEMAKER_ENDPOINT_NAME')
# Initialize DynamoDB resource and table
dynamodb = boto3.resource('dynamodb', region_name=os.environ['AWS_REGION'])
table = dynamodb.Table(os.getenv('DYNAMODB_TABLE_NAME'))
# Initialize S3 resource and bucket name
s3_client = boto3.resource('s3')
inference_results_bucket = os.getenv('INFERENCE_RESULTS_BUCKET')
success_topic_arn = os.getenv('ASYNC_SUCCESS_TOPIC_ARN')
failure_topic_arn = os.getenv('ASYNC_ERROR_TOPIC_ARN')


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
        "result": item.get('result')
    }
    
    return {
        "statusCode": status_map.get(item.get('status', "Unknown")),
        "body": json.dumps(body, indent=2)
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
                existing_version = item.get('modelVersion', None)
                if existing_version == model_version:
                    return process_response(item)

            # If no cached results, invoke SageMaker endpoint
            payload = asdict(data)
            payload['jobId'] = request_id  # Keep original request_id for DynamoDB
            payload['requestTime'] = datetime.utcnow().isoformat() + 'Z'            
            
            input_bucket, filename = extract_s3_details(data.s3Key)
            request_s3_url = upload_to_s3(
                s3_client,
                inference_results_bucket, 
                f"input/{input_bucket}/{filename.removesuffix('.dat')}/{request_id}.json", 
                payload
            )

            sm_response = sagemaker_runtime.invoke_endpoint_async(
                EndpointName=endpoint_name,
                InputLocation=request_s3_url,
                InvocationTimeoutSeconds=3600,
                InferenceId=inference_id,
                ContentType="application/json"
            )

            update_data = {
                "jobId": payload["jobId"],
                "status": "InProgress",
                "modelPackageGroup": model_package_group,
                "modelVersion": model_version,
                "result": {
                        "outputS3Url": sm_response["OutputLocation"], 
                        "failureS3Url": sm_response["FailureLocation"]
                }
            }            
            update_item_in_dynamodb(
                table, 
                data.s3Key, 
                payload['requestTime'],
                update_data
            )

            response_body = {
                "s3Key": payload["s3Key"],
                "requestTime": payload["requestTime"],
                "successTopicArn": success_topic_arn,
                "failureTopicArn": failure_topic_arn,
                **update_data
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
