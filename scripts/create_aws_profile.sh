#!/bin/bash

# Usage information
usage() {
    echo "Usage: $0 -p <profile_name> -i <aws_access_key_id> -k <aws_secret_access_key> -r <region>"
    echo
    echo "Required Parameters:"
    echo "  -p    AWS CLI profile name to configure"
    echo "  -i    AWS Access Key ID"
    echo "  -k    AWS Secret Access Key"
    echo "  -r    AWS Region (e.g., us-east-1)"
    echo "  -h    Show help and exit"
    echo
    exit 1
}

# Argument flags
profile_flag=false
id_flag=false
key_flag=false
region_flag=false

# Argument parsing
while getopts ":p:i:k:r:h" opt; do
    case "$opt" in
        p) profile_flag=true; aws_profile="$OPTARG" ;;
        i) id_flag=true; aws_access_key_id="$OPTARG" ;;
        k) key_flag=true; aws_secret_access_key="$OPTARG" ;;
        r) region_flag=true; aws_region="$OPTARG" ;;
        h) usage ;;
        :) echo "❌ Missing argument for -$OPTARG" >&2; usage ;;
        \?) echo "❌ Unknown option: -$OPTARG" >&2; usage ;;
    esac
done

# Validate all required parameters
if ! $profile_flag || ! $id_flag || ! $key_flag || ! $region_flag; then
    echo "❌ Error: All parameters -p, -i, -k, and -r are required."
    usage
fi

# Configure AWS profile
aws configure set aws_access_key_id "$aws_access_key_id" --profile "$aws_profile"
aws configure set aws_secret_access_key "$aws_secret_access_key" --profile "$aws_profile"
aws configure set region "$aws_region" --profile "$aws_profile"

echo "✅ AWS profile '$aws_profile' configured successfully."
