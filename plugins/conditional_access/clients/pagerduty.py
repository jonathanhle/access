import logging
import os
from typing import AnyStr, List, Tuple

import requests

PAGERDUTY_API_KEY = os.environ["PAGERDUTY_API_KEY"]

logger = logging.getLogger(__name__)


def get_pd_user_id(username: AnyStr) -> AnyStr:
    # Get PagerDuty User ID, if available
    # GET https://api.pagerduty.com/users

    try:
        response = requests.get(
            url="https://api.pagerduty.com/users",
            params={
                "query": username,
            },
            headers={
                "Accept": "application/vnd.pagerduty+json;version=2",
                "Authorization": f"Token token={PAGERDUTY_API_KEY}",
                "Content-Type": "application/json",
            },
        )
        logger.info(f"Response HTTP Status Code: {response.status_code}")
        logger.info(f"Response HTTP Response Body: {response.text}")

        response.raise_for_status()  # Will raise an HTTPError if the HTTP request returned an unsuccessful status code

        # Assuming the response returns a JSON object and the user data structure is correct
        user_data = response.json()
        if "users" in user_data and len(user_data["users"]) > 0:
            return user_data["users"][0]["id"]
        else:
            logger.info("No user found with that username")
            return None

    except requests.exceptions.RequestException as e:
        logger.info(f"HTTP Request failed: {e}")
        return None


def get_pd_user_email(user_id: AnyStr) -> AnyStr:
    try:
        response = requests.get(
            url=f"https://api.pagerduty.com/users/{user_id}",
            headers={
                "Accept": "application/json",
                "Authorization": f"Token token={PAGERDUTY_API_KEY}",
                "Content-Type": "application/json",
            },
        )

        response.raise_for_status()  # Will raise an HTTPError if the HTTP request returned an unsuccessful status code

        user_email = response.json()["user"].get("email", [])

    except requests.exceptions.RequestException as e:
        logger.info(f"HTTP Request failed: {e}")

    return user_email


def get_pd_user_incidents(user_id: AnyStr, search_string: AnyStr) -> List[Tuple[str, str]]:
    # Loop through a User's Active PagerDuty incidents to check if the name
    # or description fields of their Active Incidents contain a string
    # GET https://api.pagerduty.com/incidents

    matching_incidents = []

    try:
        response = requests.get(
            url="https://api.pagerduty.com/incidents",
            params={
                "user_ids[]": user_id,
                "statuses[]": ["acknowledged", "triggered"],
            },
            headers={
                "Accept": "application/json",
                "Authorization": f"Token token={PAGERDUTY_API_KEY}",
                "Content-Type": "application/json",
            },
        )

        response.raise_for_status()  # Will raise an HTTPError if the HTTP request returned an unsuccessful status code

        incidents = response.json().get("incidents", [])
        # PagerDuty's API response for title and description are the same.  They do no expose description for some reason in my tests.
        for incident in incidents:
            if (
                search_string.lower() in incident["service"].get("summary", "").lower()
                or search_string.lower() in incident.get("title", "").lower()
            ):
                parse_incident = {}
                parse_incident["incident_id"] = incident.get("id")
                parse_incident["incident_name"] = incident.get("title")
                parse_incident["incident_html_url"] = incident.get("html_url")
                parse_incident["incident_assignees"] = [
                    (assignee["assignee"]["summary"], assignee["assignee"]["id"])
                    for assignee in incident.get("assignments")
                ]
                parse_incident["incident_assignees_by_email"] = [
                    get_pd_user_email(assignee["assignee"]["id"]) for assignee in incident.get("assignments")
                ]

                matching_incidents.append(parse_incident)

        all_assignees_across_incidents = [
            assignee for incident in matching_incidents for assignee in incident["incident_assignees"]
        ]
        all_assignees_across_incidents = dict(set(all_assignees_across_incidents))

        all_assignees_across_incidents_by_email = list(
            set([assignee for incident in matching_incidents for assignee in incident["incident_assignees_by_email"]])
        )
    except requests.exceptions.RequestException as e:
        logger.info(f"HTTP Request failed: {e}")

    return {
        "matching_incidents": matching_incidents,
        "all_combined_assignees": all_assignees_across_incidents,
        "all_combined_assignees_by_email": all_assignees_across_incidents_by_email,
    }
