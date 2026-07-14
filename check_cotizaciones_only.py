import os
import requests
import json
from dotenv import load_dotenv

load_dotenv("c:\\Users\\Lenovo\\Documents\crmnew\\api-geofal-crm\\.env")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

headers = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json"
}

# 1. Query by number = 1428
print("--- QUERY 1428 ---")
url = f"{SUPABASE_URL}/rest/v1/cotizaciones?numero=eq.1428"
resp = requests.get(url, headers=headers)
if resp.status_code == 200:
    data = resp.json()
    print(f"Count: {len(data)}")
    for r in data:
        print(f"ID: {r.get('id')}, Numero: {r.get('numero')}, Year: {r.get('year')}, Cliente: {r.get('cliente_nombre')}, Total: {r.get('total')}, Estado: {r.get('estado')}")
else:
    print(f"Error {resp.status_code}: {resp.text}")

# 2. Query by COMEDSA
print("\n--- QUERY COMEDSA ---")
url = f"{SUPABASE_URL}/rest/v1/cotizaciones?cliente_nombre=ilike.*COMEDSA*"
resp = requests.get(url, headers=headers)
if resp.status_code == 200:
    data = resp.json()
    print(f"Count: {len(data)}")
    for r in data:
        print(f"ID: {r.get('id')}, Numero: {r.get('numero')}, Year: {r.get('year')}, Cliente: {r.get('cliente_nombre')}, Total: {r.get('total')}, Estado: {r.get('estado')}")
else:
    print(f"Error {resp.status_code}: {resp.text}")
