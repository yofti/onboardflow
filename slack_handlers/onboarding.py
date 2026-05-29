import json

from config import (
    SLACK_APPROVER_CHANNEL_ID,
    JIRA_APPROVED_TRANSITION_ID,
    JIRA_REJECTED_TRANSITION_ID,
)
from logging_utils import log_step
from services import airtable_service, jira_service, okta_service


def format_access(access):
    if not access:
        return "None selected"
    if isinstance(access, list):
        return ", ".join(access)
    return str(access)


def employee_summary_blocks(request_data):
    """
    Full employee preview used before approval and after selection.
    """
    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "*Employee profile pulled from Airtable*",
            },
        },
        {
            "type": "section",
            "fields": [
                {
                    "type": "mrkdwn",
                    "text": f"*Name:*\n{request_data.get('full_name', '')}",
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Email:*\n{request_data.get('email', '')}",
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Department:*\n{request_data.get('department', '')}",
                },
                {"type": "mrkdwn", "text": f"*Role:*\n{request_data.get('role', '')}"},
                {
                    "type": "mrkdwn",
                    "text": f"*Manager:*\n{request_data.get('manager', '')}",
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Start Date:*\n{request_data.get('start_date', '')}",
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Location:*\n{request_data.get('location', '')}",
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Requested Access:*\n{format_access(request_data.get('access'))}",
                },
            ],
        },
    ]


def register_onboarding_handlers(app):

    @app.command("/onboard")
    def open_onboarding_modal(ack, body, client):
        ack()

        user_id = body["user_id"]
        channel_id = body["channel_id"]

        log_step("SLACK", "Received /onboard command", user=user_id, channel=channel_id)

        try:
            log_step("AIRTABLE", "Loading pending employees")
            employees = airtable_service.get_pending_employees()
            log_step("AIRTABLE", "Loaded pending employees", count=len(employees))

            if not employees:
                client.chat_postEphemeral(
                    channel=channel_id,
                    user=user_id,
                    text="No pending employees found in Airtable.",
                )
                return

            options = []
            for record in employees[:100]:
                fields = record.get("fields", {})
                full_name = fields.get("Full Name", "Unknown")
                role = fields.get("Role", "No role")
                department = fields.get("Department", "No department")
                start_date = fields.get("Start Date", "No start date")

                options.append(
                    {
                        "text": {
                            "type": "plain_text",
                            "text": f"{full_name} — {role}"[:75],
                        },
                        "value": record["id"],
                        "description": {
                            "type": "plain_text",
                            "text": f"{department} • {start_date}"[:75],
                        },
                    }
                )

            log_step("SLACK", "Opening employee selection modal", options=len(options))

            client.views_open(
                trigger_id=body["trigger_id"],
                view={
                    "type": "modal",
                    "callback_id": "onboarding_request_modal",
                    "title": {"type": "plain_text", "text": "New Hire Onboarding"},
                    "submit": {"type": "plain_text", "text": "Preview"},
                    "close": {"type": "plain_text", "text": "Cancel"},
                    "blocks": [
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": (
                                    "Select a pending employee from Airtable.\n"
                                    "After you click *Preview*, I’ll show the full profile before sending for approval."
                                ),
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
            log_step("ERROR", "Could not load employees from Airtable", error=e)
            client.chat_postEphemeral(
                channel=channel_id,
                user=user_id,
                text=f"Could not load employees from Airtable: {e}",
            )

    @app.view("onboarding_request_modal")
    def handle_onboarding_preview(ack, body, client, view):
        """
        First modal submit does NOT create Jira yet.
        It loads the Airtable record and shows the full employee profile for confirmation.
        """
        ack()

        user_id = body["user"]["id"]
        selected_record_id = view["state"]["values"]["employee_block"][
            "employee_select"
        ]["selected_option"]["value"]

        log_step(
            "SLACK",
            "Employee selected for preview",
            user=user_id,
            airtable_record=selected_record_id,
        )

        try:
            log_step(
                "AIRTABLE",
                "Loading selected employee record",
                record=selected_record_id,
            )
            employee_record = airtable_service.get_employee(selected_record_id)

            request_data = airtable_service.record_to_request_data(
                employee_record,
                requested_by=user_id,
            )

            log_step(
                "SLACK",
                "Opening full employee preview modal",
                employee=request_data["full_name"],
                email=request_data["email"],
            )

            client.views_open(
                trigger_id=body["trigger_id"],
                view={
                    "type": "modal",
                    "callback_id": "confirm_onboarding_modal",
                    "private_metadata": json.dumps(request_data),
                    "title": {"type": "plain_text", "text": "Confirm Onboarding"},
                    "submit": {"type": "plain_text", "text": "Send Approval"},
                    "close": {"type": "plain_text", "text": "Back"},
                    "blocks": employee_summary_blocks(request_data)
                    + [
                        {
                            "type": "divider",
                        },
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": (
                                    "*Next steps after confirmation:*\n"
                                    "1. Create Jira ticket\n"
                                    "2. Mark Airtable as `Submitted`\n"
                                    "3. Post Slack approval request\n"
                                    "4. Wait for approver decision"
                                ),
                            },
                        },
                    ],
                },
            )

        except Exception as e:
            log_step("ERROR", "Could not preview employee", error=e)
            client.chat_postMessage(
                channel=user_id,
                text=f"Could not preview employee from Airtable: {e}",
            )

    @app.view("confirm_onboarding_modal")
    def handle_onboarding_submission(ack, body, client, view):
        ack()

        request_data = json.loads(view["private_metadata"])
        user_id = body["user"]["id"]

        log_step(
            "WORKFLOW",
            "Starting onboarding submission",
            employee=request_data["full_name"],
            email=request_data["email"],
        )

        try:
            client.chat_postMessage(
                channel=user_id,
                text=f"⏳ Starting onboarding workflow for *{request_data['full_name']}*...",
            )

            log_step("JIRA", "Creating Jira ticket", employee=request_data["full_name"])
            jira_issue = jira_service.create_ticket(request_data)
            issue_key = jira_issue["key"]
            log_step("JIRA", "Created Jira ticket", issue=issue_key)

            client.chat_postMessage(
                channel=user_id,
                text=f"✅ Jira ticket `{issue_key}` created.",
            )

            log_step(
                "AIRTABLE",
                "Updating Airtable status",
                status="Submitted",
                record=request_data["airtable_record_id"],
            )
            airtable_service.update_status(
                request_data["airtable_record_id"], "Submitted"
            )
            log_step("AIRTABLE", "Airtable status updated", status="Submitted")

            client.chat_postMessage(
                channel=user_id,
                text="✅ Airtable status updated to `Submitted`.",
            )

            metadata = {
                "request_data": request_data,
                "jira_issue_key": issue_key,
            }

            approval_blocks = [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": "New onboarding approval needed",
                    },
                },
                *employee_summary_blocks(request_data),
                {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": f"*Jira Ticket:*\n`{issue_key}`"},
                        {"type": "mrkdwn", "text": f"*Requested By:*\n<@{user_id}>"},
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
            ]

            log_step(
                "SLACK",
                "Posting approval request",
                channel=SLACK_APPROVER_CHANNEL_ID,
                issue=issue_key,
            )
            client.chat_postMessage(
                channel=SLACK_APPROVER_CHANNEL_ID,
                text=f"Approval needed for onboarding {request_data['full_name']}",
                blocks=approval_blocks,
            )

            log_step(
                "WORKFLOW", "Submission complete. Waiting for approval", issue=issue_key
            )

            client.chat_postMessage(
                channel=user_id,
                text=(
                    f"✅ Approval request posted for *{request_data['full_name']}*.\n"
                    f"Current state: waiting for Slack approval."
                ),
            )

        except Exception as e:
            log_step(
                "ERROR",
                "Workflow submission failed",
                employee=request_data.get("full_name"),
                error=e,
            )
            client.chat_postMessage(
                channel=user_id,
                text=f"❌ Something went wrong while submitting onboarding for {request_data['full_name']}: {e}",
            )

    @app.action("approve_onboarding")
    def approve_onboarding(ack, body, client):
        ack()

        approver = body["user"]["id"]
        metadata = json.loads(body["actions"][0]["value"])
        request_data = metadata["request_data"]
        issue_key = metadata["jira_issue_key"]
        airtable_record_id = request_data["airtable_record_id"]

        log_step(
            "APPROVAL",
            "Approve button clicked",
            approver=approver,
            employee=request_data["full_name"],
            issue=issue_key,
        )

        try:
            client.chat_update(
                channel=body["channel"]["id"],
                ts=body["message"]["ts"],
                text=f"Processing approval for {request_data['full_name']}",
                blocks=[
                    {
                        "type": "header",
                        "text": {
                            "type": "plain_text",
                            "text": "Processing onboarding approval",
                        },
                    },
                    *employee_summary_blocks(request_data),
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": (
                                f"⏳ Approved by <@{approver}>.\n"
                                "Now creating Okta user, updating Jira, and updating Airtable..."
                            ),
                        },
                    },
                ],
            )

            log_step(
                "AIRTABLE",
                "Updating Airtable status",
                status="Approved",
                record=airtable_record_id,
            )
            airtable_service.update_status(airtable_record_id, "Approved")
            log_step("AIRTABLE", "Airtable status updated", status="Approved")

            log_step(
                "OKTA",
                "Creating Okta user",
                employee=request_data["full_name"],
                email=request_data["email"],
            )
            okta_user = okta_service.create_user(request_data)
            okta_id = okta_user["id"]
            log_step("OKTA", "Created Okta user", okta_id=okta_id)

            log_step("JIRA", "Adding approval comment", issue=issue_key)
            jira_service.add_comment(
                issue_key,
                f"Approved in Slack by <@{approver}>. Okta user created successfully. Okta user ID: {okta_id}",
            )
            log_step("JIRA", "Approval comment added", issue=issue_key)

            log_step(
                "JIRA",
                "Transitioning Jira issue",
                issue=issue_key,
                transition=JIRA_APPROVED_TRANSITION_ID,
            )
            jira_service.transition_issue(issue_key, JIRA_APPROVED_TRANSITION_ID)
            log_step("JIRA", "Jira transition attempted", issue=issue_key)

            log_step(
                "AIRTABLE",
                "Updating Airtable status",
                status="Provisioned",
                record=airtable_record_id,
            )
            airtable_service.update_status(airtable_record_id, "Provisioned")
            log_step("AIRTABLE", "Airtable status updated", status="Provisioned")

            log_step(
                "WORKFLOW",
                "Onboarding workflow completed",
                employee=request_data["full_name"],
                issue=issue_key,
            )

            client.chat_update(
                channel=body["channel"]["id"],
                ts=body["message"]["ts"],
                text=f"Approved onboarding for {request_data['full_name']}",
                blocks=[
                    {
                        "type": "header",
                        "text": {
                            "type": "plain_text",
                            "text": "Onboarding approved and provisioned",
                        },
                    },
                    *employee_summary_blocks(request_data),
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": (
                                f"✅ *Workflow complete*\n"
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
                    f"✅ Onboarding completed for *{request_data['full_name']}*.\n"
                    f"Jira `{issue_key}` updated, Okta user `{okta_id}` created, "
                    f"and Airtable marked `Provisioned`."
                ),
            )

        except Exception as e:
            log_step(
                "ERROR",
                "Approval workflow failed",
                employee=request_data["full_name"],
                issue=issue_key,
                error=e,
            )

            try:
                airtable_service.update_status(airtable_record_id, "Failed")
            except Exception as airtable_error:
                log_step(
                    "ERROR", "Could not mark Airtable as Failed", error=airtable_error
                )

            try:
                jira_service.add_comment(
                    issue_key,
                    f"Approval clicked by Slack user {approver}, but automation failed: {e}",
                )
            except Exception as jira_error:
                log_step(
                    "ERROR", "Could not add Jira failure comment", error=jira_error
                )

            client.chat_postMessage(
                channel=SLACK_APPROVER_CHANNEL_ID,
                text=f"❌ Onboarding failed for *{request_data['full_name']}*: {e}",
            )

    @app.action("reject_onboarding")
    def reject_onboarding(ack, body, client):
        ack()

        rejector = body["user"]["id"]
        metadata = json.loads(body["actions"][0]["value"])
        request_data = metadata["request_data"]
        issue_key = metadata["jira_issue_key"]
        airtable_record_id = request_data["airtable_record_id"]

        log_step(
            "APPROVAL",
            "Reject button clicked",
            rejector=rejector,
            employee=request_data["full_name"],
            issue=issue_key,
        )

        try:
            log_step(
                "AIRTABLE",
                "Updating Airtable status",
                status="Rejected",
                record=airtable_record_id,
            )
            airtable_service.update_status(airtable_record_id, "Rejected")

            log_step("JIRA", "Adding rejection comment", issue=issue_key)
            jira_service.add_comment(issue_key, f"Rejected in Slack by <@{rejector}>.")

            log_step(
                "JIRA",
                "Transitioning Jira issue",
                issue=issue_key,
                transition=JIRA_REJECTED_TRANSITION_ID,
            )
            jira_service.transition_issue(issue_key, JIRA_REJECTED_TRANSITION_ID)

            log_step(
                "WORKFLOW",
                "Onboarding rejected",
                employee=request_data["full_name"],
                issue=issue_key,
            )

            client.chat_update(
                channel=body["channel"]["id"],
                ts=body["message"]["ts"],
                text=f"Rejected onboarding for {request_data['full_name']}",
                blocks=[
                    {
                        "type": "header",
                        "text": {"type": "plain_text", "text": "Onboarding rejected"},
                    },
                    *employee_summary_blocks(request_data),
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": (
                                f"❌ *Rejected by:* <@{rejector}>\n"
                                f"*Jira:* `{issue_key}`\n"
                                f"*Airtable Status:* `Rejected`"
                            ),
                        },
                    },
                ],
            )

        except Exception as e:
            log_step(
                "ERROR",
                "Reject workflow failed",
                employee=request_data["full_name"],
                issue=issue_key,
                error=e,
            )
            client.chat_postMessage(
                channel=SLACK_APPROVER_CHANNEL_ID,
                text=f"❌ Rejection workflow failed for *{request_data['full_name']}*: {e}",
            )
