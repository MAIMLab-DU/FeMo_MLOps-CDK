"""
This module contains the Lambda function handler for processing S3 events.
The function builds a manifest file from the S3 events, compresses it into a zip file,
and uploads it to a designated S3 bucket.
"""

import json
import os
import zipfile
import tempfile
import boto3
from botocore.exceptions import ClientError

# Initialize the S3 client
s3_client = boto3.client('s3')
s3_bucket_name = os.environ.get('DATA_MANIFEST_BUCKET_NAME', '')

def build_manifest_file_content(records):
    """Create a manifest content from the S3 event records."""
    data_file_list = [
        {
            "bucketName": record['s3']['bucket']['name'],
            "objectKey": record['s3']['object']['key']
        }
        for record in records if 's3' in record
    ]

    return json.dumps({"data": data_file_list}, indent=2)

def create_zip_file_content(object_key, file_content):
    """Create a zip file with the manifest.json inside."""
    temp_dir = tempfile.gettempdir()
    zip_file_path = os.path.join(temp_dir, f"{object_key}.zip")

    with zipfile.ZipFile(zip_file_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        zipf.writestr("manifest.json", file_content)

    return zip_file_path

def upload_to_s3(zip_file_path):
    """Upload the zip file to the specified S3 bucket."""
    with open(zip_file_path, 'rb') as file_data:
        try:
            s3_client.put_object(
                Bucket=s3_bucket_name,
                Key="manifest.json.zip",
                Body=file_data
            )
        except ClientError as e:
            print(f"Error uploading to S3: {e}")
            raise e

def handler(event, context):
    """Lambda function handler."""
    print(f"Event: {json.dumps(event, indent=2)}")
    try:
        if "Records" in event and len(event["Records"]) > 0:
            sns_message = json.loads(event["Records"][0]["Sns"]["Message"])
            records = sns_message.get("Records", [])

            if records and len(records) > 0:
                print("Updating the data manifest file")

                # Build the manifest content from the records
                file_content = build_manifest_file_content(records)
                # Create a zip file with the manifest content
                zip_file_path = create_zip_file_content(context.aws_request_id, file_content)
                # Upload the zip file to S3
                upload_to_s3(zip_file_path)

                # Clean up temporary zip file
                if os.path.exists(zip_file_path):
                    os.remove(zip_file_path)

    except Exception as e:
        print(f"Error: {e}")
        raise e
