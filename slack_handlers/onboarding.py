import json
from config import (
    SLACK_APPROVER_CHANNEL_ID,
    JIRA_APPROVED_TRANSITION_ID,
    JIRA_REJECTED_TRANSITION_ID,
)
from services import airtable_service, jira_service, okta_service


def register_onboarding_handlers(app):

    @app.command("/onboard")
    def open_onboarding_modal(ack, body, client):
        ack()

        try:
            employees = airtable_service.get_pending_employees()

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
                        "text": {"type": "plain_text", "text": f"{full_name} — {role}"[:75]},
                        "value": record["id"],
                        "description": {"type": "plain_text", "text": department[:75]},
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
                                "text": "Select a pending employee from Airtable.",
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
            employee_record = airtable_service.get_employee(selected_record_id)
            request_data = airtable_service.record_to_request_data(
                employee_record,
                requested_by=body["user"]["id"],
            )

            jira_issue = jira_service.create_ticket(request_data)
            issue_key = jira_issue["key"]

            airtable_service.update_status(selected_record_id, "Submitted")

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
                text=f"Submitted onboarding request for {request_data['full_name']}. Jira ticket `{issue_key}` was created.",
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
            airtable_service.update_status(airtable_record_id, "Approved")

            okta_user = okta_service.create_user(request_data)
            okta_id = okta_user["id"]

            jira_service.add_comment(
                issue_key,
                f"Approved in Slack by <@{approver}>. Okta user created successfully. Okta user ID: {okta_id}",
            )

            jira_service.transition_issue(issue_key, JIRA_APPROVED_TRANSITION_ID)
            airtable_service.update_status(airtable_record_id, "Provisioned")

            client.chat_update(
                channel=body["channel"]["id"],
                ts=body["message"]["ts"],
                text=f"Approved onboarding for {request_data['full_name']}",
                blocks=[
                    {
                        "type": "header",
                        "text": {"type": "plain_text", "text": "Onboarding approved"},
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

        except Exception as e:
            airtable_service.update_status(airtable_record_id, "Failed")
            jira_service.add_comment(
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

        airtable_service.update_status(airtable_record_id, "Rejected")
        jira_service.add_comment(issue_key, f"Rejected in Slack by <@{rejector}>.")
        jira_service.transition_issue(issue_key, JIRA_REJECTED_TRANSITION_ID)

        client.chat_update(
            channel=body["channel"]["id"],
            ts=body["message"]["ts"],
            text=f"Rejected onboarding for {request_data['full_name']}",
            blocks=[
                {
                    "type": "header",
                    "text": {"type": "plain_text", "text": "Onboarding rejected"},
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