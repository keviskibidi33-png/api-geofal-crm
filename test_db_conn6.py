import psycopg2

url = "postgresql://supabase_admin:F4xvOgZobs6EBgiAkKkkDKd8Agz7QzLi@192.168.18.250:5432/postgres?sslmode=disable"

try:
    conn = psycopg2.connect(url, connect_timeout=3)
    print("SUCCESS: Connected as supabase_admin")
    cur = conn.cursor()
    
    cur.execute("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public' AND (table_name LIKE '%densidad%' OR table_name LIKE '%cono%');
    """)
    print("Tables like 'densidad' or 'cono':", cur.fetchall())

    cur.execute("""
        SELECT codigo, nombre, area FROM control_ensayos_catalogo WHERE codigo LIKE '%densidad%' OR nombre LIKE '%DENSIDAD%';
    """)
    print("Catalog entries:", cur.fetchall())

    cur.close()
    conn.close()
except Exception as e:
    print(f"FAILED: {repr(e)}")
