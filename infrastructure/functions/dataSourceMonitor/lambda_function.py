import json
import time
import os
import re
import boto3
import tempfile
import zipfile
from typing import Literal
from datetime import datetime
from botocore.exceptions import ClientError

# Initialize the S3 client
s3_client = boto3.client('s3')
DATA_BUCKET_NAME = os.environ.get('DATA_BUCKET_NAME', '')
MANIFEST_BUCKET_NAME = os.environ.get('DATA_MANIFEST_BUCKET_NAME', '')

def list_objects_by_belt_type(bucket_name):
    """Group objects by belt type from folder structure `<beltType>/<deviceId>/<logfile.dat>`."""
    grouped_objects = {
        'A': [],
        'B': [],
        'C': []
    }
    continuation_token = None
    
    try:
        while True:
            if continuation_token:                
                response = s3_client.list_objects_v2(Bucket=bucket_name, ContinuationToken=continuation_token)
            else:
                response = s3_client.list_objects_v2(Bucket=bucket_name)

            for obj in response.get('Contents', []):
                key = obj['Key']
                if not key.endswith('.dat'):
                    continue
                parts = key.split('/')
                if len(parts) < 3:
                    print(f"Skipping invalid file path: {key}")
                    continue
                
                belt_type, device_id, _ = parts[0], parts[1], parts[2]
                # Validate belt_type format
                if not re.match(r"^[ABC]_type$", belt_type):
                    print(f"Skipping invalid belt_type format: {belt_type} in file path: {key}")
                    continue
                
                belt_type: Literal['A', 'B', 'C'] = belt_type.split('_type')[0]
                grouped_objects[belt_type].append({
                    "deviceId": device_id,
                    "bucketName": bucket_name,
                    "datFileKey": key,
                    "csvFileKey": key.replace('.dat', '.csv')
                })

            if response.get('IsTruncated'):
                continuation_token = response['NextContinuationToken']
            else:
                break

    except ClientError as e:
        print(f"Error listing objects in bucket {bucket_name}: {e}")
        raise e

    return grouped_objects

def build_manifest(previous_manifest=None, all_objects=None, belt_type=None):
    """
    Build a manifest for a specific belt type, incorporating the provided logic
    for checking differences in object count.
    """
    version = datetime.now().strftime("%Y-%m-%d_%H:%M")

    # Handle the case where there are no previous manifests
    if previous_manifest is None:
        current_manifest = {
            "version": version,
            "beltType": belt_type,
            "lastNumObjects": len(all_objects),
            "items": all_objects
        }
    else:
        # Compare the difference in object count
        difference = len(all_objects) - previous_manifest['lastNumObjects']
        if difference != 0:
            current_manifest = {
                "version": version,
                "beltType": belt_type,
                "lastNumObjects": len(all_objects),
                "items": all_objects
            }
        else:
            print(f"No change in the number of objects for {belt_type}. Skipping manifest update.")
            return None

    return current_manifest


def upload_manifest_to_s3(manifest, belt_type):
    """Upload the manifest file for a specific belt type to the manifest bucket."""
    manifest_file_name = f"manifest-{belt_type}.json"
    manifest_file_content = json.dumps(manifest, indent=4)
    temp_dir = tempfile.gettempdir()
    zip_file_path = os.path.join(temp_dir, f"{manifest_file_name}.zip")
    with zipfile.ZipFile(zip_file_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        zipf.writestr(manifest_file_name, manifest_file_content)

    try:
        # Upload the manifest JSON file
        s3_client.put_object(
            Bucket=MANIFEST_BUCKET_NAME,
            Key=manifest_file_name,
            Body=manifest_file_content,
            ContentType='application/json'
        )
        with open(zip_file_path, 'rb') as file_data:
            s3_client.put_object(
                Bucket=MANIFEST_BUCKET_NAME,
                Key=f"{manifest_file_name}.zip",
                Body=file_data
            )
        print(f"Uploaded {manifest_file_name} to {MANIFEST_BUCKET_NAME}")
    except ClientError as e:
        print(f"Error uploading manifest for {belt_type}: {e}")
        raise e


def check_and_read_manifest(belt_type):
    """Check if manifest.json exists in the bucket and read the manifest.json if it does."""
    try:
        manifest_file_name = f"manifest-{belt_type}.json"
        s3_client.head_object(Bucket=MANIFEST_BUCKET_NAME, Key=manifest_file_name)
        print(f"{manifest_file_name} exists, downloading...")

        temp_dir = tempfile.gettempdir()
        manifest_file_path = os.path.join(temp_dir, manifest_file_name)
        
        s3_client.download_file(MANIFEST_BUCKET_NAME, manifest_file_name, manifest_file_path)
        
        with open(manifest_file_path, 'r') as manifest_file:
            manifest_content = json.load(manifest_file)
            print(f"Previous manifest item count: {len(manifest_content['items'])}")
        
        return manifest_content

    except ClientError as e:
        if e.response['Error']['Code'] == '404':
            print(f"{manifest_file_name} does not exist.")
        else:
            print(f"Error checking or downloading manifest.json: {e}")
        return None


def lambda_handler(event, context):
    """Lambda function handler to generate and upload manifests for each belt type."""
    print("Lambda triggered to process S3 log files and generate manifests.")

    try:
        # Group objects by belt type
        grouped_objects = list_objects_by_belt_type(DATA_BUCKET_NAME)

        # Process each belt type
        for belt_type, items in grouped_objects.items():
            print(f"Processing belt type: {belt_type} with {len(items)} items.")

            # Check for previous manifest
            previous_manifest = check_and_read_manifest(belt_type)  # Modify to fetch based on belt type if needed
            
            # Build the manifest for this belt type
            manifest = build_manifest(previous_manifest=previous_manifest, all_objects=items, belt_type=belt_type)

            # Upload the manifest if it was generated
            if manifest is not None:
                upload_manifest_to_s3(manifest, belt_type)
            
            # Sleep added to ensure queueing of Codepipeline execution
            if len(grouped_objects) > 1 and len(items) > 0:        
                time.sleep(10)

    except Exception as e:
        print(f"Error in Lambda execution: {e}")
        raise e
