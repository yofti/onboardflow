import os
from dotenv import load_dotenv

load_dotenv()

SLACK_BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]
SLACK_APP_TOKEN = os.environ["SLACK_APP_TOKEN"]
SLACK_APPROVER_CHANNEL_ID = os.environ["SLACK_APPROVER_CHANNEL_ID"]

JIRA_BASE_URL = os.environ["JIRA_BASE_URL"].rstrip("/")
JIRA_EMAIL = os.environ["JIRA_EMAIL"]
JIRA_API_TOKEN = os.environ["JIRA_API_TOKEN"]
JIRA_PROJECT_KEY = os.environ["JIRA_PROJECT_KEY"]
JIRA_ISSUE_TYPE = os.environ.get("JIRA_ISSUE_TYPE", "Task")
JIRA_APPROVED_TRANSITION_ID = os.environ.get("JIRA_APPROVED_TRANSITION_ID")
JIRA_REJECTED_TRANSITION_ID = os.environ.get("JIRA_REJECTED_TRANSITION_ID")

OKTA_DOMAIN = os.environ["OKTA_DOMAIN"].rstrip("/")
OKTA_API_TOKEN = os.environ["OKTA_API_TOKEN"]

AIRTABLE_API_TOKEN = os.environ["AIRTABLE_API_TOKEN"]
AIRTABLE_BASE_ID = os.environ["AIRTABLE_BASE_ID"]
AIRTABLE_TABLE_NAME = os.environ.get("AIRTABLE_TABLE_NAME", "Employees")