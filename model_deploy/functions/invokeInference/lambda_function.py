import json
from api_handler import get_inference
from sns_handler import process_sns_notification

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
    if not method:
        return {
            "statusCode": 400,
            "headers": cors_header,
            "body": json.dumps({"message": "Invalid request: Missing httpMethod."}),
        }

    # Delegate method-specific logic to `get_inference`
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