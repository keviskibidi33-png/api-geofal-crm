import psycopg2

urls = [
    "postgresql://directus:directus@192.168.18.250:5432/directus",
    "postgresql://directus:F4xvOgZobs6EBgiAkKkkDKd8Agz7QzLi@192.168.18.250:5432/directus",
    "postgresql://postgres:directus@192.168.18.250:5432/postgres",
    "postgresql://directus:directus@192.168.18.250:5432/postgres",
]

for url in urls:
    try:
        conn = psycopg2.connect(url, connect_timeout=2)
        print(f"SUCCESS: {url}")
        conn.close()
        break
    except Exception as e:
        print(f"FAILED: {url} -> {repr(e)}")
