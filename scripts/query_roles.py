import os
import sys
import json
import requests
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
env_path = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(env_path)

supabase_url = os.getenv("SUPABASE_URL")
service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

if not supabase_url or not service_key:
    print("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY in .env")
    sys.exit(1)

headers = {
    "apikey": service_key,
    "Authorization": f"Bearer {service_key}",
    "Content-Type": "application/json"
}

url = f"{supabase_url}/rest/v1/role_definitions"
try:
    r = requests.get(url, headers=headers)
    if r.status_code == 200:
        roles = r.json()
        print("Role Definitions in DB:")
        for role in roles:
            print(f"- Role ID: {role.get('role_id')}, Label: {role.get('label')}")
            # print(json.dumps(role.get('permissions'), indent=2))
    else:
        print(f"Error fetching roles: {r.status_code} - {r.text}")
except Exception as e:
    print(f"Failed to query roles: {e}")
