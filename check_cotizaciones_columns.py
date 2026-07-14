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
    "Accept": "application/vnd.pgrst.object+json" # get single object
}

# Let's get one row to inspect columns and their values
url = f"{SUPABASE_URL}/rest/v1/cotizaciones?limit=1"
resp = requests.get(url, headers=headers)
if resp.status_code == 200:
    print(json.dumps(resp.json(), indent=2, ensure_ascii=False))
else:
    print(f"Error {resp.status_code}: {resp.text}")
