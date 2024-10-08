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
from datetime import datetime
from botocore.exceptions import ClientError

# Initialize the S3 client
s3_client = boto3.client('s3')
DATA_BUCKET_NAME = os.environ.get('DATA_BUCKET_NAME', '')
MANIFEST_BUCKET_NAME = os.environ.get('DATA_MANIFEST_BUCKET_NAME', '')
MIN_DIFF = int(os.environ.get('MIN_DIFF', 1))


def list_all_objects(bucket_name):
    """List all objects in the specified S3 bucket, handle pagination."""
    all_objects = []
    continuation_token = None

    try:
        while True:
            # Prepare the request parameters
            if continuation_token:
                response = s3_client.list_objects_v2(Bucket=bucket_name, ContinuationToken=continuation_token)
            else:
                response = s3_client.list_objects_v2(Bucket=bucket_name)

            # Append the object keys from the response
            objects = response.get('Contents', [])
            all_objects.extend([{'bucketName': bucket_name, 'objectKey': obj['Key']} for obj in objects if obj['Key'].endswith('.dat')])

            # Check if there are more objects to retrieve
            if response.get('IsTruncated'):  # More objects to fetch
                continuation_token = response['NextContinuationToken']
            else:
                break

    except ClientError as e:
        print(f"Error listing objects in bucket {bucket_name}: {e}")
        raise e

    return all_objects

def build_manifest_file_content(records: list, previous_manifest: dict|None = None):
    """Create a manifest content from the S3 event records. New manifest json is created if
    the number of new objects is greater than or equal to MIN_DIFF or if the difference between the previous
    manifest and the current manifest is greater than or equal to MIN_DIFF."""

    all_objects = list_all_objects(DATA_BUCKET_NAME)
    data_file_list = [
        {
            "bucketName": DATA_BUCKET_NAME,
            "objectKey": record['s3']['object']['key']
        }
        for record in records if 's3' in record
    ]
    version = datetime.now().strftime("%Y-%m-%d_%H:%M")

    if previous_manifest is None:
        current_manifest = {
            "version": version,
            "lastNumObjects": len(all_objects),
            "items": all_objects
        }
    else:
        difference = len(all_objects) - previous_manifest['lastNumObjects']
        if len(data_file_list) >= MIN_DIFF or difference >= MIN_DIFF:
            current_manifest = {
                "version": version,
                "lastNumObjects": len(all_objects),
                "items": all_objects
            }
        else:
            return None

    return json.dumps(current_manifest, indent=4)

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
                Bucket=MANIFEST_BUCKET_NAME,
                Key="manifest.json.zip",
                Body=file_data
            )
        except ClientError as e:
            print(f"Error uploading to S3: {e}")
            raise e

def check_and_read_manifest():
    """Check if manifest.json.zip exists in the bucket and read the manifest.json if it does."""
    try:
        # Check if the manifest.zip file exists in the bucket
        s3_client.head_object(Bucket=MANIFEST_BUCKET_NAME, Key='manifest.json.zip')
        print("manifest.json.zip exists, downloading...")

        # Download the manifest.zip file to a temporary location
        temp_dir = tempfile.gettempdir()
        zip_file_path = os.path.join(temp_dir, 'manifest.json.zip')
        
        s3_client.download_file(MANIFEST_BUCKET_NAME, 'manifest.json.zip', zip_file_path)
        
        # Extract the manifest.json file from the zip
        with zipfile.ZipFile(zip_file_path, 'r') as zip_ref:
            zip_ref.extractall(temp_dir)
        
        # Read the contents of the manifest.json file
        manifest_file_path = os.path.join(temp_dir, 'manifest.json')
        with open(manifest_file_path, 'r') as manifest_file:
            manifest_content = json.load(manifest_file)
            print(f"Manifest content: {manifest_content}")
        
        return manifest_content

    except ClientError as e:
        if e.response['Error']['Code'] == '404':
            print("manifest.json.zip does not exist.")
        else:
            print(f"Error checking or downloading manifest.json.zip: {e}")
        return None

def handler(event, context):
    """Lambda function handler."""
    print(f"Event: {json.dumps(event, indent=2)}")
    try:
        if "Records" in event and len(event["Records"]) > 0:
            sns_message = json.loads(event["Records"][0]["Sns"]["Message"])
            records = sns_message.get("Records", [])

            if records and len(records) > 0:
                print("Updating the data manifest file")

                # Check existing manifest
                previous_manifest = check_and_read_manifest()
                # Build the manifest content from the records
                file_content = build_manifest_file_content(records, previous_manifest)
                # Create a zip file with the manifest content
                if file_content is not None:
                    zip_file_path = create_zip_file_content(context.aws_request_id, file_content)
                    # Upload the zip file to S3
                    upload_to_s3(zip_file_path)

                    # Clean up temporary zip file
                    if os.path.exists(zip_file_path):
                        os.remove(zip_file_path)

    except Exception as e:
        print(f"Error: {e}")
        raise e
