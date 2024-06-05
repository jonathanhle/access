import logging
import os
from typing import Any, Dict, Optional, Tuple

import yaml

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Get the environment variables
SERVICES_AWS_SSO = os.getenv("SERVICES_AWS_SSO")
SERVICES_TWINGATE_SSO = os.getenv("SERVICES_TWINGATE_SSO")

if not SERVICES_AWS_SSO or not SERVICES_TWINGATE_SSO:
    raise EnvironmentError("SERVICES_AWS_SSO or SERVICES_TWINGATE_SSO environment variable not set")

SERVICES_AWS_SSO = os.path.abspath(SERVICES_AWS_SSO)
SERVICES_TWINGATE_SSO = os.path.abspath(SERVICES_TWINGATE_SSO)


def get_service_file_and_key(target_okta_group_mapping: str) -> Tuple[Optional[str], Optional[str]]:
    """Determine the appropriate YAML file and service key based on the prefix of the target_okta_group_mapping.

    Args:
        target_okta_group_mapping (str): The Okta group mapping to check.

    Returns:
        Tuple[Optional[str], Optional[str]]: The service file path and service key if valid, otherwise (None, None).
    """
    if target_okta_group_mapping.startswith("APP_AWS_SSO"):
        return SERVICES_AWS_SSO, "aws_services"
    elif target_okta_group_mapping.startswith("APP_TG_"):
        return SERVICES_TWINGATE_SSO, "twingate_services"
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
