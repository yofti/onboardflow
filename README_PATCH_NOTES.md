# OnboardFlow Slack UX Updates

Files included:
- app.py
- logging_utils.py
- slack_handlers/onboarding.py
- services/jira_service_patch_example.py

Apply:
1. Copy logging_utils.py to the repo root.
2. Replace app.py.
3. Replace slack_handlers/onboarding.py.
4. Manually add the snippets from services/jira_service_patch_example.py into your existing services/jira_service.py.
5. Run:

python -m py_compile app.py config.py logging_utils.py services/*.py slack_handlers/*.py
python app.py

Expected UX:
- /onboard opens a selector.
- Selecting an employee opens a preview modal with full Airtable profile.
- Submitting preview creates Jira + updates Airtable + posts approval.
- Slack and terminal logs are more verbose at every step.
