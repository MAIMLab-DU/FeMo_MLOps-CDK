import json
import os
import boto3
from datetime import datetime
from typing import Dict, Any
import re

# Initialize AWS clients
ses_client = boto3.client('ses')
sns_client = boto3.client('sns')

# Environment variables
EMAIL_ADDRESSES = os.environ.get('EMAIL_ADDRESSES', '').split(',')
PROJECT_NAME = os.environ.get('PROJECT_NAME', '')


def lambda_handler(event, context):
    """
    Lambda function handler to process CodePipeline state change notifications
    and send formatted email notifications.
    
    Args:
        event: The event object containing SNS notification data
        context: The context object with Lambda invocation information
        
    Returns:
        dict: Response object
    """
    print(f"Received event: {json.dumps(event)}")
    
    try:
        # Process each SNS record
        for record in event.get('Records', []):
            if record.get('EventSource') == 'aws:sns':
                message = json.loads(record['Sns']['Message'])
                
                # Process the pipeline state change notification
                process_pipeline_notification(message)
        
        return {
            'statusCode': 200,
            'body': json.dumps({'message': 'Notifications processed successfully'})
        }
        
    except Exception as e:
        print(f"Error processing notification: {e}")
        import traceback
        print(traceback.format_exc())
        raise


def process_pipeline_notification(message: Dict[str, Any]) -> None:
    """
    Process the CodePipeline state change notification and send email.
    
    Args:
        message: The CodePipeline state change event message
    """
    print(f"Processing pipeline notification: {json.dumps(message)}")
    
    try:
        # Extract pipeline information
        detail = message.get('detail', {})
        pipeline_name = detail.get('pipeline', 'Unknown Pipeline')
        execution_id = detail.get('execution-id', 'Unknown Execution')
        state = detail.get('state', 'Unknown State')
        start_time = detail.get('start-time', '')
        version = detail.get('version', 'Unknown Version')
        execution_attempt = detail.get('pipeline-execution-attempt', 1)
        
        # Parse trigger information
        trigger = detail.get('execution-trigger', {})
        trigger_type = trigger.get('trigger-type', 'Unknown')
        trigger_detail = trigger.get('trigger-detail', '')
        
        # Format the trigger details
        trigger_info = format_trigger_details(trigger_type, trigger_detail)
        
        # Generate email content
        subject = f"[{PROJECT_NAME}] Pipeline {state}: {pipeline_name}"
        body_html, body_text = generate_email_content(
            pipeline_name, execution_id, state, start_time, 
            version, execution_attempt, trigger_info, message
        )
        
        # Send email to all configured addresses
        send_email_notifications(subject, body_html, body_text)
        
    except Exception as e:
        print(f"Error processing pipeline notification: {e}")
        raise


def format_trigger_details(trigger_type: str, trigger_detail: str) -> Dict[str, Any]:
    """
    Parse and format trigger details based on trigger type.
    
    Args:
        trigger_type: The type of trigger (e.g., WebhookV2)
        trigger_detail: JSON string containing trigger details
        
    Returns:
        dict: Formatted trigger information
    """
    try:
        if trigger_detail:
            details = json.loads(trigger_detail)
            
            if trigger_type == 'WebhookV2':
                repo_id = details.get('repositoryId', '')
                tag_name = details.get('tagName', '')
                push_type = details.get('type', '')
                
                return {
                    'type': 'Git Repository Push',
                    'repository': repo_id,
                    'tag': tag_name,
                    'push_type': push_type
                }
        
        return {
            'type': trigger_type,
            'details': trigger_detail if trigger_detail else 'No additional details'
        }
        
    except (json.JSONDecodeError, Exception) as e:
        print(f"Error parsing trigger details: {e}")
        return {
            'type': trigger_type,
            'details': 'Failed to parse trigger details'
        }


def generate_email_content(pipeline_name: str, execution_id: str, state: str, 
                         start_time: str, version: float, execution_attempt: float,
                         trigger_info: Dict[str, Any], full_message: Dict[str, Any]) -> tuple:
    """
    Generate HTML and text email content for the pipeline notification.
    
    Args:
        pipeline_name: Name of the pipeline
        execution_id: Pipeline execution ID
        state: Current state of the pipeline (STARTED, SUCCEEDED, FAILED, etc.)
        start_time: When the execution started
        version: Pipeline version
        execution_attempt: Execution attempt number
        trigger_info: Formatted trigger information
        full_message: Complete notification message for debugging
        
    Returns:
        tuple: (html_body, text_body)
    """
    # Format the timestamp
    formatted_time = format_timestamp(start_time)
    
    # Determine state emoji and color
    state_info = get_state_info(state)
    
    # Generate AWS Console links
    region = full_message.get('region', 'us-east-1')
    pipeline_url = f"https://{region}.console.aws.amazon.com/codesuite/codepipeline/pipelines/{pipeline_name}/view"
    execution_url = f"https://{region}.console.aws.amazon.com/codesuite/codepipeline/pipelines/{pipeline_name}/executions/{execution_id}/timeline"
    
    # HTML Email Body
    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Pipeline Notification</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5; }}
            .container {{ max-width: 600px; margin: 0 auto; background-color: white; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
            .header {{ background-color: {state_info['color']}; color: white; padding: 20px; text-align: center; }}
            .content {{ padding: 20px; }}
            .info-row {{ margin: 10px 0; padding: 10px; background-color: #f8f9fa; border-left: 4px solid {state_info['color']}; }}
            .label {{ font-weight: bold; color: #333; }}
            .value {{ color: #666; }}
            .button {{ display: inline-block; padding: 10px 20px; background-color: #007bff; color: white; text-decoration: none; border-radius: 4px; margin: 5px; }}
            .trigger-info {{ background-color: #e9ecef; padding: 15px; border-radius: 4px; margin: 15px 0; }}
            .footer {{ padding: 20px; text-align: center; font-size: 12px; color: #666; background-color: #f8f9fa; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>{state_info['emoji']} Pipeline {state}</h1>
                <h2>{PROJECT_NAME} - MLOps Pipeline</h2>
            </div>
            <div class="content">
                <div class="info-row">
                    <span class="label">Pipeline:</span> <span class="value">{pipeline_name}</span>
                </div>
                <div class="info-row">
                    <span class="label">Status:</span> <span class="value">{state}</span>
                </div>
                <div class="info-row">
                    <span class="label">Execution ID:</span> <span class="value">{execution_id}</span>
                </div>
                <div class="info-row">
                    <span class="label">Started:</span> <span class="value">{formatted_time}</span>
                </div>
                <div class="info-row">
                    <span class="label">Version:</span> <span class="value">{version}</span>
                </div>
                <div class="info-row">
                    <span class="label">Attempt:</span> <span class="value">{execution_attempt}</span>
                </div>
                
                <div class="trigger-info">
                    <h3>Trigger Information</h3>
                    <div class="info-row">
                        <span class="label">Type:</span> <span class="value">{trigger_info.get('type', 'Unknown')}</span>
                    </div>
                    {format_trigger_html(trigger_info)}
                </div>
                
                <div style="text-align: center; margin: 20px 0;">
                    <a href="{pipeline_url}" class="button">View Pipeline</a>
                    <a href="{execution_url}" class="button">View Execution</a>
                </div>
            </div>
            <div class="footer">
                <p>This is an automated notification from the {PROJECT_NAME} MLOps Pipeline.</p>
                <p>Timestamp: {datetime.utcnow().isoformat()}Z</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    # Text Email Body
    text_body = f"""
{state_info['emoji']} Pipeline {state}: {PROJECT_NAME} - MLOps Pipeline

Pipeline Details:
- Pipeline: {pipeline_name}
- Status: {state}
- Execution ID: {execution_id}
- Started: {formatted_time}
- Version: {version}
- Attempt: {execution_attempt}

Trigger Information:
- Type: {trigger_info.get('type', 'Unknown')}
{format_trigger_text(trigger_info)}

AWS Console Links:
- Pipeline: {pipeline_url}
- Execution: {execution_url}

---
This is an automated notification from the {PROJECT_NAME} MLOps Pipeline.
Timestamp: {datetime.utcnow().isoformat()}Z
"""
    
    return html_body, text_body


def format_trigger_html(trigger_info: Dict[str, Any]) -> str:
    """Format trigger information as HTML."""
    html = ""
    for key, value in trigger_info.items():
        if key != 'type' and value:
            html += f'<div class="info-row"><span class="label">{key.title()}:</span> <span class="value">{value}</span></div>'
    return html


def format_trigger_text(trigger_info: Dict[str, Any]) -> str:
    """Format trigger information as plain text."""
    text = ""
    for key, value in trigger_info.items():
        if key != 'type' and value:
            text += f"- {key.title()}: {value}\n"
    return text


def format_timestamp(timestamp: str) -> str:
    """
    Format ISO timestamp to a more readable format.
    
    Args:
        timestamp: ISO format timestamp string
        
    Returns:
        str: Formatted timestamp
    """
    try:
        if timestamp:
            dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            return dt.strftime('%Y-%m-%d %H:%M:%S UTC')
        return 'Unknown Time'
    except Exception as e:
        print(f"Error formatting timestamp {timestamp}: {e}")
        return timestamp


def get_state_info(state: str) -> Dict[str, str]:
    """
    Get emoji and color information based on pipeline state.
    
    Args:
        state: Pipeline state
        
    Returns:
        dict: Contains emoji and color for the state
    """
    state_mapping = {
        'STARTED': {'emoji': '🚀', 'color': '#17a2b8'},
        'SUCCEEDED': {'emoji': '✅', 'color': '#28a745'},
        'FAILED': {'emoji': '❌', 'color': '#dc3545'},
        'CANCELED': {'emoji': '⚠️', 'color': '#ffc107'},
        'SUPERSEDED': {'emoji': '🔄', 'color': '#6c757d'},
        'STOPPING': {'emoji': '⏹️', 'color': '#fd7e14'},
        'STOPPED': {'emoji': '⏹️', 'color': '#6c757d'}
    }
    
    return state_mapping.get(state, {'emoji': '📋', 'color': '#6c757d'})


def send_email_notifications(subject: str, html_body: str, text_body: str) -> None:
    """
    Send email notifications to all configured email addresses.
    
    Args:
        subject: Email subject
        html_body: HTML email body
        text_body: Plain text email body
    """
    if not EMAIL_ADDRESSES or not EMAIL_ADDRESSES[0]:
        print("No email addresses configured")
        return
    
    # Filter out empty email addresses
    valid_emails = [email.strip() for email in EMAIL_ADDRESSES if email.strip()]
    
    if not valid_emails:
        print("No valid email addresses found")
        return
    
    try:
        # Use the first email as the source (should be verified in SES)
        source_email = valid_emails[0]
        
        # Send email to all recipients
        response = ses_client.send_email(
            Source=source_email,
            Destination={
                'ToAddresses': valid_emails
            },
            Message={
                'Subject': {
                    'Data': subject,
                    'Charset': 'UTF-8'
                },
                'Body': {
                    'Html': {
                        'Data': html_body,
                        'Charset': 'UTF-8'
                    },
                    'Text': {
                        'Data': text_body,
                        'Charset': 'UTF-8'
                    }
                }
            }
        )
        
        print(f"Email sent successfully to {len(valid_emails)} recipients. MessageId: {response['MessageId']}")
        
    except Exception as e:
        print(f"Error sending email: {e}")
        # If SES fails, log the error but don't fail the entire function
        print(f"Failed to send email notification. Recipients: {valid_emails}")
        print(f"Subject: {subject}")
