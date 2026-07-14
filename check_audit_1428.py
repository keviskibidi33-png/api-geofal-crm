import os
import requests
import json
from dotenv import load_dotenv

load_dotenv("c:\\Users\\Lenovo\\Documents\\crmnew\\api-geofal-crm\\.env")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

headers = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json"
}

# Search auditoria
url = f"{SUPABASE_URL}/rest/v1/auditoria?or=(action.ilike.*1428*,details.fts.*1428*)"
resp = requests.get(url, headers=headers)
if resp.status_code == 200:
    data = resp.json()
    print(f"Auditoria Count: {len(data)}")
    for r in data:
        print(json.dumps(r, indent=2, ensure_ascii=False))
else:
    print(f"Error {resp.status_code}: {resp.text}")
