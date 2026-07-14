import os
import requests
import json
from dotenv import load_dotenv

load_dotenv("c:\\Users\\Lenovo\\Documents\\crmnew\\api-geofal-crm\\.env")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

def query_db(sql):
    resp = requests.post(
        f"{SUPABASE_URL}/rest/v1/rpc/exec_sql",
        headers={
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json"
        },
        json={"query": sql}
    )
    if resp.status_code == 200:
        return resp.json()
    else:
        print(f"Error: {resp.status_code}")
        print(resp.text)
        return None

print("--- Querying cotizaciones for 1428 ---")
res_quotes = query_db("SELECT * FROM cotizaciones WHERE numero::text = '1428' OR cliente_nombre LIKE '%COMEDSA%';")
print(json.dumps(res_quotes, indent=2, ensure_ascii=False) if res_quotes else "No results")

print("\n--- Querying auditoria for 1428 or COMEDSA ---")
res_audit = query_db("SELECT * FROM auditoria WHERE details::text LIKE '%1428%' OR details::text LIKE '%COMEDSA%' OR action LIKE '%1428%' ORDER BY created_at DESC LIMIT 20;")
print(json.dumps(res_audit, indent=2, ensure_ascii=False) if res_audit else "No results")
