import os
import requests
import io
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

BUCKETS = ["recepciones", "verificacion", "compresiones", "humedad"]

def test_buckets():
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("Missing Supabase credentials.")
        return

    for bucket in BUCKETS:
        print(f"DEBUG: Starting test for {bucket}")
        
        filename = "test_upsert.txt"
        content1 = b"Content Version 1"
        content2 = b"Content Version 2"
        
        url = f"{SUPABASE_URL.rstrip('/')}/storage/v1/object/{bucket}/{filename}"
        headers = {
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "text/plain",
            "x-upsert": "true"
        }

        # 1. First Upload
        print("Uploading Version 1...")
        resp1 = requests.post(url, headers=headers, data=content1)
        print(f"Status: {resp1.status_code}")
        if resp1.status_code not in [200, 201]:
            print(f"Error: {resp1.text}")
            continue

        # 2. Second Upload (Upsert)
        print("Uploading Version 2 (Upsert)...")
        resp2 = requests.post(url, headers=headers, data=content2)
        print(f"Status: {resp2.status_code}")
        if resp2.status_code not in [200, 201]:
            print(f"Error: {resp2.text}")
            continue
        
        # 3. Verify Content
        print("Verifying content...")
        get_url = f"{SUPABASE_URL.rstrip('/')}/storage/v1/object/public/{bucket}/{filename}"
        resp3 = requests.get(get_url)
        if resp3.status_code == 200:
            if resp3.content == content2:
                print("SUCCESS: Content was correctly replaced (Upsert works).")
            else:
                print(f"FAILURE: Content mismatch. Got: {resp3.content}")
        else:
            print(f"Could not verify via public URL ({resp3.status_code}). Trying authenticated GET...")
            # Fallback to authenticated GET
            resp4 = requests.get(url, headers={"Authorization": f"Bearer {SUPABASE_KEY}"})
            if resp4.status_code == 200 and resp4.content == content2:
                 print("SUCCESS: Content was correctly replaced (Verified via Auth GET).")
            else:
                 print(f"FAILURE: Could not verify content. Status: {resp4.status_code}")

if __name__ == "__main__":
    test_buckets()
