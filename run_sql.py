import os
import requests
import json
from dotenv import load_dotenv

load_dotenv("c:\\Users\\Lenovo\\Documents\crmnew\\api-geofal-crm\\.env")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

def run_query(sql_query):
    resp = requests.post(
        f"{SUPABASE_URL}/rest/v1/rpc/exec_sql",
        headers={
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json"
        },
        json={"query": sql_query}
    )
    if resp.status_code in (200, 201, 204):
        try:
            return resp.json()
        except:
            return resp.text
    else:
        return f"ERROR {resp.status_code}: {resp.text}"

print("=== TABLES LIKE 'densidad' OR 'cono' ===")
tables_sql = """
SELECT table_name 
FROM information_schema.tables 
WHERE table_schema = 'public' AND (table_name LIKE '%densidad%' OR table_name LIKE '%cono%');
"""
print(json.dumps(run_query(tables_sql), indent=2))

print("\n=== CATALOG ENTRIES FOR DENSIDAD ===")
catalog_sql = """
SELECT codigo, nombre, area FROM control_ensayos_catalogo WHERE codigo LIKE '%densidad%' OR nombre LIKE '%DENSIDAD%';
"""
print(json.dumps(run_query(catalog_sql), indent=2))
