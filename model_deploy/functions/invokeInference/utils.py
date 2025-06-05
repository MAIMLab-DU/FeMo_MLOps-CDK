import json
from decimal import Decimal
from urllib.parse import urlparse
from boto3.dynamodb.conditions import Key


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


def upload_to_s3(s3_client, bucket_name, s3_key, data):
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
        s3_client.Object(bucket_name, s3_key).put(Body=json_data)
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