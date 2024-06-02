import logging
import os
from datetime import datetime, timezone

import yaml
from flask import Flask
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload, selectin_polymorphic, selectinload

from api.extensions import db
from api.models import AppGroup, OktaGroup, OktaUser, OktaUserGroupMember, RoleGroup

from dotenv import load_dotenv

load_dotenv()

# Setup basic configuration and logging
app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URI")
db.init_app(app)
logging.basicConfig(level=logging.INFO)

# Get the environment variables
SERVICES_AWS_SSO = os.path.abspath(os.getenv("SERVICES_AWS_SSO"))
SERVICES_TWINGATE_SSO = os.path.abspath(os.getenv("SERVICES_TWINGATE_SSO"))

def load_config(file_path: str = "path/to/your/config.yml") -> dict:
    """Loads YAML configuration from the specified file path."""
    try:
        with open(file_path, "r") as file:
            return yaml.safe_load(file)
    except FileNotFoundError:
        logging.error(f"Configuration file not found at {file_path}")
        raise
    except yaml.YAMLError as e:
        logging.error(f"Error parsing YAML file: {e}")
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
        logging.error(f"Database error occurred: {e}")
        raise


def add_owner_to_group(group: OktaGroup, owner_email: str) -> None:
    """Adds a new owner to a group if not already an owner."""
    try:
        owner = db.session.query(OktaUser).filter_by(email=owner_email).first()
        if not owner:
            logging.info(f"No user found with email {owner_email}")
            return

        current_time = datetime.now(timezone.utc)
        existing_owner = (
            db.session.query(OktaUserGroupMember)
            .filter_by(group_id=group.id, user_id=owner.id, is_owner=True)
            .filter((OktaUserGroupMember.ended_at == None) | (OktaUserGroupMember.ended_at > current_time))
            .first()
        )

        if existing_owner:
            logging.info(f"User {owner_email} is already an active owner of the group {group.name}")
            return

        new_owner = OktaUserGroupMember(user_id=owner.id, group_id=group.id, is_owner=True)
        db.session.add(new_owner)
        db.session.commit()
        logging.info(f"Added {owner_email} as an owner to the group {group.name}")
    except SQLAlchemyError:
        logging.error(f"Failed to add owner to group: {e}")
        db.session.rollback()
        raise


def add_owners_to_appropriate_twingate_group(resources):
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
        for owner in all_owners:
            # Try first with the prefix
            group_name = f"{twingate_group_prefix}{service_name}"
            group = get_group_by_name(group_name)

            # # If not found, try without the prefix
            # if not group:
            #     group_name = service_name
            #     group = get_group_by_name(group_name)

            # Add to group if it exists
            if group:
                add_owner_to_group(group, owner)
            else:
                logging.info(f"Group {group_name} not found.")


def add_owners_to_aws_sso_group(resources):
    aws_sso_group_prefix = "APP_AWS_SSO_"
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
        for owner in all_owners:
            group_name = service_name
            group = get_group_by_name(group_name)

            # Add to group if it exists
            if group:
                add_owner_to_group(group, owner)
            else:
                logging.info(f"Group {group_name} not found.")


def main():
    """Main function to execute the script logic."""
    twingate_resources = load_config(SERVICES_TWINGATE_SSO)
    aws_sso_resources = load_config(SERVICES_AWS_SSO)

    add_owners_to_appropriate_twingate_group(twingate_resources)
    add_owners_to_aws_sso_group(aws_sso_resources)


if __name__ == "__main__":
    with app.app_context():
        main()
