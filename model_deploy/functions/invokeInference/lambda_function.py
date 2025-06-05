import json
from api_handler import get_inference

# CORS headers
cors_header = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "OPTIONS,POST,GET,PUT,DELETE",
}


def lambda_handler(event, context):
    """
    AWS Lambda handler function.

    Args:
        event: The event object containing request data.
        context: The context object with Lambda invocation information.

    Returns:
        dict: The response object with statusCode, headers, and body.
    """
    print("Event: ", json.dumps(event))

    try:
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

    except Exception as e:
        print("Error: ", e)
        message = str(e)
        return {
            "statusCode": 500,
            "headers": cors_header,
            "body": json.dumps({"message": message}),
        }
