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

# Query by ID
quote_id = "f68ff4b1-761e-4d14-b959-7c63bb347f2f"
url = f"{SUPABASE_URL}/rest/v1/cotizaciones?id=eq.{quote_id}"
resp = requests.get(url, headers=headers)
if resp.status_code == 200:
    data = resp.json()
    print(f"By ID count: {len(data)}")
    for r in data:
        print(f"ID: {r.get('id')}")
        print(f"Numero: {r.get('numero')}")
        print(f"Year: {r.get('year')}")
        print(f"Cliente: {r.get('cliente_nombre')}")
        print(f"Total: {r.get('total')}")
        print(f"Estado: {r.get('estado')}")
        print(f"Object Key: {r.get('object_key')}")
        print(f"Filepath: {r.get('archivo_path')}")
        # Write full json to file to inspect
        with open("quote_detail.json", "w", encoding="utf-8") as f:
            json.dump(r, f, indent=2, ensure_ascii=False)
        print("Written full details to quote_detail.json")
else:
    print(f"Error {resp.status_code}: {resp.text}")
