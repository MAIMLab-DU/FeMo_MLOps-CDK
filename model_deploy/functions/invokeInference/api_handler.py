import boto3
import json
import os
import traceback
from decimal import Decimal
from datetime import datetime
from urllib.parse import urlparse
from boto3.dynamodb.conditions import Key
from typing import Optional, Literal
from dataclasses import dataclass, asdict

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
s3 = boto3.resource('s3')
inference_results_bucket = os.getenv('INFERENCE_RESULTS_BUCKET')
success_topic_arn = os.getenv('ASYNC_SUCCESS_TOPIC_ARN')
failure_topic_arn = os.getenv('ASYNC_ERROR_TOPIC_ARN')



def convert_decimals(obj):
    if isinstance(obj, list):
        return [convert_decimals(i) for i in obj]
    elif isinstance(obj, dict):
        return {k: convert_decimals(v) for k, v in obj.items()}
    elif isinstance(obj, Decimal):
        return float(obj)  # Or int(obj) if appropriate
    else:
        return obj


def extract_s3_details(s3_path: str):
    """Extracts the bucket name and filename from an S3 path."""
    # Parse the S3 path
    parsed_url = urlparse(s3_path)
    bucket_name = parsed_url.netloc
    filename = parsed_url.path.lstrip('/')

    # Extract the bucket name and the filename
    if bucket_name == '':
        raise ValueError(f"Invalid S3 path: {s3_path}")
    
    return bucket_name, filename


def upload_to_s3(bucket_name, s3_key, data):
    """
    Upload data to an S3 bucket.

    Args:
        bucket_name (str): The name of the S3 bucket.
        s3_key (str): The S3 key where the data will be stored.
        data (dict): The data to upload.

    Returns:
        str: S3 URL of the uploaded object.
    """
    try:
        # Convert data to JSON string
        json_data = json.dumps(data, indent=2, default=str)
        s3.Object(bucket_name, s3_key).put(Body=json_data)
        s3_url = f"s3://{bucket_name}/{s3_key}"
        return s3_url
    except Exception as e:
        print(f"Error uploading to S3: {e}")
        raise


def update_item_in_dynamodb(table, s3_key, time_stamp, update_data):
    """
    Update an item in a DynamoDB table with specific s3Key and timeStamp.

    Args:
        table_name (str): The name of the DynamoDB table.
        s3_key (str): The s3Key value to identify the item.
        time_stamp (str): The timeStamp value to identify the item.
        update_data (dict): The attributes and their new values to update.

    Returns:
        dict: Response from the update_item operation.
    """

    # Build the update expression
    update_expression = "SET " + ", ".join(f"#{k} = :{k}" for k in update_data.keys())
    expression_attribute_names = {f"#{k}": k for k in update_data.keys()}
    expression_attribute_values = {f":{k}": v for k, v in update_data.items()}

    try:
        # Update the item
        response = table.update_item(
            Key={
                "s3Key": s3_key,
                "timeStamp": time_stamp
            },
            UpdateExpression=update_expression,
            ExpressionAttributeNames=expression_attribute_names,
            ExpressionAttributeValues=expression_attribute_values,
            ReturnValues="UPDATED_NEW"
        )
        return response
    except Exception as e:
        print(f"Error updating item: {e}")
        raise


def query_table_with_keys(table, s3_key=None, job_id=None, limit=1):
    """
    Query the DynamoDB table based on the provided keys.

    Args:
        table: DynamoDB table object.
        s3_key: The s3Key to query (optional).
        job_id: The jobId to query (optional).
        limit: Number of items to limit the query to.

    Returns:
        dict: Query response.
    """
    if s3_key:
        # Query using the primary key (partition key)
        return table.query(
            KeyConditionExpression=Key('s3Key').eq(s3_key),
            ConsistentRead=True,
            Limit=limit,
            ScanIndexForward=False  # Query in descending order (latest to oldest)
        )
    elif job_id:
        # Query using the GSI (jobId)
        return table.query(
            IndexName='JobIdIndex',  # Name of the GSI
            KeyConditionExpression=Key('jobId').eq(job_id),
            Limit=limit
        )
    else:
        raise ValueError("Either 's3Key' or 'jobId' must be provided.")

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
