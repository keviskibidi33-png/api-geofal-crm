import os
import requests
from dotenv import load_dotenv

load_dotenv("c:\\Users\\Lenovo\\Documents\\crmnew\\api-geofal-crm\\.env")

SUPABASE_URL = os.getenv("SUPABASE_URL") or "https://db.geofal.com.pe"
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJpc3MiOiJzdXBhYmFzZSIsImlhdCI6MTc3ODY4NzY0MCwiZXhwIjo0OTM0MzYxMjQwLCJyb2xlIjoic2VydmljZV9yb2xlIn0.eH_lLQ_RF3_Py_bLzjOI2iPrWyxzmcATlxkBzmwbU9A"

tables = [
    "densidad_ensayos",
    "densidad_campo_ensayos",
    "cono_ensayos",
    "cono_de_arena_ensayos",
    "densidad_campo",
    "densidad",
    "densidad_huantar",
    "densidad_huantar_ensayos",
]

headers = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
}

for table in tables:
    url = f"{SUPABASE_URL}/rest/v1/{table}?select=id&limit=1"
    resp = requests.get(url, headers=headers, timeout=5)
    print(f"Table '{table}': Status {resp.status_code} -> {resp.text[:200]}")
