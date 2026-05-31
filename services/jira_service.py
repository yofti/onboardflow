import json
import requests
from requests.auth import HTTPBasicAuth
from logging_utils import log_step
from config import JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN, JIRA_PROJECT_KEY, JIRA_ISSUE_TYPE

def headers():
    return {"Accept": "application/json", "Content-Type": "application/json"}

def auth():
    return HTTPBasicAuth(JIRA_EMAIL, JIRA_API_TOKEN)

def adf_text(text):
    return {"type": "doc", "version": 1, "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}]}

def create_ticket(request_data):
    """Creates the parent onboarding ticket."""
    url = f"{JIRA_BASE_URL}/rest/api/3/issue"
    log_step("JIRA", "Creating parent onboarding ticket", employee=request_data["full_name"], project=JIRA_PROJECT_KEY, issue_type=JIRA_ISSUE_TYPE)
    description_text = (
        f"Parent onboarding request submitted from Slack.\n\n"
        f"Employee: {request_data['full_name']}\n"
        f"Email: {request_data['email']}\n"
        f"Department: {request_data['department']}\n"
        f"Role: {request_data['role']}\n"
        f"Manager: {request_data['manager']}\n"
        f"Start Date: {request_data['start_date']}\n"
        f"Location: {request_data['location']}\n"
        f"Requested Access Profiles: {', '.join(request_data['access'])}\n"
        f"Airtable Record ID: {request_data['airtable_record_id']}\n"
        f"Requested by Slack user: {request_data['requested_by']}\n\n"
        f"Child tickets will be created for each individual access profile to provide a granular audit trail."
    )
    payload = {"fields": {"project": {"key": JIRA_PROJECT_KEY}, "summary": f"Parent onboarding request: {request_data['full_name']}", "description": adf_text(description_text), "issuetype": {"name": JIRA_ISSUE_TYPE}, "labels": ["onboarding-parent"]}}
    response = requests.post(url, headers=headers(), auth=auth(), data=json.dumps(payload), timeout=20)
    if not response.ok:
        log_step("ERROR", "Jira parent ticket creation failed", status=response.status_code, body=response.text)
    response.raise_for_status()
    issue = response.json()
    log_step("JIRA", "Parent onboarding ticket created", issue=issue["key"])
    return issue

def create_access_ticket(request_data, access_name, owner_team, parent_issue_key):
    """Creates one granular Jira ticket per individual access profile."""
    url = f"{JIRA_BASE_URL}/rest/api/3/issue"
    log_step("JIRA", "Creating child access ticket", employee=request_data["full_name"], access=access_name, owner_team=owner_team, parent=parent_issue_key)
    description_text = (
        f"Granular access approval request.\n\n"
        f"Employee: {request_data['full_name']}\n"
        f"Email: {request_data['email']}\n"
        f"Department: {request_data['department']}\n"
        f"Role: {request_data['role']}\n"
        f"Manager: {request_data['manager']}\n"
        f"Start Date: {request_data['start_date']}\n"
        f"Location: {request_data['location']}\n\n"
        f"Access Profile Requested: {access_name}\n"
        f"Approval Owner Team: {owner_team}\n"
        f"Parent Onboarding Ticket: {parent_issue_key}\n"
        f"Airtable Record ID: {request_data['airtable_record_id']}\n\n"
        f"Audit purpose: This ticket records that {request_data['full_name']} requested {access_name}, owned by {owner_team}, as part of parent onboarding request {parent_issue_key}."
    )
    labels = ["onboarding-access", f"owner-{owner_team.lower().replace(' ', '-')}", f"access-{access_name.lower().replace(' ', '-').replace('/', '-')}"]
    payload = {"fields": {"project": {"key": JIRA_PROJECT_KEY}, "summary": f"{access_name} access approval: {request_data['full_name']}", "description": adf_text(description_text), "issuetype": {"name": JIRA_ISSUE_TYPE}, "labels": labels}}
    response = requests.post(url, headers=headers(), auth=auth(), data=json.dumps(payload), timeout=20)
    if not response.ok:
        log_step("ERROR", "Jira child access ticket creation failed", status=response.status_code, body=response.text, access=access_name, owner_team=owner_team, parent=parent_issue_key)
    response.raise_for_status()
    issue = response.json()
    log_step("JIRA", "Child access ticket created", issue=issue["key"], access=access_name, owner_team=owner_team, parent=parent_issue_key)
    return issue

def add_comment(issue_key, comment_text):
    url = f"{JIRA_BASE_URL}/rest/api/3/issue/{issue_key}/comment"
    log_step("JIRA", "Adding Jira comment", issue=issue_key)
    response = requests.post(url, headers=headers(), auth=auth(), data=json.dumps({"body": adf_text(comment_text)}), timeout=20)
    if not response.ok:
        log_step("ERROR", "Jira add comment failed", status=response.status_code, body=response.text, issue=issue_key)
    response.raise_for_status()
    log_step("JIRA", "Jira comment added", issue=issue_key)
    return response.json()

def list_available_transitions(issue_key):
    url = f"{JIRA_BASE_URL}/rest/api/3/issue/{issue_key}/transitions"
    log_step("JIRA", "Fetching available transitions", issue=issue_key)
    response = requests.get(url, headers=headers(), auth=auth(), timeout=20)
    if not response.ok:
        log_step("ERROR", "Could not fetch Jira transitions", status=response.status_code, body=response.text)
    response.raise_for_status()
    transitions = response.json().get("transitions", [])
    if not transitions:
        log_step("JIRA", "No transitions available", issue=issue_key)
    else:
        for transition in transitions:
            to_status = transition.get("to", {}).get("name", "Unknown")
            log_step("JIRA", "Available transition", issue=issue_key, transition_id=transition.get("id"), transition_name=transition.get("name"), to_status=to_status)
    return transitions

def transition_issue(issue_key, transition_id):
    if not transition_id:
        log_step("JIRA", "No Jira transition ID configured. Skipping transition.", issue=issue_key)
        list_available_transitions(issue_key)
        return
    transition_id = str(transition_id).strip()
    log_step("JIRA", "Attempting Jira transition", issue=issue_key, transition_id=transition_id)
    list_available_transitions(issue_key)
    url = f"{JIRA_BASE_URL}/rest/api/3/issue/{issue_key}/transitions"
    response = requests.post(url, headers=headers(), auth=auth(), data=json.dumps({"transition": {"id": transition_id}}), timeout=20)
    if not response.ok:
        log_step("ERROR", "Jira transition failed", issue=issue_key, transition_id=transition_id, status=response.status_code, body=response.text)
    response.raise_for_status()
    log_step("JIRA", "Jira transition successful", issue=issue_key, transition_id=transition_id)
