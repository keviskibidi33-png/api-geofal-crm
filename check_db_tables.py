import os
import psycopg2
from dotenv import load_dotenv

load_dotenv(r"C:\Users\Lenovo\Documents\crmnew\api-geofal-crm\.env")

conn = psycopg2.connect(os.getenv("QUOTES_DATABASE_URL"))
cur = conn.cursor()

cur.execute("""
    SELECT table_name 
    FROM information_schema.tables 
    WHERE table_schema = 'public' AND table_name LIKE '%densidad%';
""")
print("Tables with 'densidad':", cur.fetchall())

cur.execute("""
    SELECT table_name 
    FROM information_schema.tables 
    WHERE table_schema = 'public' AND table_name LIKE '%cono%';
""")
print("Tables with 'cono':", cur.fetchall())

cur.execute("""
    SELECT codigo, nombre, area FROM control_ensayos_catalogo WHERE codigo LIKE '%densidad%' OR nombre LIKE '%DENSIDAD%';
""")
print("Catalog entries:", cur.fetchall())

cur.close()
conn.close()
