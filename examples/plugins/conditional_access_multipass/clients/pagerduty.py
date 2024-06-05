import logging
import os
from typing import AnyStr, Dict, List, Optional, Tuple, Union

import requests

PAGERDUTY_API_KEY = os.environ.get("PAGERDUTY_API_KEY")
if not PAGERDUTY_API_KEY:
    raise EnvironmentError("PAGERDUTY_API_KEY environment variable not set")

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def get_pd_user_id(username: AnyStr) -> Optional[AnyStr]:
    """Get PagerDuty User ID by username.

    Args:
        username (AnyStr): The username to search for.

    Returns:
        Optional[AnyStr]: The user ID if found, otherwise None.
    """
    try:
        response = requests.get(
            url="https://api.pagerduty.com/users",
            params={"query": username},
            headers={
                "Accept": "application/vnd.pagerduty+json;version=2",
                "Authorization": f"Token token={PAGERDUTY_API_KEY}",
                "Content-Type": "application/json",
            },
        )
        logger.info(f"Response HTTP Status Code: {response.status_code}")
        logger.info(f"Response HTTP Response Body: {response.text}")

        response.raise_for_status()

        user_data = response.json()
        if "users" in user_data and user_data["users"]:
            return user_data["users"][0]["id"]
        else:
            logger.info("No user found with that username")
            return None
    except requests.exceptions.RequestException as e:
        logger.error(f"HTTP Request failed: {e}")
        return None


def get_pd_user_email(user_id: AnyStr) -> Optional[AnyStr]:
    """Get PagerDuty User email by user ID.

    Args:
        user_id (AnyStr): The user ID to search for.

    Returns:
        Optional[AnyStr]: The user email if found, otherwise None.
    """
    try:
        response = requests.get(
            url=f"https://api.pagerduty.com/users/{user_id}",
            headers={
                "Accept": "application/json",
                "Authorization": f"Token token={PAGERDUTY_API_KEY}",
                "Content-Type": "application/json",
            },
        )

        response.raise_for_status()

        user_email = response.json().get("user", {}).get("email")
        if user_email:
            return user_email
        else:
            logger.info(f"No email found for user ID: {user_id}")
            return None
    except requests.exceptions.RequestException as e:
        logger.error(f"HTTP Request failed: {e}")
        return None


def get_pd_user_incidents(
    user_id: AnyStr, search_string: AnyStr
) -> Dict[str, Union[List[Dict[str, AnyStr]], List[Tuple[str, str]], List[AnyStr]]]:
    """Get a User's Active PagerDuty incidents containing a search string.

    Args:
        user_id (AnyStr): The user ID to search for incidents.
        search_string (AnyStr): The string to search for in incident summaries and titles.

    Returns:
        Dict[str, Union[List[Dict[str, AnyStr]], List[Tuple[str, str]], List[AnyStr]]]: A dictionary containing matching incidents,
                                                                                   all combined assignees, and all combined assignees by email.
    """
    matching_incidents = []
    all_assignees_across_incidents = []
    all_assignees_across_incidents_by_email = []

    try:
        response = requests.get(
            url="https://api.pagerduty.com/incidents",
            params={"user_ids[]": user_id, "statuses[]": ["acknowledged", "triggered"]},
            headers={
                "Accept": "application/json",
                "Authorization": f"Token token={PAGERDUTY_API_KEY}",
                "Content-Type": "application/json",
            },
        )

        response.raise_for_status()

        incidents = response.json().get("incidents", [])
        for incident in incidents:
            if (
                search_string.lower() in incident["service"].get("summary", "").lower()
                or search_string.lower() in incident.get("title", "").lower()
            ):
                parse_incident = {
                    "incident_id": incident.get("id"),
                    "incident_name": incident.get("title"),
                    "incident_html_url": incident.get("html_url"),
                    "incident_assignees": [
                        (assignee["assignee"]["summary"], assignee["assignee"]["id"])
                        for assignee in incident.get("assignments", [])
                    ],
                    "incident_assignees_by_email": [
                        get_pd_user_email(assignee["assignee"]["id"]) for assignee in incident.get("assignments", [])
                    ],
                }

                matching_incidents.append(parse_incident)

        all_assignees_across_incidents = [
            assignee for incident in matching_incidents for assignee in incident["incident_assignees"]
        ]
        all_assignees_across_incidents = dict(set(all_assignees_across_incidents))

        all_assignees_across_incidents_by_email = list(
            set([assignee for incident in matching_incidents for assignee in incident["incident_assignees_by_email"]])
        )
    except requests.exceptions.RequestException as e:
        logger.error(f"HTTP Request failed: {e}")

    return {
        "matching_incidents": matching_incidents,
        "all_combined_assignees": all_assignees_across_incidents,
        "all_combined_assignees_by_email": all_assignees_across_incidents_by_email,
    }
