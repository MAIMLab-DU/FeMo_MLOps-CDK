import json
from utils import (
    MODEL_PACKAGE_NAME,
    GIT_COMMIT_ID,
    TABLE_NAME,
    RESULTS_BUCKET,
    SUCCESS_TOPIC_ARN,
    FAILURE_TOPIC_ARN,
    SM_ENDPOINT_NAME
)

if not MODEL_PACKAGE_NAME or '/' not in MODEL_PACKAGE_NAME:
    raise ValueError("Environment variable 'MODEL_PACKAGE_NAME' must be set and contain at least one '/'.")
if not GIT_COMMIT_ID:
    raise ValueError("Environment variable 'GIT_COMMIT_ID' must be set.")
if not TABLE_NAME:
    raise ValueError("Environment variable 'DYNAMODB_TABLE_NAME' must be set.")
if not RESULTS_BUCKET:
    raise ValueError("Environment variable 'INFERENCE_RESULTS_BUCKET' must be set.")
if not SUCCESS_TOPIC_ARN:
    raise ValueError("Environment variable 'ASYNC_SUCCESS_TOPIC_ARN' must be set.")
if not FAILURE_TOPIC_ARN:
    raise ValueError("Environment variable 'ASYNC_ERROR_TOPIC_ARN' must be set.")
if not SM_ENDPOINT_NAME:
    raise ValueError("Environment variable 'SAGEMAKER_ENDPOINT_NAME' must be set.")

# CORS headers
cors_header = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "OPTIONS,POST,GET,PUT,DELETE",
}


def lambda_handler(event, context):
    """
    AWS Lambda handler function that supports both API Gateway and SNS triggers.

    Args:
        event: The event object containing request data.
        context: The context object with Lambda invocation information.

    Returns:
        dict: The response object with statusCode, headers, and body.
    """
    print("Event: ", json.dumps(event))

    try:
        # Detect event source
        if is_sns_event(event):
            return handle_sns_event(event, context)
        elif is_api_gateway_event(event):
            return handle_api_gateway_event(event, context)
        else:
            print(f"Unknown event source: {event}")
            return {
                "statusCode": 400,
                "headers": cors_header,
                "body": json.dumps({"message": "Unsupported event source"}),
            }

    except Exception as e:
        print("Error: ", e)
        import traceback
        print(traceback.format_exc())
        message = str(e)
        return {
            "statusCode": 500,
            "headers": cors_header,
            "body": json.dumps({"message": message}),
        }


def is_sns_event(event):
    """Check if the event is from SNS."""
    return "Records" in event and len(event["Records"]) > 0 and event["Records"][0].get("EventSource") == "aws:sns"


def is_api_gateway_event(event):
    """Check if the event is from API Gateway."""
    return "httpMethod" in event and "requestContext" in event


def handle_sns_event(event, context):
    """Handle SNS notification events (async inference completion)."""
    print("Processing SNS event")
    try:        
        from sns_handler import process_sns_notification

        results = []
        for record in event["Records"]:
            if record["EventSource"] == "aws:sns":
                sns_message = json.loads(record["Sns"]["Message"])
                
                # Process the SNS notification
                result = process_sns_notification(
                    sns_message=sns_message,
                    topic_arn=record["Sns"]["TopicArn"],
                    message_id=record["Sns"]["MessageId"]
                )
                results.append(result)
        
        # For SNS events, we don't need to return HTTP response format
        return {
            "processed_count": len(results),
            "results": results
        }
    except Exception as e:
        print(f"SNS processing failed: {e}")
        raise


def handle_api_gateway_event(event, context):
    """Handle API Gateway HTTP requests."""
    print("Processing API Gateway event")    
    
    method = event.get("httpMethod")
    path = event.get("path", "")
    
    if not method:
        return {
            "statusCode": 400,
            "headers": cors_header,
            "body": json.dumps({"message": "Invalid request: Missing httpMethod."}),
        }

    # Route to status endpoint
    if path == "/status" and method == "GET":
        from api_handler import get_endpoint_status
        response = get_endpoint_status()
    else:
        # Route to inference endpoint
        from api_handler import get_inference
        response = get_inference(
            request_id=context.aws_request_id,
            method=method,
            body=json.loads(event["body"]) if "body" in event and event["body"] else None,
            query_params=event.get("queryStringParameters", {})
        )
    
    # To ensure body is returned as JSON in response
    body = response.get("body", {})
    body = body if isinstance(body, str) else json.dumps(body, indent=2)
    
    return {
        "statusCode": response.get("statusCode", 200),
        "headers": cors_header,
        "body": body,
    }