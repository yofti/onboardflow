import json
import requests
from requests.auth import HTTPBasicAuth
from logging_utils import log_step
from config import (
    JIRA_BASE_URL,
    JIRA_EMAIL,
    JIRA_API_TOKEN,
    JIRA_PROJECT_KEY,
    JIRA_ISSUE_TYPE,
)


def headers():
    return {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def auth():
    return HTTPBasicAuth(JIRA_EMAIL, JIRA_API_TOKEN)


def create_ticket(request_data):
    url = f"{JIRA_BASE_URL}/rest/api/3/issue"

    description_text = (
        f"New onboarding request submitted from Slack.\n\n"
        f"Name: {request_data['full_name']}\n"
        f"Email: {request_data['email']}\n"
        f"Department: {request_data['department']}\n"
        f"Role: {request_data['role']}\n"
        f"Manager: {request_data['manager']}\n"
        f"Start Date: {request_data['start_date']}\n"
        f"Location: {request_data['location']}\n"
        f"Requested access: {', '.join(request_data['access'])}\n"
        f"Airtable Record ID: {request_data['airtable_record_id']}\n"
        f"Requested by Slack user: {request_data['requested_by']}"
    )

    payload = {
        "fields": {
            "project": {"key": JIRA_PROJECT_KEY},
            "summary": f"Onboard new employee: {request_data['full_name']}",
            "description": {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": description_text}],
                    }
                ],
            },
            "issuetype": {"name": JIRA_ISSUE_TYPE},
        }
    }

    response = requests.post(
        url,
        headers=headers(),
        auth=auth(),
        data=json.dumps(payload),
        timeout=20,
    )
    if not response.ok:
        log_step(
            "ERROR",
            "Jira create ticket failed",
            status=response.status_code,
            body=response.text,
        )
    response.raise_for_status()

    return response.json()


def add_comment(issue_key, comment_text):
    url = f"{JIRA_BASE_URL}/rest/api/3/issue/{issue_key}/comment"

    payload = {
        "body": {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": comment_text}],
                }
            ],
        }
    }

    log_step("JIRA", "POST /comment", issue=issue_key)
    response = requests.post(
        url,
        headers=headers(),
        auth=auth(),
        data=json.dumps(payload),
        timeout=20,
    )

    if not response.ok:
        log_step(
            "ERROR",
            "Jira add comment failed",
            status=response.status_code,
            body=response.text,
        )
    response.raise_for_status()
    return response.json()


def transition_issue(issue_key, transition_id):
    if not transition_id:
        print("No Jira transition ID configured. Skipping status transition.")
        return

    url = f"{JIRA_BASE_URL}/rest/api/3/issue/{issue_key}/transitions"

    payload = {"transition": {"id": transition_id}}
    log_step("JIRA", "POST /transitions", issue=issue_key, transition=transition_id)
    response = requests.post(
        url,
        headers=headers(),
        auth=auth(),
        data=json.dumps(payload),
        timeout=20,
    )
    if not response.ok:
        log_step(
            "ERROR",
            "Jira transition failed",
            status=response.status_code,
            body=response.text,
        )
    response.raise_for_status()
