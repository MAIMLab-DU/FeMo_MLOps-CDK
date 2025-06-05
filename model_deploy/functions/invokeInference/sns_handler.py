import os
import json
import boto3
from datetime import datetime
from typing import Dict, Any
from utils import (
    extract_s3_details,
    upload_json_to_s3,
    download_json_from_s3,
    query_table_with_keys,
    update_item_in_dynamodb,
    TABLE_NAME,
    RESULTS_BUCKET,
    MODEL_PACKAGE_GROUP,
    MODEL_VERSION,
    GIT_COMMIT_ID
)

# Initialize DynamoDB and S3
s3_client = boto3.client('s3')
dynamodb = boto3.resource('dynamodb', region_name=os.environ['AWS_REGION'])
table = dynamodb.Table(TABLE_NAME)


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
        input_location: str = sns_message.get("requestParameters", {}).get("inputLocation")
        output_location: str = sns_message.get("responseParameters", {}).get("outputLocation")
        invocation_end_time = sns_message.get("eventTime")
        
        if not output_location:
            raise ValueError("No output location found in success notification")
        
        # Download and process output from S3
        output_bucket_name, output_s3_key = extract_s3_details(output_location)
        print(f"Downloading output from S3 bucket: {output_bucket_name}, key: {output_s3_key}")
        result_data = download_json_from_s3(
            s3_client=s3_client,
            bucket_name=output_bucket_name,
            key=output_s3_key
        )

        result_data["modelPackageGroup"] = MODEL_PACKAGE_GROUP
        result_data["modelVersion"] = MODEL_VERSION
        result_data["gitCommitIdMLCode"] = GIT_COMMIT_ID
        result_data["completionTime"] = invocation_end_time

        _, input_s3_key = extract_s3_details(input_location)
        result_s3_key = input_s3_key.replace("/input/", "/result/", 1)
        print(f"Uploading result to S3 bucket: {RESULTS_BUCKET}, key: {result_s3_key}")
        result_s3_url = upload_json_to_s3(
            s3_client=s3_client,
            bucket_name=RESULTS_BUCKET,
            key=result_s3_key,
            data=result_data
        )
        
        # Update DynamoDB with results
        print(f"Updating DynamoDB for Completed inference ID: {inference_id}")
        update_result = update_inference_status(
            inference_id=inference_id,
            status="Completed",
            result_location=result_s3_url,
            completion_time=invocation_end_time
        )
        
        return {
            "status": "Completed",
            "jobId": inference_id,
            "resultS3Url": result_s3_url,
            "dynamodbUpdated": update_result
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
        print(f"Updating DynamoDB for Failed inference ID: {inference_id}")
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


def update_inference_status(inference_id: str, status: str, **kwargs) -> bool:
    """Update inference status in DynamoDB."""
    if not table:
        print("DynamoDB table not configured")
        return False
    
    try:
        # Find the item by jobId = inference_id
        response = query_table_with_keys(table, None, job_id=inference_id)
        if not response.get('Items'):
            print(f"No item found with jobId: {inference_id}")
            return False
        
        item = response['Items'][0]        
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
                    "resultS3Url": kwargs.get('result_location'),
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
        update_item_in_dynamodb(
            table=table,
            s3_key=s3_key,
            time_stamp=request_time,
            update_data=update_attributes
        )
        
        print(f"Successfully updated inference status for {inference_id}")
        return True
        
    except Exception as e:
        print(f"Error updating DynamoDB: {e}")
        import traceback
        print(traceback.format_exc())
        return False