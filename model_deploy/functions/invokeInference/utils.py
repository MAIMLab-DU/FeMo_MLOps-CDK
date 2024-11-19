import boto3
import json
import os
from decimal import Decimal
from datetime import datetime
from boto3.dynamodb.conditions import Key, Attr
from typing import Optional
from dataclasses import dataclass, asdict

@dataclass
class RequestData:
    s3Key: str
    jobId: Optional[str] = None
    reEval: Optional[bool] = None

    def __post_init__(self):
        """
        Validate the fields after the dataclass is initialized.
        """
        # Validate field types
        if not isinstance(self.s3Key, str):
            raise ValueError(f"'s3Key' must be a string, got {type(self.s3Key).__name__}")
        
        if self.jobId is not None and not isinstance(self.jobId, str):
            raise ValueError(f"'jobId' must be a string, got {type(self.jobId).__name__}")
        
        if self.reEval is not None and not isinstance(self.reEval, bool):
            raise ValueError(f"'reEval' must be a boolean, got {type(self.reEval).__name__}")


# Initialize SageMaker runtime client
sagemaker_runtime = boto3.client('sagemaker-runtime')
# Retrieve endpoint name from environment variables
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
    

def query_table_with_keys(table, s3_key, job_id=None, limit=1):
    """
    Query the DynamoDB table based on the provided keys.

    Args:
        table: DynamoDB table object.
        s3_key: The s3Key to query.
        job_id: The jobId to query (optional).
        limit: Number of items to limit the query to.

    Returns:
        dict: Query response.
    """
    if job_id is not None:
        return table.query(
            KeyConditionExpression=Key('s3Key').eq(s3_key),
            FilterExpression=Attr('jobId').eq(job_id),
            ConsistentRead=True
        )
    return table.query(
        KeyConditionExpression=Key('s3Key').eq(s3_key),
        ScanIndexForward=False,
        Limit=limit
    )

def process_response(item, data, status_code=None):
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
        "InProgress": ("Inference job still in progress.", 204),
        "Completed": ("Inference job completed.", 200)
    }
    message, status_code = message_map.get(status, ("Inference job failed.", 400)) if not status_code else (message_map.get(status)[0], status_code)

    body = {
        "message": message,
        "s3Key": data.s3Key,
        "timeStamp": item.get('timeStamp'),
        "jobId": item.get('jobId'),
        "result": item.get('result')
    }
    body = convert_decimals(body)

    if status_code == 200:
        result = body['result']
        body['result'] = {
            "numBoutsPerHour": (result['numKicks'] * 60) / (result['totalFMDuration'] + result['totalNonFMDuration']) if result['numKicks'] > 0 else 0,
            "meanDurationFM_s": result['totalFMDuration'] * 60 / result['numKicks'] if result['numKicks'] > 0 else 0,
            "medianOnsetInterval_s": result['medianOnsetInterval_s'],
            "activeTimeFM_%": (result['totalFMDuration'] / (result['totalFMDuration'] + result['totalNonFMDuration'])) * 100 if result['numKicks'] > 0 else 0,
        }
    
    return {
        "statusCode": status_code,
        "body": json.dumps(body)
    }


def get_inference(id: str, data: dict):

    data: RequestData = RequestData(**data)
        
    try:
        response = query_table_with_keys(table, data.s3Key, job_id=data.jobId if data.jobId else None)
        if data.jobId and 'Item' in response:
            item = response['Item']
            return process_response(item, data)

        response = query_table_with_keys(table, data.s3Key)
        if 'Items' in response and response['Items']:
            item = response['Items'][0]
            if not data.reEval:
                return process_response(item, data)

        # Convert validated input to a dictionary
        payload = asdict(data)
        payload['jobId'] = id
        payload['timeStamp'] = datetime.now().isoformat()

        # Convert payload to JSON string
        payload_json = json.dumps(payload)

        # Invoke the SageMaker endpoint
        response = sagemaker_runtime.invoke_endpoint(
            EndpointName=endpoint_name,
            ContentType="application/json",
            Body=payload_json
        )
        
        # Read the response body
        result = json.loads(response['Body'].read().decode('utf-8'))
        
        return {
            "statusCode": 200,
            "body": json.dumps(result)
        }
    except ValueError as e:
        # Handle validation errors
        return {
            "statusCode": 400,
            "body": json.dumps({"error": str(e)})
        }
    except Exception as e:
        # Handle other exceptions
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }
