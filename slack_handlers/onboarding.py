import json

from config import SLACK_APPROVER_CHANNEL_ID, JIRA_APPROVED_TRANSITION_ID, JIRA_REJECTED_TRANSITION_ID
from logging_utils import log_step
from services import airtable_service, jira_service, okta_service
from services.access_routing import build_access_ticket_plan

def format_access(access):
    if not access:
        return "None selected"
    if isinstance(access, list):
        return ", ".join(access)
    return str(access)

def employee_summary_blocks(request_data):
    return [
        {"type": "section", "text": {"type": "mrkdwn", "text": "*Employee profile pulled from Airtable*"}},
        {"type": "section", "fields": [
            {"type": "mrkdwn", "text": f"*Name:*\n{request_data.get('full_name', '')}"},
            {"type": "mrkdwn", "text": f"*Email:*\n{request_data.get('email', '')}"},
            {"type": "mrkdwn", "text": f"*Department:*\n{request_data.get('department', '')}"},
            {"type": "mrkdwn", "text": f"*Role:*\n{request_data.get('role', '')}"},
            {"type": "mrkdwn", "text": f"*Manager:*\n{request_data.get('manager', '')}"},
            {"type": "mrkdwn", "text": f"*Start Date:*\n{request_data.get('start_date', '')}"},
            {"type": "mrkdwn", "text": f"*Location:*\n{request_data.get('location', '')}"},
            {"type": "mrkdwn", "text": f"*Requested Access:*\n{format_access(request_data.get('access'))}"},
        ]},
    ]

def access_ticket_blocks(access_tickets):
    if not access_tickets:
        return [{"type": "section", "text": {"type": "mrkdwn", "text": "*Access Tickets:*\nNo access tickets created."}}]
    lines = [f"• *{item['access_name']}* → `{item['issue_key']}` | Owner: *{item['owner_team']}*" for item in access_tickets]
    return [{"type": "section", "text": {"type": "mrkdwn", "text": "*Granular access approval tickets created:*\n" + "\n".join(lines)}}]

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
                client.chat_postEphemeral(channel=channel_id, user=user_id, text="No pending employees found in Airtable.")
                return
            options = []
            for record in employees[:100]:
                fields = record.get("fields", {})
                full_name = fields.get("Full Name", "Unknown")
                role = fields.get("Role", "No role")
                department = fields.get("Department", "No department")
                start_date = fields.get("Start Date", "No start date")
                options.append({
                    "text": {"type": "plain_text", "text": f"{full_name} — {role}"[:75]},
                    "value": record["id"],
                    "description": {"type": "plain_text", "text": f"{department} • {start_date}"[:75]},
                })
            client.views_open(trigger_id=body["trigger_id"], view={
                "type": "modal",
                "callback_id": "onboarding_request_modal",
                "title": {"type": "plain_text", "text": "New Hire Onboarding"},
                "submit": {"type": "plain_text", "text": "Preview"},
                "close": {"type": "plain_text", "text": "Cancel"},
                "blocks": [
                    {"type": "section", "text": {"type": "mrkdwn", "text": "Select a pending employee from Airtable. The workflow will create one parent Jira ticket and one child ticket per access profile."}},
                    {"type": "input", "block_id": "employee_block", "element": {"type": "static_select", "action_id": "employee_select", "placeholder": {"type": "plain_text", "text": "Choose employee"}, "options": options}, "label": {"type": "plain_text", "text": "Employee"}},
                ],
            })
        except Exception as e:
            log_step("ERROR", "Could not load employees from Airtable", error=e)
            client.chat_postEphemeral(channel=channel_id, user=user_id, text=f"Could not load employees from Airtable: {e}")

    @app.view("onboarding_request_modal")
    def handle_onboarding_preview(ack, body, client, view):
        ack()
        user_id = body["user"]["id"]
        selected_record_id = view["state"]["values"]["employee_block"]["employee_select"]["selected_option"]["value"]
        log_step("SLACK", "Employee selected for preview", user=user_id, airtable_record=selected_record_id)
        try:
            employee_record = airtable_service.get_employee(selected_record_id)
            request_data = airtable_service.record_to_request_data(employee_record, requested_by=user_id)
            access_plan = build_access_ticket_plan(request_data)
            access_plan_lines = [f"• *{item['access_name']}* → Owner: *{item['owner_team']}*" for item in access_plan]
            client.views_open(trigger_id=body["trigger_id"], view={
                "type": "modal",
                "callback_id": "confirm_onboarding_modal",
                "private_metadata": json.dumps(request_data),
                "title": {"type": "plain_text", "text": "Confirm Onboarding"},
                "submit": {"type": "plain_text", "text": "Create Tickets"},
                "close": {"type": "plain_text", "text": "Back"},
                "blocks": employee_summary_blocks(request_data) + [
                    {"type": "divider"},
                    {"type": "section", "text": {"type": "mrkdwn", "text": "*Granular ticket plan:*\n" + "\n".join(access_plan_lines) + "\n\nThis creates one parent onboarding ticket plus one child audit ticket per access profile."}},
                ],
            })
        except Exception as e:
            log_step("ERROR", "Could not preview employee", error=e)
            client.chat_postMessage(channel=user_id, text=f"Could not preview employee from Airtable: {e}")

    @app.view("confirm_onboarding_modal")
    def handle_onboarding_submission(ack, body, client, view):
        ack()
        request_data = json.loads(view["private_metadata"])
        user_id = body["user"]["id"]
        log_step("WORKFLOW", "Starting granular onboarding submission", employee=request_data["full_name"], email=request_data["email"])
        try:
            client.chat_postMessage(channel=user_id, text=f"⏳ Starting granular onboarding workflow for *{request_data['full_name']}*...")
            parent_issue = jira_service.create_ticket(request_data)
            parent_issue_key = parent_issue["key"]
            client.chat_postMessage(channel=user_id, text=f"✅ Parent Jira onboarding ticket `{parent_issue_key}` created.")

            access_plan = build_access_ticket_plan(request_data)
            access_tickets = []
            for item in access_plan:
                access_name = item["access_name"]
                owner_team = item["owner_team"]
                client.chat_postMessage(channel=user_id, text=f"⏳ Creating Jira child ticket for *{access_name}* access. Owner team: *{owner_team}*.")
                child_issue = jira_service.create_access_ticket(request_data, access_name, owner_team, parent_issue_key)
                access_tickets.append({"access_name": access_name, "owner_team": owner_team, "issue_key": child_issue["key"]})
                client.chat_postMessage(channel=user_id, text=f"✅ Child ticket `{child_issue['key']}` created for *{access_name}* access.")

            airtable_service.update_status(request_data["airtable_record_id"], "Submitted")
            jira_service.add_comment(parent_issue_key, "Granular access child tickets created:\n" + "\n".join([f"- {t['access_name']} ({t['owner_team']}): {t['issue_key']}" for t in access_tickets]))

            metadata = {"request_data": request_data, "parent_jira_issue_key": parent_issue_key, "access_tickets": access_tickets}
            client.chat_postMessage(channel=SLACK_APPROVER_CHANNEL_ID, text=f"Granular approval needed for onboarding {request_data['full_name']}", blocks=[
                {"type": "header", "text": {"type": "plain_text", "text": "Granular onboarding approval needed"}},
                *employee_summary_blocks(request_data),
                {"type": "section", "fields": [
                    {"type": "mrkdwn", "text": f"*Parent Jira Ticket:*\n`{parent_issue_key}`"},
                    {"type": "mrkdwn", "text": f"*Requested By:*\n<@{user_id}>"},
                ]},
                *access_ticket_blocks(access_tickets),
                {"type": "actions", "block_id": "approval_actions", "elements": [
                    {"type": "button", "text": {"type": "plain_text", "text": "Approve All"}, "style": "primary", "action_id": "approve_onboarding", "value": json.dumps(metadata)},
                    {"type": "button", "text": {"type": "plain_text", "text": "Reject All"}, "style": "danger", "action_id": "reject_onboarding", "value": json.dumps(metadata)},
                ]},
            ])
            client.chat_postMessage(channel=user_id, text=f"✅ Approval request posted. Parent: `{parent_issue_key}`. Child tickets: {', '.join([t['issue_key'] for t in access_tickets])}")
            log_step("WORKFLOW", "Granular submission complete. Waiting for approval.", parent=parent_issue_key, child_count=len(access_tickets))
        except Exception as e:
            log_step("ERROR", "Granular workflow submission failed", employee=request_data.get("full_name"), error=e)
            client.chat_postMessage(channel=user_id, text=f"❌ Something went wrong while submitting onboarding for {request_data['full_name']}: {e}")

    @app.action("approve_onboarding")
    def approve_onboarding(ack, body, client):
        ack()
        approver = body["user"]["id"]
        metadata = json.loads(body["actions"][0]["value"])
        request_data = metadata["request_data"]
        parent_issue_key = metadata.get("parent_jira_issue_key") or metadata.get("jira_issue_key")
        access_tickets = metadata.get("access_tickets", [])
        airtable_record_id = request_data["airtable_record_id"]
        log_step("APPROVAL", "Approve All clicked", approver=approver, employee=request_data["full_name"], parent=parent_issue_key, child_count=len(access_tickets))
        try:
            client.chat_update(channel=body["channel"]["id"], ts=body["message"]["ts"], text=f"Processing approval for {request_data['full_name']}", blocks=[
                {"type": "header", "text": {"type": "plain_text", "text": "Processing granular onboarding approval"}},
                *employee_summary_blocks(request_data),
                *access_ticket_blocks(access_tickets),
                {"type": "section", "text": {"type": "mrkdwn", "text": f"⏳ Approved by <@{approver}>. Creating Okta user and updating parent + child Jira tickets."}},
            ])
            airtable_service.update_status(airtable_record_id, "Approved")
            okta_user = okta_service.create_user(request_data)
            okta_id = okta_user["id"]
            jira_service.add_comment(parent_issue_key, f"Approved in Slack by <@{approver}>. Okta user created successfully. Okta user ID: {okta_id}")
            for ticket in access_tickets:
                jira_service.add_comment(ticket["issue_key"], f"Access approved in Slack by <@{approver}>. Okta user ID: {okta_id}. Access profile: {ticket['access_name']}. Owner team: {ticket['owner_team']}. Parent onboarding ticket: {parent_issue_key}.")
                jira_service.transition_issue(ticket["issue_key"], JIRA_APPROVED_TRANSITION_ID)
            jira_service.transition_issue(parent_issue_key, JIRA_APPROVED_TRANSITION_ID)
            airtable_service.update_status(airtable_record_id, "Provisioned")
            client.chat_update(channel=body["channel"]["id"], ts=body["message"]["ts"], text=f"Approved onboarding for {request_data['full_name']}", blocks=[
                {"type": "header", "text": {"type": "plain_text", "text": "Onboarding approved and provisioned"}},
                *employee_summary_blocks(request_data),
                {"type": "section", "text": {"type": "mrkdwn", "text": f"✅ *Workflow complete*\n*Parent Jira:* `{parent_issue_key}`\n*Okta user ID:* `{okta_id}`\n*Airtable Status:* `Provisioned`\n*Approved by:* <@{approver}>"}},
                *access_ticket_blocks(access_tickets),
            ])
            client.chat_postMessage(channel=SLACK_APPROVER_CHANNEL_ID, text=f"✅ Granular onboarding completed for *{request_data['full_name']}*. Parent Jira `{parent_issue_key}` updated. {len(access_tickets)} child access tickets updated. Okta user `{okta_id}` created.")
        except Exception as e:
            log_step("ERROR", "Approval workflow failed", employee=request_data["full_name"], parent=parent_issue_key, error=e)
            try:
                airtable_service.update_status(airtable_record_id, "Failed")
            except Exception as airtable_error:
                log_step("ERROR", "Could not mark Airtable as Failed", error=airtable_error)
            try:
                jira_service.add_comment(parent_issue_key, f"Approval clicked by Slack user {approver}, but automation failed: {e}")
            except Exception as jira_error:
                log_step("ERROR", "Could not add Jira failure comment", error=jira_error)
            client.chat_postMessage(channel=SLACK_APPROVER_CHANNEL_ID, text=f"❌ Onboarding failed for *{request_data['full_name']}*: {e}")

    @app.action("reject_onboarding")
    def reject_onboarding(ack, body, client):
        ack()
        rejector = body["user"]["id"]
        metadata = json.loads(body["actions"][0]["value"])
        request_data = metadata["request_data"]
        parent_issue_key = metadata.get("parent_jira_issue_key") or metadata.get("jira_issue_key")
        access_tickets = metadata.get("access_tickets", [])
        airtable_record_id = request_data["airtable_record_id"]
        try:
            airtable_service.update_status(airtable_record_id, "Rejected")
            jira_service.add_comment(parent_issue_key, f"Rejected in Slack by <@{rejector}>.")
            for ticket in access_tickets:
                jira_service.add_comment(ticket["issue_key"], f"Access rejected in Slack by <@{rejector}>. Access profile: {ticket['access_name']}. Owner team: {ticket['owner_team']}. Parent onboarding ticket: {parent_issue_key}.")
                jira_service.transition_issue(ticket["issue_key"], JIRA_REJECTED_TRANSITION_ID)
            jira_service.transition_issue(parent_issue_key, JIRA_REJECTED_TRANSITION_ID)
            client.chat_update(channel=body["channel"]["id"], ts=body["message"]["ts"], text=f"Rejected onboarding for {request_data['full_name']}", blocks=[
                {"type": "header", "text": {"type": "plain_text", "text": "Onboarding rejected"}},
                *employee_summary_blocks(request_data),
                {"type": "section", "text": {"type": "mrkdwn", "text": f"❌ *Rejected by:* <@{rejector}>\n*Parent Jira:* `{parent_issue_key}`\n*Airtable Status:* `Rejected`"}},
                *access_ticket_blocks(access_tickets),
            ])
        except Exception as e:
            log_step("ERROR", "Reject workflow failed", employee=request_data["full_name"], parent=parent_issue_key, error=e)
            client.chat_postMessage(channel=SLACK_APPROVER_CHANNEL_ID, text=f"❌ Rejection workflow failed for *{request_data['full_name']}*: {e}")
