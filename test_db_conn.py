import psycopg2

urls = [
    "postgresql://postgres:F4xvOgZobs6EBgiAkKkkDKd8Agz7QzLi@localhost:5432/postgres",
    "postgresql://postgres:F4xvOgZobs6EBgiAkKkkDKd8Agz7QzLi@127.0.0.1:5432/postgres",
    "postgresql://directus:directus@localhost:5432/directus",
    "postgresql://directus:directus@127.0.0.1:5432/directus",
    "postgresql://postgres:postgres@localhost:5432/postgres",
    "postgresql://postgres:postgres@127.0.0.1:5432/postgres",
]

for url in urls:
    try:
        conn = psycopg2.connect(url, connect_timeout=2)
        print(f"SUCCESS: {url}")
        conn.close()
        break
    except Exception as e:
        print(f"FAILED: {url} -> {e}")
