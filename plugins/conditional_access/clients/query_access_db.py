import logging

from sqlalchemy.orm import joinedload, selectin_polymorphic, selectinload

from api.extensions import db
from api.models import AppGroup, OktaGroup, OktaUserGroupMember, RoleGroup

logger = logging.getLogger(__name__)


def get_group_by_name(group_name):
    # Query the database for an OktaGroup record by name
    logger.info(f"Getting DB query for {group_name}")
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
    logger.info(f"Getting DB query for {group_name}: {group}")
    return group
