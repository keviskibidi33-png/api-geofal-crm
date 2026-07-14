import psycopg2
import traceback

urls = [
    "postgresql://postgres:F4xvOgZobs6EBgiAkKkkDKd8Agz7QzLi@localhost:5432/postgres",
    "postgresql://postgres:F4xvOgZobs6EBgiAkKkkDKd8Agz7QzLi@127.0.0.1:5432/postgres",
    "postgresql://directus:directus@localhost:5432/directus",
    "postgresql://directus:directus@127.0.0.1:5432/directus",
    "postgresql://postgres:postgres@localhost:5432/postgres",
    "postgresql://postgres:postgres@127.0.0.1:5432/postgres",
    # Try with 192.168.18.250
    "postgresql://postgres:F4xvOgZobs6EBgiAkKkkDKd8Agz7QzLi@192.168.18.250:5432/postgres",
]

for url in urls:
    try:
        conn = psycopg2.connect(url, connect_timeout=2)
        print(f"SUCCESS: {url}")
        conn.close()
        break
    except Exception as e:
        # Get raw bytes or try cp1252 decoding
        err_str = str(e)
        try:
            err_bytes = err_str.encode('utf-8', errors='replace')
            print(f"FAILED: {url} -> {err_bytes.decode('utf-8')}")
        except:
            print(f"FAILED: {url} -> unknown error")
