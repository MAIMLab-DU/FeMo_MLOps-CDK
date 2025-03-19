import boto3
import json
import os
import traceback
from decimal import Decimal
from datetime import datetime
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
dynamodb = boto3.resource('dynamodb', region_name=os.environ['AWS_REGION'])
table = dynamodb.Table(os.getenv('DYNAMODB_TABLE_NAME'))


def convert_decimals(obj):
    if isinstance(obj, list):
        return [convert_decimals(i) for i in obj]
    elif isinstance(obj, dict):
        return {k: convert_decimals(v) for k, v in obj.items()}
    elif isinstance(obj, Decimal):
        return float(obj)  # Or int(obj) if appropriate
    else:
        return obj


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

def process_response(item, status_code=None):
    """
    Process a DynamoDB item response and return formatted response.

    Args:
        item: The DynamoDB item to process.
        data: Input data for additional processing.
        status_code: HTTP status code (optional).

    Returns:
        dict: Formatted HTTP response.
    """
    status = item.get('status')
    message_map = {
        "InProgress": ("Inference job still in progress.", 202),
        "Completed": ("Inference job completed.", 200)
    }
    message, status_code = message_map.get(status, ("Inference job failed.", 400)) if not status_code else (message_map.get(status)[0], status_code)
    
    body = {
        "message": message,
        "modelPackageGroup": item.get('modelPackageGroup'),
        "modelVersion": item.get('modelVersion'),
        "s3Key": item.get('s3Key'),
        "timeStamp": item.get('timeStamp'),
        "jobId": item.get('jobId'),
        "result": item.get('result')
    }
    body = convert_decimals(body)

    def process_result(data: dict) -> dict:
        """Compute hiccup metrics for given data dictionary."""
        if data.get('numKicks', 0) == 0:
            return {
                "numBoutsPerHour": 0,
                "meanDurationFM_s": 0,
                "medianOnsetInterval_s": data.get("medianOnsetInterval_s", 0),
                "activeTimeFM_%": 0,
            }
        
        total_duration = data["totalFMDuration"] + data["totalNonFMDuration"]
        
        return {
            "numBoutsPerHour": (data["numKicks"] * 60) / total_duration,
            "meanDurationFM_s": (data["totalFMDuration"] * 60) / data["numKicks"],
            "medianOnsetInterval_s": data["medianOnsetInterval_s"],
            "activeTimeFM_%": (data["totalFMDuration"] / total_duration) * 100,
        }

    if status_code == 200:
        result = body["result"]
    
        # Process pre_hiccup and post_hiccup if available
        if result.get("pre_hiccup", None) is not None:
            result["pre_hiccup"] = process_result(result.get("pre_hiccup"))
        if result.get("post_hiccup", None) is not None:
            result["post_hiccup"] = process_result(result.get("post_hiccup"))

        # If neither exist, process the main result
        if result.get("pre_hiccup", None) is None and result.get("post_hiccup", None) is None:
            result = process_result(result)

        body["result"] = result
    
    return {
        "statusCode": status_code,
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

    Args:
        request_id: AWS request ID for tracing.
        method: HTTP method (POST or GET).
        body: Parsed JSON body for POST requests.
        query_params: Query parameters for GET requests.

    Returns:
        dict: Response with statusCode and body.
    """
    if method == "POST":
        if not body:
            raise ValueError("POST request missing body.")

        data = RequestData(**body)
        try:
            # Query the DynamoDB table based on `s3Key`
            response = query_table_with_keys(table, data.s3Key)

            # Check if cached results exist
            if 'Items' in response and response['Items']:
                item = response['Items'][0]
                existing_version = item.get('modelVersion', None)
                if existing_version == model_version:
                    # Re-use cached result if model version matches
                    return process_response(item)

            # If no cached results, invoke SageMaker endpoint
            payload = asdict(data)
            payload['jobId'] = request_id
            payload['timeStamp'] = datetime.now().isoformat()

            payload_json = json.dumps(payload)
            sm_response = sagemaker_runtime.invoke_endpoint(
                EndpointName=endpoint_name,
                ContentType="application/json",
                Body=payload_json
            )
            update_item_in_dynamodb(table, data.s3Key, payload['timeStamp'],
                                    {"modelVersion": model_version, "modelPackageGroup": model_package_group})
            result = json.loads(sm_response['Body'].read().decode('utf-8'))
            return {
                "statusCode": 200,
                "body": result
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
            print(f"Error invoking SageMaker endpoint: {e}\t{traceback.format_exc()}")
            return {
                "statusCode": 500,
                "body": {"message": str(e)}
            }

    else:
        return {
            "statusCode": 405,
            "body": {"message": "Method Not Allowed"}
        }
