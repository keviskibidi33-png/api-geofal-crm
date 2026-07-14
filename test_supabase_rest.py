import os
import requests
import json
from dotenv import load_dotenv

load_dotenv("c:\\Users\\Lenovo\\Documents\\crmnew\\api-geofal-crm\\.env")

SUPABASE_URL = os.getenv("SUPABASE_URL") or "https://db.geofal.com.pe"
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJpc3MiOiJzdXBhYmFzZSIsImlhdCI6MTc3ODY4NzY0MCwiZXhwIjo0OTM0MzYxMjQwLCJyb2xlIjoic2VydmljZV9yb2xlIn0.eH_lLQ_RF3_Py_bLzjOI2iPrWyxzmcATlxkBzmwbU9A"

# Let's query the control_ensayos_catalogo table via PostgREST
url = f"{SUPABASE_URL}/rest/v1/control_ensayos_catalogo?select=codigo,nombre,area&limit=150"
headers = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
}

try:
    resp = requests.get(url, headers=headers, timeout=5)
    print(f"Status Code: {resp.status_code}")
    if resp.status_code == 200:
        print("Data fetched successfully:")
        print(json.dumps(resp.json(), indent=2))
    else:
        print(f"Error Response: {resp.text}")
except Exception as e:
    print(f"Request failed: {e}")
