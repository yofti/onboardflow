import os
import json
import requests
from dotenv import load_dotenv
from requests.auth import HTTPBasicAuth
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

load_dotenv()

# -------------------------
# Config
# -------------------------

SLACK_BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]
SLACK_APP_TOKEN = os.environ["SLACK_APP_TOKEN"]
SLACK_APPROVER_CHANNEL_ID = os.environ["SLACK_APPROVER_CHANNEL_ID"]

JIRA_BASE_URL = os.environ["JIRA_BASE_URL"].rstrip("/")
JIRA_EMAIL = os.environ["JIRA_EMAIL"]
JIRA_API_TOKEN = os.environ["JIRA_API_TOKEN"]
JIRA_PROJECT_KEY = os.environ["JIRA_PROJECT_KEY"]
JIRA_ISSUE_TYPE = os.environ.get("JIRA_ISSUE_TYPE", "Task")

# Optional Jira transition IDs
JIRA_APPROVED_TRANSITION_ID = os.environ.get("JIRA_APPROVED_TRANSITION_ID")
JIRA_REJECTED_TRANSITION_ID = os.environ.get("JIRA_REJECTED_TRANSITION_ID")

OKTA_DOMAIN = os.environ["OKTA_DOMAIN"].rstrip("/")
OKTA_API_TOKEN = os.environ["OKTA_API_TOKEN"]

AIRTABLE_API_TOKEN = os.environ["AIRTABLE_API_TOKEN"]
AIRTABLE_BASE_ID = os.environ["AIRTABLE_BASE_ID"]
AIRTABLE_TABLE_NAME = os.environ.get("AIRTABLE_TABLE_NAME", "Employees")

app = App(token=SLACK_BOT_TOKEN)


# -------------------------
# Airtable helpers
# -------------------------

def airtable_headers():
    return {
        "Authorization": f"Bearer {AIRTABLE_API_TOKEN}",
        "Content-Type": "application/json",
    }


def airtable_base_url():
    return f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{AIRTABLE_TABLE_NAME}"


def get_pending_airtable_employees():
    print("Loading pending employees from Airtable...")

    params = {
        "filterByFormula": "{Status} = 'Pending'",
        "maxRecords": 100,
    }

    response = requests.get(
        airtable_base_url(),
        headers=airtable_headers(),
        params=params,
        timeout=20,
    )

    response.raise_for_status()
    return response.json().get("records", [])


def get_airtable_employee(record_id):
    print(f"Loading Airtable employee record {record_id}...")

    url = f"{airtable_base_url()}/{record_id}"

    response = requests.get(
        url,
        headers=airtable_headers(),
        timeout=20,
    )

    response.raise_for_status()
    return response.json()


def update_airtable_status(record_id, status):
    print(f"Updating Airtable status to {status}...")

    url = f"{airtable_base_url()}/{record_id}"

    payload = {
        "fields": {
            "Status": status
        }
    }

    response = requests.patch(
        url,
        headers=airtable_headers(),
        data=json.dumps(payload),
        timeout=20,
    )

    if not response.ok:
        print("Airtable error:", response.text)

    response.raise_for_status()
    return response.json()


def airtable_record_to_request_data(record, requested_by):
    fields = record["fields"]

    return {
        "airtable_record_id": record["id"],
        "full_name": fields.get("Full Name", ""),
        "email": fields.get("Email", ""),
        "department": fields.get("Department", ""),
        "manager": fields.get("Manager", ""),
        "role": fields.get("Role", ""),
        "start_date": fields.get("Start Date", ""),
        "location": fields.get("Location", ""),
        "access": fields.get("Access Profile", []),
        "requested_by": requested_by,
    }


# -------------------------
# Jira helpers
# -------------------------

def jira_headers():
    return {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def jira_auth():
    return HTTPBasicAuth(JIRA_EMAIL, JIRA_API_TOKEN)


def create_jira_ticket(request_data):
    url = f"{JIRA_BASE_URL}/rest/api/3/issue"

    print("Creating Jira ticket...")

    summary = f"Onboard new employee: {request_data['full_name']}"

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

    description = {
        "type": "doc",
        "version": 1,
        "content": [
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": description_text}],
            }
        ],
    }

    payload = {
        "fields": {
            "project": {"key": JIRA_PROJECT_KEY},
            "summary": summary,
            "description": description,
            "issuetype": {"name": JIRA_ISSUE_TYPE},
        }
    }

    response = requests.post(
        url,
        headers=jira_headers(),
        auth=jira_auth(),
        data=json.dumps(payload),
        timeout=20,
    )

    response.raise_for_status()
    return response.json()


def add_jira_comment(issue_key, comment_text):
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

    response = requests.post(
        url,
        headers=jira_headers(),
        auth=jira_auth(),
        data=json.dumps(payload),
        timeout=20,
    )

    response.raise_for_status()
    return response.json()


def transition_jira_issue(issue_key, transition_id):
    if not transition_id:
        print("No Jira transition ID configured. Skipping status transition.")
        return

    print(f"Transitioning Jira issue {issue_key} using transition {transition_id}...")

    url = f"{JIRA_BASE_URL}/rest/api/3/issue/{issue_key}/transitions"

    payload = {
        "transition": {
            "id": transition_id
        }
    }

    response = requests.post(
        url,
        headers=jira_headers(),
        auth=jira_auth(),
        data=json.dumps(payload),
        timeout=20,
    )

    response.raise_for_status()


# -------------------------
# Okta helpers
# -------------------------

def create_okta_user(request_data):
    url = f"{OKTA_DOMAIN}/api/v1/users?activate=false"

    print("Creating Okta user...")

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"SSWS {OKTA_API_TOKEN}",
    }

    first_name, last_name = split_name(request_data["full_name"])

    payload = {
        "profile": {
            "firstName": first_name,
            "lastName": last_name,
            "email": request_data["email"],
            "login": request_data["email"],
            "department": request_data["department"],
            "title": request_data["role"],
        }
    }

    response = requests.post(
        url,
        headers=headers,
        data=json.dumps(payload),
        timeout=20,
    )

    response.raise_for_status()
    return response.json()


def split_name(full_name):
    parts = full_name.strip().split()
    if len(parts) == 1:
        return parts[0], "Employee"
    return parts[0], " ".join(parts[1:])


# -------------------------
# Slack UI
# -------------------------

@app.command("/onboard")
def open_onboarding_modal(ack, body, client):
    ack()

    try:
        employees = get_pending_airtable_employees()

        if not employees:
            client.chat_postEphemeral(
                channel=body["channel_id"],
                user=body["user_id"],
                text="No pending employees found in Airtable.",
            )
            return

        options = []

        for record in employees:
            fields = record.get("fields", {})
            full_name = fields.get("Full Name", "Unknown")
            role = fields.get("Role", "No role")
            department = fields.get("Department", "No department")

            options.append(
                {
                    "text": {
                        "type": "plain_text",
                        "text": f"{full_name} — {role}",
                    },
                    "value": record["id"],
                    "description": {
                        "type": "plain_text",
                        "text": department[:75],
                    },
                }
            )

        client.views_open(
            trigger_id=body["trigger_id"],
            view={
                "type": "modal",
                "callback_id": "onboarding_request_modal",
                "title": {"type": "plain_text", "text": "New Hire Onboarding"},
                "submit": {"type": "plain_text", "text": "Submit"},
                "close": {"type": "plain_text", "text": "Cancel"},
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "Select a pending employee from Airtable."
                        },
                    },
                    {
                        "type": "input",
                        "block_id": "employee_block",
                        "element": {
                            "type": "static_select",
                            "action_id": "employee_select",
                            "placeholder": {
                                "type": "plain_text",
                                "text": "Choose employee",
                            },
                            "options": options,
                        },
                        "label": {"type": "plain_text", "text": "Employee"},
                    },
                ],
            },
        )

    except Exception as e:
        client.chat_postEphemeral(
            channel=body["channel_id"],
            user=body["user_id"],
            text=f"Could not load employees from Airtable: {e}",
        )


@app.view("onboarding_request_modal")
def handle_onboarding_submission(ack, body, client, view):
    ack()

    selected_record_id = view["state"]["values"]["employee_block"]["employee_select"]["selected_option"]["value"]

    try:
        employee_record = get_airtable_employee(selected_record_id)

        request_data = airtable_record_to_request_data(
            employee_record,
            requested_by=body["user"]["id"],
        )

        jira_issue = create_jira_ticket(request_data)
        issue_key = jira_issue["key"]

        update_airtable_status(selected_record_id, "Submitted")

        metadata = {
            "request_data": request_data,
            "jira_issue_key": issue_key,
        }

        client.chat_postMessage(
            channel=SLACK_APPROVER_CHANNEL_ID,
            text=f"Approval needed for onboarding {request_data['full_name']}",
            blocks=[
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": "New onboarding approval needed",
                    },
                },
                {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": f"*Name:*\n{request_data['full_name']}"},
                        {"type": "mrkdwn", "text": f"*Email:*\n{request_data['email']}"},
                        {"type": "mrkdwn", "text": f"*Department:*\n{request_data['department']}"},
                        {"type": "mrkdwn", "text": f"*Role:*\n{request_data['role']}"},
                        {"type": "mrkdwn", "text": f"*Manager:*\n{request_data['manager']}"},
                        {"type": "mrkdwn", "text": f"*Start Date:*\n{request_data['start_date']}"},
                        {"type": "mrkdwn", "text": f"*Location:*\n{request_data['location']}"},
                        {"type": "mrkdwn", "text": f"*Access:*\n{', '.join(request_data['access'])}"},
                        {"type": "mrkdwn", "text": f"*Jira:*\n{issue_key}"},
                    ],
                },
                {
                    "type": "actions",
                    "block_id": "approval_actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "Approve"},
                            "style": "primary",
                            "action_id": "approve_onboarding",
                            "value": json.dumps(metadata),
                        },
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "Reject"},
                            "style": "danger",
                            "action_id": "reject_onboarding",
                            "value": json.dumps(metadata),
                        },
                    ],
                },
            ],
        )

        client.chat_postEphemeral(
            channel=body["user"]["id"],
            user=body["user"]["id"],
            text=f"Submitted onboarding request for {request_data['full_name']}. Jira ticket `{issue_key}` was created and Airtable status was updated to `Submitted`.",
        )

    except Exception as e:
        client.chat_postEphemeral(
            channel=body["user"]["id"],
            user=body["user"]["id"],
            text=f"Something went wrong while submitting the onboarding request: {e}",
        )


@app.action("approve_onboarding")
def approve_onboarding(ack, body, client):
    ack()

    approver = body["user"]["id"]
    metadata = json.loads(body["actions"][0]["value"])
    request_data = metadata["request_data"]
    issue_key = metadata["jira_issue_key"]
    airtable_record_id = request_data["airtable_record_id"]

    try:
        update_airtable_status(airtable_record_id, "Approved")

        okta_user = create_okta_user(request_data)
        okta_id = okta_user["id"]

        add_jira_comment(
            issue_key,
            f"Approved in Slack by <@{approver}>. Okta user created successfully. Okta user ID: {okta_id}",
        )

        transition_jira_issue(issue_key, JIRA_APPROVED_TRANSITION_ID)

        update_airtable_status(airtable_record_id, "Provisioned")

        client.chat_update(
            channel=body["channel"]["id"],
            ts=body["message"]["ts"],
            text=f"Approved onboarding for {request_data['full_name']}",
            blocks=[
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": "Onboarding approved",
                    },
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            f"*Employee:* {request_data['full_name']}\n"
                            f"*Email:* {request_data['email']}\n"
                            f"*Role:* {request_data['role']}\n"
                            f"*Jira:* `{issue_key}`\n"
                            f"*Okta user ID:* `{okta_id}`\n"
                            f"*Airtable Status:* `Provisioned`\n"
                            f"*Approved by:* <@{approver}>"
                        ),
                    },
                },
            ],
        )

        client.chat_postMessage(
            channel=SLACK_APPROVER_CHANNEL_ID,
            text=(
                f"✅ Onboarding completed for {request_data['full_name']}. "
                f"Jira `{issue_key}` updated, Okta user `{okta_id}` created, and Airtable marked `Provisioned`."
            ),
        )

    except Exception as e:
        update_airtable_status(airtable_record_id, "Failed")

        add_jira_comment(
            issue_key,
            f"Approval clicked by Slack user {approver}, but automation failed: {e}",
        )

        client.chat_postMessage(
            channel=SLACK_APPROVER_CHANNEL_ID,
            text=f"❌ Onboarding failed for {request_data['full_name']}: {e}",
        )


@app.action("reject_onboarding")
def reject_onboarding(ack, body, client):
    ack()

    rejector = body["user"]["id"]
    metadata = json.loads(body["actions"][0]["value"])
    request_data = metadata["request_data"]
    issue_key = metadata["jira_issue_key"]
    airtable_record_id = request_data["airtable_record_id"]

    update_airtable_status(airtable_record_id, "Rejected")

    add_jira_comment(
        issue_key,
        f"Rejected in Slack by <@{rejector}>.",
    )

    transition_jira_issue(issue_key, JIRA_REJECTED_TRANSITION_ID)

    client.chat_update(
        channel=body["channel"]["id"],
        ts=body["message"]["ts"],
        text=f"Rejected onboarding for {request_data['full_name']}",
        blocks=[
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "Onboarding rejected",
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*Employee:* {request_data['full_name']}\n"
                        f"*Jira:* `{issue_key}`\n"
                        f"*Airtable Status:* `Rejected`\n"
                        f"*Rejected by:* <@{rejector}>"
                    ),
                },
            },
        ],
    )


if __name__ == "__main__":
    print("Starting Nametag Mock POC onboarding app in Slack Socket Mode...")
    SocketModeHandler(app, SLACK_APP_TOKEN).start()