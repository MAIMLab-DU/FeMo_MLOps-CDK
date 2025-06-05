import json
import os
import boto3
from datetime import datetime
from typing import Dict, Any
from utils import (
    extract_s3_details
)

# Initialize AWS clients
dynamodb = boto3.resource('dynamodb')
s3_client = boto3.client('s3')

# Environment variables
table_name = os.environ.get('DYNAMODB_TABLE_NAME')
inference_results_bucket = os.environ.get('INFERENCE_RESULTS_BUCKET')

# Initialize DynamoDB table
table = dynamodb.Table(table_name) if table_name else None


def process_sns_notification(sns_message: Dict[str, Any], topic_arn: str, message_id: str) -> Dict[str, Any]:
    """
    Process SNS notification from SageMaker async inference completion.
    
    Args:
        sns_message: The SNS message containing inference result information
        topic_arn: The ARN of the SNS topic
        message_id: The SNS message ID
    
    Returns:
        dict: Processing result
    """
    print(f"Processing SNS message: {json.dumps(sns_message)}")
    
    try:
        # Determine if this is success or error notification
        is_success = sns_message.get("invocationStatus") == "Completed"
        
        # Extract key information from SNS message
        inference_id = sns_message.get("inferenceId")
        
        if is_success:
            return process_success_notification(sns_message, inference_id)
        else:
            return process_error_notification(sns_message, inference_id)
            
    except Exception as e:
        print(f"Error processing SNS notification: {e}")
        import traceback
        print(traceback.format_exc())
        return {
            "status": "error",
            "message": str(e),
            "message_id": message_id
        }


def process_success_notification(sns_message: Dict[str, Any], inference_id: str) -> Dict[str, Any]:
    """Process successful inference completion notification."""
    print(f"Processing successful inference completion for ID: {inference_id}")
    
    try:
        # Extract result information
        output_location = sns_message.get("responseParameters", {}).get("outputLocation")
        invocation_end_time = sns_message.get("eventTime")
        
        if not output_location:
            raise ValueError("No output location found in success notification")
        
        # Download and process results from S3
        result_data = download_inference_results(output_location)
        
        # Update DynamoDB with results
        update_result = update_inference_status(
            inference_id=inference_id,
            status="Completed",
            result_data=result_data,
            output_location=output_location,
            completion_time=invocation_end_time
        )
        
        return {
            "status": "Completed",
            "jobId": inference_id,
            "outputS3Url": output_location,
            "dynamodb_updated": update_result
        }
        
    except Exception as e:
        print(f"Error processing success notification: {e}")
        raise


def process_error_notification(sns_message: Dict[str, Any], inference_id: str) -> Dict[str, Any]:
    """Process failed inference notification."""
    print(f"Processing failed inference for ID: {inference_id}")
    
    try:
        # Extract error information
        failure_reason = sns_message.get("failureReason", "Unknown error")
        failure_location = sns_message.get("responseParameters", {}).get("failureLocation")
        invocation_end_time = sns_message.get("eventTime")
                
        # Update DynamoDB with error status
        update_result = update_inference_status(
            inference_id=inference_id,
            status="Failed",
            error_message=failure_reason,
            failure_location=failure_location,
            completion_time=invocation_end_time
        )
        
        return {
            "status": "Failed",
            "jobId": inference_id,
            "error": failure_reason,
            "failureS3Url": failure_location,
            "dynamodb_updated": update_result
        }
        
    except Exception as e:
        print(f"Error processing error notification: {e}")
        raise


def download_inference_results(s3_url: str) -> Dict[str, Any]:
    """Download inference results from S3."""
    try:
        # Parse S3 URL
        bucket_name, key = extract_s3_details(s3_url)
        
        print(f"Downloading results from s3://{bucket_name}/{key}")
        
        # Download file from S3
        response = s3_client.get_object(Bucket=bucket_name, Key=key)
        content = response['Body'].read().decode('utf-8')
        
        # Parse JSON content
        return json.loads(content)
        
    except Exception as e:
        print(f"Error downloading inference results: {e}")
        raise


def update_inference_status(inference_id: str, status: str, **kwargs) -> bool:
    """Update inference status in DynamoDB."""
    if not table:
        print("DynamoDB table not configured")
        return False
    
    try:
        # Find the item by jobId = inference_id
        scan_response = table.scan(
            FilterExpression="jobId = :id",
            ExpressionAttributeValues={":id": inference_id}
        )
        
        if not scan_response['Items']:
            print(f"No item found with jobId: {inference_id}")
            return False
        
        item = scan_response['Items'][0]
        s3_key = item['s3Key']
        request_time = item['timeStamp']
        
        # Prepare update attributes
        update_attributes = {
            "status": status,
            "completionTime": kwargs.get('completion_time', datetime.utcnow().isoformat() + 'Z')
        }
        
        if status == "Completed":
            update_attributes.update({
                "result": {
                    "outputS3Url": kwargs.get('output_location')
                }
            })
        elif status == "Failed":
            update_attributes.update({
                "result": {
                    "error": kwargs.get('error_message'),
                    "failureS3Url": kwargs.get('failure_location')
                }
            })
        
        # Update the item
        table.update_item(
            Key={'s3Key': s3_key, 'timeStamp': request_time},
            UpdateExpression="SET " + ", ".join([f"#{k} = :{k}" for k in update_attributes.keys()]),
            ExpressionAttributeNames={f"#{k}": k for k in update_attributes.keys()},
            ExpressionAttributeValues={f":{k}": v for k, v in update_attributes.items()}
        )
        
        print(f"Successfully updated inference status for {inference_id}")
        return True
        
    except Exception as e:
        print(f"Error updating DynamoDB: {e}")
        import traceback
        print(traceback.format_exc())
        return False