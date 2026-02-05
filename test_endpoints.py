import requests
import os

BASE_URL = "http://localhost:8100" # Testing against local 8100

def test_endpoint(path, params=None):
    try:
        url = f"{BASE_URL}{path}"
        print(f"Testing {url} ...")
        # Simulate CORS preflight-ish or just GET
        headers = {
            "Origin": "https://cotizador.geofal.com.pe"
        }
        resp = requests.get(url, params=params, headers=headers)
        print(f"Status: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            print(f"Data count: {len(data.get('data', []))}")
            # Check CORS header
            print(f"Access-Control-Allow-Origin: {resp.headers.get('Access-Control-Allow-Origin')}")
        else:
            print(f"Error: {resp.text}")
    except Exception as e:
        print(f"Failed: {e}")

if __name__ == "__main__":
    test_endpoint("/health")
    test_endpoint("/clientes", {"search": "geofal"})
    test_endpoint("/proyectos")
    test_endpoint("/condiciones")
