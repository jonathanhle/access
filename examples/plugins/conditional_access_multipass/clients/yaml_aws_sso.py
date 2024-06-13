import logging
import os
from typing import Any, Dict, Optional, Tuple

import boto3
import yaml

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Get the environment variables
SERVICES_AWS_SSO_PATH = os.getenv("SERVICES_AWS_SSO_PATH")
SERVICES_TWINGATE_SSO_PATH = os.getenv("SERVICES_TWINGATE_SSO_PATH")
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")

if not SERVICES_AWS_SSO_PATH or not SERVICES_TWINGATE_SSO_PATH or not S3_BUCKET_NAME:
    raise EnvironmentError(
        "SERVICES_AWS_SSO_PATH, SERVICES_TWINGATE_SSO_PATH, or S3_BUCKET_NAME environment variable not set"
    )

SERVICES_AWS_SSO_PATH = os.path.abspath(SERVICES_AWS_SSO_PATH)
SERVICES_TWINGATE_SSO_PATH = os.path.abspath(SERVICES_TWINGATE_SSO_PATH)


def download_latest_yaml_from_s3(s3_key: str, local_path: str) -> None:
    """
    Download the latest YAML file from S3 to the specified local path.

    This function checks if the local YAML file is up-to-date with the one in S3
    and downloads the latest version if necessary. It compares the last modified
    timestamps of the local and S3 files to determine if an update is needed.

    Args:
        s3_key (str): The S3 key (path) of the YAML file.
        local_path (str): The local file path where the YAML file will be saved.

    Returns:
        None
    """
    s3 = boto3.client("s3")
    try:
        logger.info(f"Attempting to access S3 bucket '{S3_BUCKET_NAME}' with key '{s3_key}'")

        # Retrieve the metadata of the S3 object
        s3_object = s3.head_object(Bucket=S3_BUCKET_NAME, Key=s3_key)
        s3_last_modified = s3_object["LastModified"]

        # Check if the local file exists and compare timestamps
        if os.path.exists(local_path):
            local_last_modified = os.path.getmtime(local_path)
            if s3_last_modified.timestamp() <= local_last_modified:
                logger.info(f"Local YAML file {local_path} is up-to-date.")
                return

        # Download the file from S3 if the local file is outdated or does not exist
        logger.info(f"Downloading latest YAML file from S3: {S3_BUCKET_NAME}/{s3_key}")
        s3.download_file(S3_BUCKET_NAME, s3_key, local_path)
        # Update the access and modification times of the local file to match the S3 object
        os.utime(local_path, (s3_last_modified.timestamp(), s3_last_modified.timestamp()))
        logger.info(f"Downloaded and updated {local_path} with the latest version.")
    except s3.exceptions.NoSuchKey:
        logger.error(f"The specified key does not exist: {s3_key}")
    except s3.exceptions.ClientError as e:
        if e.response["Error"]["Code"] == "403":
            logger.error(f"Access denied for bucket: {S3_BUCKET_NAME}")
        else:
            logger.error(f"Failed to download YAML file from S3: {e}")


def get_service_file_and_key(target_okta_group_mapping: str) -> Tuple[Optional[str], Optional[str]]:
    """Determine the appropriate YAML file and service key based on the prefix of the target_okta_group_mapping.

    Args:
        target_okta_group_mapping (str): The Okta group mapping to check.

    Returns:
        Tuple[Optional[str], Optional[str]]: The service file path and service key if valid, otherwise (None, None).
    """
    if target_okta_group_mapping.startswith("APP_AWS_SSO"):
        return SERVICES_AWS_SSO_PATH, "aws_services"
    elif target_okta_group_mapping.startswith("APP_TG_"):
        return SERVICES_TWINGATE_SSO_PATH, "twingate_services"
    else:
        logger.error("Invalid okta_group_mapping prefix")
        return None, None


def find_first_matching_service(target_okta_group_mapping: str) -> Optional[Dict[str, Any]]:
    """Find the first matching service in the appropriate YAML file based on the target_okta_group_mapping.

    Args:
        target_okta_group_mapping (str): The Okta group mapping to search for.

    Returns:
        Optional[Dict[str, Any]]: The matching service details if found, otherwise None.
    """
    service_file, service_key = get_service_file_and_key(target_okta_group_mapping)

    if not service_file or not service_key:
        return None

    # Determine the S3 key from the local file path
    s3_key = os.path.basename(service_file)

    # Download the latest YAML file from S3
    download_latest_yaml_from_s3(s3_key, service_file)

    logger.info(f"Starting search in {service_file} for {target_okta_group_mapping}")
    if not os.path.exists(service_file):
        logger.error(f"File not found: {service_file}")
        return None

    try:
        with open(service_file, "r") as file:
            documents = list(yaml.safe_load_all(file))  # Convert to list to keep the file open while processing

        for doc in documents:
            services = doc.get(service_key, [])
            for service in services:
                if service_key == "aws_services":
                    if service.get("okta_group_mapping") == target_okta_group_mapping:
                        logger.info(f"Matching service found in {service_file}.")
                        return service
                elif service_key == "twingate_services":
                    hostname = service.get("hostname", "")
                    if target_okta_group_mapping.split("_", 2)[-1] == hostname:
                        logger.info(f"Matching service found in {service_file}.")
                        return service
    except yaml.YAMLError as exc:
        logger.error(f"Error parsing YAML file: {exc}")
        return None

    logger.info(f"No matching service found in {service_file}.")
    return None
