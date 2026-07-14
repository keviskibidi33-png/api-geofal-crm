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

# List files in bucket "cotizaciones" under folder "2026"
url = f"{SUPABASE_URL}/storage/v1/object/list/cotizaciones"
payload = {
    "prefix": "2026/",
    "limit": 100,
    "sortBy": {"column": "name", "order": "desc"}
}

resp = requests.post(url, headers=headers, json=payload)
if resp.status_code == 200:
    files = resp.json()
    print("Files in storage:")
    for f in files[:20]:
        print(f"Name: {f.get('name')} | Created: {f.get('created_at')} | Size: {f.get('metadata', {}).get('size')}")
else:
    print(f"Error {resp.status_code}: {resp.text}")
