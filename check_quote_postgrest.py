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

print("--- Querying cotizaciones table via PostgREST ---")
# Let's search for "1428" in numero column, or COMEDSA in cliente_nombre
url = f"{SUPABASE_URL}/rest/v1/cotizaciones?or=(numero.eq.1428,cliente_nombre.ilike.*COMEDSA*)"
resp = requests.get(url, headers=headers)
if resp.status_code == 200:
    print(json.dumps(resp.json(), indent=2, ensure_ascii=False))
else:
    print(f"Error {resp.status_code}: {resp.text}")

print("\n--- Querying auditoria table via PostgREST ---")
url = f"{SUPABASE_URL}/rest/v1/auditoria?order=created_at.desc&limit=20"
resp = requests.get(url, headers=headers)
if resp.status_code == 200:
    print(json.dumps(resp.json(), indent=2, ensure_ascii=False))
else:
    print(f"Error {resp.status_code}: {resp.text}")
