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

# Query latest quotes
url = f"{SUPABASE_URL}/rest/v1/cotizaciones?year=eq.2026&order=created_at.desc&limit=15"
resp = requests.get(url, headers=headers)
if resp.status_code == 200:
    data = resp.json()
    print(f"Latest 2026 quotes count: {len(data)}")
    for r in data:
        print(f"Created: {r.get('created_at')} | ID: {r.get('id')} | Numero: {r.get('numero')} | Cliente: {r.get('cliente_nombre')} | Total: {r.get('total')}")
else:
    print(f"Error {resp.status_code}: {resp.text}")
