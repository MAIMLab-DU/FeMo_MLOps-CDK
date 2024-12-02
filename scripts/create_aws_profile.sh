#!/bin/bash

function usage {
    echo "usage: codebuild_build.sh [-p profile_name] [-i aws_access_key_id] [-k aws_secret_access_key] [-r region]"
    echo "Required:"
    echo "  -p        AWS Profile name to set."
    echo "  -i        AWS Access Key ID."
    echo "  -k        AWS Secret Access Key."
    echo "  -r        AWS Region name."
}

profile_flag=false
id_flag=false
key_flag=false
region_flag=false

while getopts "cmdp:i:k:r:h" opt; do
    case $opt in
        p  ) image_flag=true; aws_profile=$OPTARG;;
        i  ) id_flag=true; aws_access_key_id=$OPTARG;;
        k  ) key_flag=true; aws_secret_access_key=$OPTARG;;
        r  ) region_flag=true; aws_region=$OPTARG;;
        h  ) usage; exit;;
        \? ) echo "Unknown option: -$OPTARG" >&2; exit 1;;
        :  ) echo "Missing option argument for -$OPTARG" >&2; exit 1;;
        *  ) echo "Invalid option: -$OPTARG" >&2; exit 1;;
    esac
done

# Configure the profile
aws configure set aws_access_key_id "$aws_access_key_id" --profile "$aws_profile"
aws configure set aws_secret_access_key "$aws_secret_access_key" --profile "$aws_profile"
aws configure set region "$aws_region" --profile "$aws_profile"

echo "AWS profile '$aws_profile' configured successfully."

