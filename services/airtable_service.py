import json
import requests
from config import AIRTABLE_API_TOKEN, AIRTABLE_BASE_ID, AIRTABLE_TABLE_NAME


def headers():
    return {
        "Authorization": f"Bearer {AIRTABLE_API_TOKEN}",
        "Content-Type": "application/json",
    }


def base_url():
    return f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{AIRTABLE_TABLE_NAME}"


def get_pending_employees():
    response = requests.get(
        base_url(),
        headers=headers(),
        params={"filterByFormula": "{Status} = 'Pending'", "maxRecords": 100},
        timeout=20,
    )

    if not response.ok:
        print("Airtable error:", response.text)

    response.raise_for_status()
    return response.json().get("records", [])


def get_employee(record_id):
    response = requests.get(
        f"{base_url()}/{record_id}",
        headers=headers(),
        timeout=20,
    )
    response.raise_for_status()
    return response.json()


def update_status(record_id, status):
    payload = {"fields": {"Status": status}}

    response = requests.patch(
        f"{base_url()}/{record_id}",
        headers=headers(),
        data=json.dumps(payload),
        timeout=20,
    )

    if not response.ok:
        print("Airtable error:", response.text)

    response.raise_for_status()
    return response.json()


def record_to_request_data(record, requested_by):
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
