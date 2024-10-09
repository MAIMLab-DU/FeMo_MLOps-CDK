import json
import os
import boto3
from datetime import datetime
from botocore.exceptions import ClientError
import tempfile

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
            if continuation_token:
                response = s3_client.list_objects_v2(Bucket=bucket_name, ContinuationToken=continuation_token)
            else:
                response = s3_client.list_objects_v2(Bucket=bucket_name)

            objects = response.get('Contents', [])
            all_objects.extend([{'bucketName': bucket_name, 'datFileKey': obj['Key'], 'csvFileKey': obj['Key'].replace('.dat', '.csv')}
                                for obj in objects if obj['Key'].endswith('.dat')])

            if response.get('IsTruncated'):
                continuation_token = response['NextContinuationToken']
            else:
                break

    except ClientError as e:
        print(f"Error listing objects in bucket {bucket_name}: {e}")
        raise e

    return all_objects

def build_manifest_file_content(previous_manifest=None):
    """Create a manifest content from the current state of the S3 bucket."""
    all_objects = list_all_objects(DATA_BUCKET_NAME)
    version = datetime.now().strftime("%Y-%m-%d_%H:%M")

    if previous_manifest is None:
        current_manifest = {
            "version": version,
            "lastNumObjects": len(all_objects),
            "items": all_objects
        }
    else:
        difference = len(all_objects) - previous_manifest['lastNumObjects']
        if difference >= MIN_DIFF:
            current_manifest = {
                "version": version,
                "lastNumObjects": len(all_objects),
                "items": all_objects
            }
        else:
            print("No significant change in the number of objects. Skipping manifest update.")
            return None

    return json.dumps(current_manifest, indent=4)

def upload_manifest_to_s3(file_content):
    """Upload the manifest.json file directly to the specified S3 bucket."""
    try:
        s3_client.put_object(
            Bucket=MANIFEST_BUCKET_NAME,
            Key="manifest.json",
            Body=file_content,
            ContentType='application/json'
        )
        print(f"Uploaded manifest.json to {MANIFEST_BUCKET_NAME}")
    except ClientError as e:
        print(f"Error uploading manifest.json to S3: {e}")
        raise e

def check_and_read_manifest():
    """Check if manifest.json exists in the bucket and read the manifest.json if it does."""
    try:
        s3_client.head_object(Bucket=MANIFEST_BUCKET_NAME, Key='manifest.json')
        print("manifest.json exists, downloading...")

        temp_dir = tempfile.gettempdir()
        manifest_file_path = os.path.join(temp_dir, 'manifest.json')
        
        s3_client.download_file(MANIFEST_BUCKET_NAME, 'manifest.json', manifest_file_path)
        
        with open(manifest_file_path, 'r') as manifest_file:
            manifest_content = json.load(manifest_file)
            print(f"Manifest content: {manifest_content}")
        
        return manifest_content

    except ClientError as e:
        if e.response['Error']['Code'] == '404':
            print("manifest.json does not exist.")
        else:
            print(f"Error checking or downloading manifest.json: {e}")
        return None

# TODO: belt type from MAC addresses
# TODO: manual triggering if event is not None
def handler(event, context):
    """Lambda function handler for periodic execution."""
    print("Lambda triggered by periodic event")

    try:
        # Check existing manifest
        previous_manifest = check_and_read_manifest()
        
        # Build the new manifest
        file_content = build_manifest_file_content(previous_manifest)

        # If there are significant changes, upload the new manifest
        if file_content is not None:
            upload_manifest_to_s3(file_content)

    except Exception as e:
        print(f"Error: {e}")
        raise e
