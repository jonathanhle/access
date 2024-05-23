from __future__ import print_function

import logging
from typing import List, Optional

import pluggy
from clients.pagerduty import get_pd_user_id, get_pd_user_incidents
from clients.query_access_db import get_group_by_name
from clients.yaml_aws_sso import find_first_matching_service

from api.models import AccessRequest, OktaGroup, OktaUser, Tag
from api.plugins import ConditionalAccessResponse

request_hook_impl = pluggy.HookimplMarker("access_conditional_access")
logger = logging.getLogger(__name__)


@request_hook_impl
def access_request_created(
    access_request: AccessRequest, group: OktaGroup, group_tags: List[Tag], requester: OktaUser
) -> Optional[ConditionalAccessResponse]:
    """Auto-approve memberships to the Auto-Approved-Group group"""

    # Require the request not be for Group Ownership and has a request reason
    if not access_request.request_ownership and access_request.request_reason:
        # -----------------------------------------------------------
        # Gather Request, User and Group Attributes that we may use to make decisions on
        # -----------------------------------------------------------
        requester_active_group_ownerships = [grp.group.name for grp in requester.active_group_ownerships]
        requester_username = requester.profile["Username"]
        logger.info(f"requester_username is: {requester_username}")

        pd_user_id = get_pd_user_id(requester_username)
        print(f"pd_user_id are: {pd_user_id}")
        if pd_user_id:
            active_incidents = get_pd_user_incidents(pd_user_id, group.name)
            print(f"active_incidents are: {active_incidents}")

            if active_incidents:
                active_incidents_all_combined_assignees_by_email = active_incidents["all_combined_assignees_by_email"]
                active_incidents_matching_incidents = active_incidents["matching_incidents"]

        yaml_service = find_first_matching_service(group.name)
        print(f"yaml_service is {yaml_service}")
        if yaml_service:
            # -----------------------------------------------------------
            # NON-SENSITIVE ACCESS ATTRIBUTES
            # -----------------------------------------------------------
            yaml_service_non_sensitive_access_enabled = (
                yaml_service.get("access_rules", {})
                .get("auto_approval", {})
                .get("non_sensitive_access", {})
                .get("enabled", False)
            )
            yaml_service_non_sensitive_access_groups = (
                yaml_service.get("access_rules", {})
                .get("auto_approval", {})
                .get("non_sensitive_access", {})
                .get("okta_groups", [])
            )
            yaml_service_non_sensitive_access_users = (
                yaml_service.get("access_rules", {})
                .get("auto_approval", {})
                .get("non_sensitive_access", {})
                .get("okta_users", [])
            )

            if yaml_service_non_sensitive_access_enabled:
                # Get Set of non-sensitive-approved-users
                yaml_service_non_sensitive_members = set(
                    [
                        member.user.email
                        for group in yaml_service_non_sensitive_access_groups
                        for member in get_group_by_name(group).active_user_memberships
                    ]
                    + yaml_service_non_sensitive_access_users
                )
                logger.info(f"Non Sensitive Access memebrs are: {yaml_service_non_sensitive_members}")
            else:
                logger.info("Non-sensitive access is not enabled.")
            # -----------------------------------------------------------
            # SYSTEM OWNERS ACCESS ATTRIBUTES
            # -----------------------------------------------------------
            yaml_service_system_owners_enabled = (
                yaml_service.get("access_rules", {})
                .get("auto_approval", {})
                .get("system_owners", {})
                .get("enabled", False)
            )
            yaml_service_system_owners_groups = (
                yaml_service.get("access_rules", {})
                .get("auto_approval", {})
                .get("system_owners", {})
                .get("okta_groups", [])
            )
            yaml_service_system_owners_users = (
                yaml_service.get("access_rules", {})
                .get("auto_approval", {})
                .get("system_owners", {})
                .get("okta_users", [])
            )

            if yaml_service_system_owners_enabled:
                # Get Set of system owners users
                yaml_service_system_owners_members = set(
                    [
                        member.user.email
                        for group in yaml_service_system_owners_groups
                        for member in get_group_by_name(group).active_user_memberships
                    ]
                    + yaml_service_system_owners_users
                )
                logger.info(f"System owners are: {yaml_service_system_owners_members}")
            else:
                logger.info("System owners access is not enabled.")
            # -----------------------------------------------------------
            # EMERGENCY ACCESS ATTRIBUTES
            # -----------------------------------------------------------
            yaml_service_emergency_access_enabled = (
                yaml_service.get("access_rules", {}).get("emergency_access", {}).get("enabled", False)
            )
            yaml_service_emergency_access_groups = (
                yaml_service.get("access_rules", {}).get("emergency_access", {}).get("okta_groups", [])
            )
            yaml_service_emergency_access_users = (
                yaml_service.get("access_rules", {}).get("emergency_access", {}).get("okta_users", [])
            )
            # Get Set of emergency_access approved users
            yaml_service_emergency_access_members = set(
                [
                    member.user.email
                    for group in yaml_service_emergency_access_groups
                    for member in get_group_by_name(group).active_user_memberships
                ]
                + yaml_service_emergency_access_users
            )

            if yaml_service_emergency_access_enabled:
                # Get Set of emergency access approved users
                yaml_service_emergency_access_members = set(
                    [
                        member.user.email
                        for group in yaml_service_emergency_access_groups
                        for member in get_group_by_name(group).active_user_memberships
                    ]
                    + yaml_service_emergency_access_users
                )
                logger.info(f"Emergency Access members are: {yaml_service_emergency_access_members}")
            else:
                logger.info("Emergency access is not enabled.")
        # -----------------------------------------------------------
        # Group Name is "Auto-Approved-Group"
        # -----------------------------------------------------------
        if group.name == "Auto-Approved-Group":
            logger.info(f"Auto-approving access request {access_request.id} to group {group.name}")
            return ConditionalAccessResponse(
                approved=True, reason="Group membership auto-approved", ending_at=access_request.request_ending_at
            )
        # -----------------------------------------------------------
        # Group is tagged with a Discord Access type tag of "AutoApprove"
        # -----------------------------------------------------------
        elif "AutoApprove" in [tag.name for tag in group_tags]:
            logger.info(f"Auto-approving access request {access_request.id} to group {group.name}")
            return ConditionalAccessResponse(
                approved=True,
                reason="Group membership auto-approved by Tag",
                ending_at=access_request.request_ending_at,
            )
        # -----------------------------------------------------------
        # Auto-Approve Access Requests if Requester is in Discord Access Ownership Group
        # -----------------------------------------------------------
        elif group.name in requester_active_group_ownerships:
            logger.info(f"Auto-approving access request {access_request.id} to group {group.name}")
            return ConditionalAccessResponse(
                approved=True,
                reason="Group membership auto-approved by because requester is Access Group owner",
                ending_at=access_request.request_ending_at,
            )
        # -----------------------------------------------------------
        # AutoApproval Logic if non_sensitive_access is True and they're in the Membership of the Access Rule
        # -----------------------------------------------------------
        elif yaml_service_non_sensitive_access_enabled and requester_username in yaml_service_non_sensitive_members:
            logger.info(f"Auto-approving access request {access_request.id} to group {group.name}")
            return ConditionalAccessResponse(
                approved=True,
                reason="Group membership auto-approved by because non_sensitive_access auto approval is enabled on access_control",
                ending_at=access_request.request_ending_at,
            )
        # -----------------------------------------------------------
        # Auto-Approve Access Requests if Requester has an Active PagerDuty incident for the PD Service representing that Group
        # and is a member of the emergency_access access rules for the service
        # -----------------------------------------------------------
        elif pd_user_id:
            if (
                active_incidents
                and requester_username in active_incidents_all_combined_assignees_by_email
                and yaml_service_emergency_access_enabled
                and requester_username in yaml_service_emergency_access_members
            ):
                logger.info(f"Auto-approving access request {access_request.id} to group {group.name}")
                return ConditionalAccessResponse(
                    approved=True,
                    reason=f"Group membership auto-approved by active PagerDuty Incident(s): {active_incidents_matching_incidents}",
                    ending_at=access_request.request_ending_at,
                )
        # -----------------------------------------------------------
        # AutoApproval Logic if system_owners is True and they're in the Membership of the Access Rule
        # -----------------------------------------------------------
        elif yaml_service_system_owners_enabled and requester_username in yaml_service_system_owners_members:
            logger.info(f"Auto-approving access request {access_request.id} to group {group.name}")
            return ConditionalAccessResponse(
                approved=True,
                reason="Group membership auto-approved by because system_owners auto approval is enabled on access_control",
                ending_at=access_request.request_ending_at,
            )
    else:
        logger.info(f"Access request {access_request.id} to group {group.name} requires manual approval")

    return None
