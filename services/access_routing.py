from logging_utils import log_step

ACCESS_OWNER_MAP = {
    "GitHub": "IT",
    "Google Workspace": "IT",
    "GoogleWorkspace": "IT",
    "AWS Access": "IT",
    "Engineering VPN": "IT",
    "Salesforce": "Sales",
    "SalesForce": "Sales",
    "HRIS": "HR",
    "Internal APIs": "Engineering",
    "Finance Tools": "Finance",
    "Security Tools": "Security",
    "Figma": "Product",
}

def owner_for_access(access_name):
    owner = ACCESS_OWNER_MAP.get(access_name, "IT")
    log_step("ACCESS_ROUTING", "Resolved access owner", access=access_name, owner=owner)
    return owner

def build_access_ticket_plan(request_data):
    access_items = request_data.get("access", []) or []
    plan = []
    for access_name in access_items:
        clean_access_name = str(access_name).strip()
        if clean_access_name:
            plan.append({"access_name": clean_access_name, "owner_team": owner_for_access(clean_access_name)})
    log_step("ACCESS_ROUTING", "Built granular access ticket plan",
             employee=request_data.get("full_name", ""), ticket_count=len(plan),
             access_items=[item["access_name"] for item in plan])
    return plan
