import json
from utils import get_inference

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
    print("Event:\t" + json.dumps(event))

    try:
        response = get_inference(context.aws_request_id, event)
        print(f"RequestId: {context.aws_request_id},\t response:{response}")
        return {
            "statusCode": 200,
            "headers": cors_header,
            "body": json.dumps(response) if response else None,
        }
    except Exception as e:
        print("Error: ", e)
        message = str(e)
        return {
            "statusCode": 500,
            "headers": cors_header,
            "body": json.dumps({"message": message}),
        }
