import psycopg2
import sys

hosts = ["127.0.0.1", "localhost", "192.168.18.250"]
users = ["postgres", "supabase_admin", "directus"]
passwords = ["F4xvOgZobs6EBgiAkKkkDKd8Agz7QzLi", "directus", "postgres"]
databases = ["postgres", "directus"]

for host in hosts:
    for user in users:
        for pwd in passwords:
            for db in databases:
                conn_str = f"postgresql://{user}:{pwd}@{host}:5432/{db}?sslmode=disable"
                try:
                    conn = psycopg2.connect(conn_str, connect_timeout=1)
                    print(f"SUCCESS: {conn_str}")
                    # Run a query
                    cur = conn.cursor()
                    cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public';")
                    print("Tables:", [r[0] for r in cur.fetchall()][:10])
                    cur.close()
                    conn.close()
                    sys.exit(0)
                except Exception as e:
                    # Just skip
                    pass
print("No combination worked.")
