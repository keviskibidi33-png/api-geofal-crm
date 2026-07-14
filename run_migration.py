import os
import requests
from dotenv import load_dotenv

load_dotenv("c:\\Users\\Lenovo\\Documents\\crmnew\\api-geofal-crm\\.env")

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
    print(resp.status_code, resp.text)

sql = "ALTER TABLE public.huanta_probetas ADD COLUMN IF NOT EXISTS f_c VARCHAR(50) NOT NULL DEFAULT '-';"
run_query(sql)
run_query("NOTIFY pgrst, 'reload schema';")
