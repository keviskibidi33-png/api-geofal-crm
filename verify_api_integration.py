import requests
import json
import sys

# Ports to check in order of likely configuration
PORTS = [8000, 8080, 8181]

def find_active_api():
    for port in PORTS:
        url = f"http://localhost:{port}"
        try:
            print(f"Checking {url}...")
            resp = requests.get(f"{url}/health", timeout=2)
            if resp.status_code == 200:
                print(f"[FOUND] API is running on port {port}")
                return url
        except:
            pass
    return None

def test_api():
    API_URL = find_active_api()
    if not API_URL:
        print("[FAIL] Could not find running API on ports 8000, 8080, or 8181.")
        print("Please ensure 'api-geofal-crm' is running.")
        return

    print(f"Testing API at {API_URL}...")
    
    # 1. Health Check
    try:
        resp = requests.get(f"{API_URL}/health", timeout=5)
        print(f"Health Check: {resp.status_code}")
        print(f"Response: {resp.json()}")
        if resp.status_code != 200:
            print("[FAIL] API is not healthy.")
            return
    except Exception as e:
        print(f"[FAIL] Could not connect to API: {e}")
        return

    # 2. Test Validity Handing (The fix for 500 -> 400)
    # Payload with empty samples (should trigger ValueError in service logic)
    payload = {
        "numero_ot": "TEST-OT-001",
        "numero_recepcion": "REC-001",
        "cliente": "Cliente Test",
        "muestras": [] # Empty list should trigger error
    }
    
    print("\nSending Payload with Empty Samples...")
    try:
        resp = requests.post(f"{API_URL}/api/ordenes/", json=payload, headers={"Content-Type": "application/json"})
        print(f"Status Code: {resp.status_code}")
        try:
            print(f"Response Body: {resp.json()}")
        except:
            print(f"Response Text: {resp.text}")

        if resp.status_code == 400:
            print("\n[SUCCESS] API returned 400 Bad Request as expected for validation error.")
        elif resp.status_code == 500:
            print("\n[FAIL] API returned 500 Internal Server Error. The ValueError handler is NOT active.")
        elif resp.status_code == 422:
            print("\n[INFO] API returned 422 Validation Error (Pydantic caught it before service logic).")
        else:
            print(f"\n[?] Unexpected status code: {resp.status_code}")

    except Exception as e:
        print(f"[FAIL] Request failed: {e}")

if __name__ == "__main__":
    test_api()
