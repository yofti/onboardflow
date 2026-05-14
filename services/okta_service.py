import json
import requests
from config import OKTA_DOMAIN, OKTA_API_TOKEN


def split_name(full_name):
    parts = full_name.strip().split()
    if len(parts) == 1:
        return parts[0], "Employee"
    return parts[0], " ".join(parts[1:])


def create_user(request_data):
    url = f"{OKTA_DOMAIN}/api/v1/users?activate=true"

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
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"SSWS {OKTA_API_TOKEN}",
        },
        data=json.dumps(payload),
        timeout=20,
    )

    response.raise_for_status()
    return response.json()