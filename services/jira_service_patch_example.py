# Add this logging to your existing services/jira_service.py.
# Keep your existing imports, then add:
from logging_utils import log_step


# Inside create_ticket(), add before/after requests:
log_step("JIRA", "POST /issue", project=JIRA_PROJECT_KEY, issue_type=JIRA_ISSUE_TYPE)

# Before response.raise_for_status():
if not response.ok:
    log_step("ERROR", "Jira create ticket failed", status=response.status_code, body=response.text)


# Inside add_comment(), before request:
log_step("JIRA", "POST /comment", issue=issue_key)

# Before response.raise_for_status():
if not response.ok:
    log_step("ERROR", "Jira add comment failed", status=response.status_code, body=response.text)


# Inside transition_issue(), before request:
log_step("JIRA", "POST /transitions", issue=issue_key, transition=transition_id)

# Before response.raise_for_status():
if not response.ok:
    log_step("ERROR", "Jira transition failed", status=response.status_code, body=response.text)
