import logging
from typing import Optional

from sqlalchemy.orm import joinedload, selectin_polymorphic, selectinload
from sqlalchemy.exc import SQLAlchemyError

from api.extensions import db
from api.models import AppGroup, OktaGroup, OktaUserGroupMember, RoleGroup

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_group_by_name(group_name: str) -> Optional[OktaGroup]:
    """Fetches an active OktaGroup by its name.

    Args:
        group_name (str): The name of the group to fetch.

    Returns:
        Optional[OktaGroup]: The OktaGroup object if found, otherwise None.
    """
    logger.info(f"Starting DB query for group name: {group_name}")
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
        if group:
            logger.info(f"Group found for {group_name}: {group}")
        else:
            logger.info(f"No group found for {group_name}")
        return group
    except SQLAlchemyError as e:
        logger.error(f"Database error occurred while querying group {group_name}: {e}")
        return None
