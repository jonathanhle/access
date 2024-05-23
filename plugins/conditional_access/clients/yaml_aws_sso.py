import logging
import os

import yaml

logger = logging.getLogger(__name__)

# Get the environment variables
SERVICES_AWS_SSO = os.path.abspath(os.getenv("SERVICES_AWS_SSO"))
SERVICES_TWINGATE_SSO = os.path.abspath(os.getenv("SERVICES_TWINGATE_SSO"))


def find_first_matching_service(target_okta_group_mapping):
    def get_service_file_and_key(target_okta_group_mapping):
        """
        Determine the appropriate YAML file and service key based on the prefix of the target_okta_group_mapping.
        """
        if target_okta_group_mapping.startswith("APP_AWS_SSO_"):
            return SERVICES_AWS_SSO, "aws_services"
        elif target_okta_group_mapping.startswith("APP_TG_"):
            return SERVICES_TWINGATE_SSO, "twingate_services"
        else:
            logger.error("Invalid okta_group_mapping prefix")
            return None, None

    service_file, service_key = get_service_file_and_key(target_okta_group_mapping)

    if not service_file or not service_key:
        return None

    logger.info(f"Starting search in {service_file} for {target_okta_group_mapping}")
    if not os.path.exists(service_file):
        logger.error(f"File not found: {service_file}")
        return None

    with open(service_file, "r") as file:
        try:
            documents = yaml.safe_load_all(file)
        except yaml.YAMLError as exc:
            logger.error(f"Error parsing YAML file: {exc}")
            return None

        for doc in documents:
            services = doc.get(service_key, [])
            for service in services:
                if service_key == "aws_services":
                    # Match based on okta_group_mapping directly for AWS services
                    if service.get("okta_group_mapping") == target_okta_group_mapping:
                        logger.info(f"Matching service found in {service_file}.")
                        return service
                elif service_key == "twingate_services":
                    # Match based on hostname for Twingate services
                    hostname = service.get("hostname", "")
                    # Extract the hostname part from the target_okta_group_mapping
                    if target_okta_group_mapping.split("_", 2)[-1] == hostname:
                        logger.info(f"Matching service found in {service_file}.")
                        return service

    logger.info(f"No matching service found in {service_file}.")
    return None
