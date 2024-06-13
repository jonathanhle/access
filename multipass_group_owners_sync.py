import logging
import os
from datetime import datetime, timezone

import yaml
from dotenv import load_dotenv
from flask import Flask
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload, selectin_polymorphic, selectinload

from api.extensions import db
from api.models import AppGroup, OktaGroup, OktaUser, OktaUserGroupMember, RoleGroup
from plugins.conditional_access_multipass.clients.yaml_aws_sso import download_latest_yaml_from_s3

load_dotenv()

# Setup basic configuration and logging
app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URI")
if not app.config["SQLALCHEMY_DATABASE_URI"]:
    raise EnvironmentError("DATABASE_URI environment variable not set")

db.init_app(app)

# Setup logging
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_FILE = "app.log"

logging.basicConfig(
    level=logging.INFO, format=LOG_FORMAT, handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()]
)

logger = logging.getLogger(__name__)

# Get the environment variables
SERVICES_AWS_SSO_PATH = os.getenv("SERVICES_AWS_SSO_PATH")
SERVICES_TWINGATE_SSO_PATH = os.getenv("SERVICES_TWINGATE_SSO_PATH")
S3_AWS_SSO_KEY = os.getenv("S3_AWS_SSO_KEY")
S3_TWINGATE_KEY = os.getenv("S3_TWINGATE_KEY")

if not SERVICES_AWS_SSO_PATH or not SERVICES_TWINGATE_SSO_PATH:
    raise EnvironmentError("SERVICES_AWS_SSO_PATH or SERVICES_TWINGATE_SSO_PATH environment variable not set")

SERVICES_AWS_SSO_PATH = os.path.abspath(SERVICES_AWS_SSO_PATH)
SERVICES_TWINGATE_SSO_PATH = os.path.abspath(SERVICES_TWINGATE_SSO_PATH)


def load_config(file_path: str) -> dict:
    """Loads YAML configuration from the specified file path."""
    try:
        with open(file_path, "r") as file:
            config = yaml.safe_load(file)
            if not config:
                raise ValueError(f"No configuration found in {file_path}")
            return config
    except FileNotFoundError:
        logger.error(f"Configuration file not found at {file_path}")
        raise
    except yaml.YAMLError as e:
        logger.error(f"Error parsing YAML file: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error while loading config: {e}")
        raise


def get_group_by_name(group_name: str) -> OktaGroup:
    """Fetches an active OktaGroup by its name."""
    try:
        group = (
            db.session.query(OktaGroup)
            .options(
                selectin_polymorphic(OktaGroup, [AppGroup, RoleGroup]),
                joinedload(AppGroup.app),
                selectinload(OktaGroup.active_user_memberships).options(joinedload(OktaUserGroupMember.user)),
            )
            .filter(OktaGroup.deleted_at.is_(None))
            .filter(OktaGroup.name == group_name)
            .first()
        )
        return group
    except SQLAlchemyError as e:
        logger.error(f"Database error occurred: {e}")
        raise


def add_owner_to_group(group: OktaGroup, owner_email: str) -> None:
    """Adds a new owner to a group if not already an owner."""
    try:
        owner = db.session.query(OktaUser).filter_by(email=owner_email).first()
        if not owner:
            logger.info(f"No user found with email {owner_email}")
            return

        current_time = datetime.now(timezone.utc)
        existing_owner = (
            db.session.query(OktaUserGroupMember).filter_by(group_id=group.id, user_id=owner.id, is_owner=True).first()
        )

        if existing_owner:
            if existing_owner.ended_at is None or existing_owner.ended_at.replace(tzinfo=timezone.utc) > current_time:
                logger.info(f"User {owner_email} is already an active owner of the group {group.name}")
                return
            else:
                # Reactivate the owner
                existing_owner.ended_at = None
                db.session.commit()
                logger.info(f"Reactivated {owner_email} as an owner of the group {group.name}")
                return

        new_owner = OktaUserGroupMember(user_id=owner.id, group_id=group.id, is_owner=True)
        db.session.add(new_owner)
        db.session.commit()
        logger.info(f"Added {owner_email} as an owner to the group {group.name}")
    except SQLAlchemyError as e:
        logger.error(f"Failed to add owner to group: {e}")
        db.session.rollback()
        raise


def remove_owner_from_group(group: OktaGroup, owner_email: str) -> None:
    """Removes an owner from a group if they are an active owner."""
    try:
        owner = db.session.query(OktaUser).filter_by(email=owner_email).first()
        if not owner:
            logger.info(f"No user found with email {owner_email}")
            return

        current_time = datetime.now(timezone.utc)
        existing_owner = (
            db.session.query(OktaUserGroupMember)
            .filter_by(group_id=group.id, user_id=owner.id, is_owner=True)
            .filter((OktaUserGroupMember.ended_at == None) | (OktaUserGroupMember.ended_at > current_time))
            .first()
        )

        if existing_owner:
            existing_owner.ended_at = current_time
            db.session.commit()
            logger.info(f"Removed {owner_email} as an owner from the group {group.name}")
        else:
            logger.info(f"User {owner_email} is not an active owner of the group {group.name}")
    except SQLAlchemyError as e:
        logger.error(f"Failed to remove owner from group: {e}")
        db.session.rollback()
        raise


def sync_group_owners(group: OktaGroup, expected_owners: set) -> None:
    """Synchronizes the owners of a group with the expected owners."""
    try:
        current_time = datetime.now(timezone.utc)
        active_owners = (
            db.session.query(OktaUserGroupMember)
            .options(joinedload(OktaUserGroupMember.user))
            .filter_by(group_id=group.id, is_owner=True)
            .filter((OktaUserGroupMember.ended_at == None) | (OktaUserGroupMember.ended_at > current_time))
            .all()
        )

        active_owner_emails = {owner.user.email for owner in active_owners}

        # Add new owners
        for owner_email in expected_owners - active_owner_emails:
            add_owner_to_group(group, owner_email)

        # Remove owners not in the expected list
        for owner_email in active_owner_emails - expected_owners:
            remove_owner_from_group(group, owner_email)
    except SQLAlchemyError as e:
        logger.error(f"Failed to sync owners for group {group.name}: {e}")
        db.session.rollback()
        raise


def sync_twingate_groups(resources: dict) -> None:
    twingate_group_prefix = "APP_TG_"
    twingate_resource_services = resources["twingate_services"]

    for service in twingate_resource_services:
        service_name = service["hostname"]
        system_owners = service["access_rules"]["auto_approval"]["system_owners"]
        groups = system_owners["okta_groups"]
        users = system_owners["okta_users"]

        system_owners_groups = [
            member.user.email for group in groups for member in get_group_by_name(group).active_user_memberships
        ]

        all_owners = set(system_owners_groups + users)
        group_name = f"{twingate_group_prefix}{service_name}"
        group = get_group_by_name(group_name)

        # Sync group owners
        if group:
            sync_group_owners(group, all_owners)
        else:
            logger.info(f"Group {group_name} not found.")


def sync_aws_sso_groups(resources: dict) -> None:
    aws_sso_services = resources["aws_services"]

    for service in aws_sso_services:
        service_name = service["okta_group_mapping"]
        system_owners = service["access_rules"]["auto_approval"]["system_owners"]
        groups = system_owners["okta_groups"]
        users = system_owners["okta_users"]

        system_owners_groups = [
            member.user.email for group in groups for member in get_group_by_name(group).active_user_memberships
        ]

        all_owners = set(system_owners_groups + users)
        group = get_group_by_name(service_name)

        # Sync group owners
        if group:
            sync_group_owners(group, all_owners)
        else:
            logger.info(f"Group {service_name} not found.")


def sync_yaml_owners() -> None:
    """Main function to execute the script logic."""
    try:
        # Download the latest YAML files if they are newer
        download_latest_yaml_from_s3(S3_AWS_SSO_KEY, SERVICES_AWS_SSO_PATH)
        download_latest_yaml_from_s3(S3_TWINGATE_KEY, SERVICES_TWINGATE_SSO_PATH)

        twingate_resources = load_config(SERVICES_TWINGATE_SSO_PATH)
        aws_sso_resources = load_config(SERVICES_AWS_SSO_PATH)

        sync_twingate_groups(twingate_resources)
        sync_aws_sso_groups(aws_sso_resources)
    except Exception as e:
        logger.error(f"An error occurred during the main execution: {e}")
        raise


if __name__ == "__main__":
    with app.app_context():
        sync_yaml_owners()
