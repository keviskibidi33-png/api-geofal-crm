import os
import psycopg2
from psycopg2.extras import RealDictCursor

# Using supabase_admin as username
conn_str = "postgresql://supabase_admin:F4xvOgZobs6EBgiAkKkkDKd8Agz7QzLi@192.168.18.250:5432/postgres?sslmode=disable"

try:
    conn = psycopg2.connect(conn_str)
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    print("--- Conexión exitosa ---")
    cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public';")
    tables = [row['table_name'] for row in cur.fetchall()]
    print("Tablas disponibles:", tables)
    
    # Check if there is a cotizaciones, quotes, or similar table
    quote_tables = [t for t in tables if 'cotiz' in t or 'quote' in t]
    print("Tablas de cotizaciones encontradas:", quote_tables)
    
    for t in quote_tables:
        try:
            # Let's check columns
            cur.execute(f"SELECT column_name FROM information_schema.columns WHERE table_name='{t}';")
            cols = [r['column_name'] for r in cur.fetchall()]
            print(f"Columnas de {t}: {cols}")
            
            # Search for 1428
            # Look for ID or numero_cotizacion or code or similar
            where_clauses = [f"{col}::text LIKE '%1428%'" for col in cols]
            if where_clauses:
                cur.execute(f"SELECT * FROM {t} WHERE " + " OR ".join(where_clauses))
                res = cur.fetchall()
                print(f"Coincidencias en {t}:")
                for r in res:
                    print(dict(r))
        except Exception as e:
            print(f"Error consultando {t}: {e}")
            conn.rollback()

    print("\n--- Buscando en la tabla auditoria para 1428 ---")
    if 'auditoria' in tables:
        cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='auditoria';")
        cols = [r['column_name'] for r in cur.fetchall()]
        where_clauses = [f"{col}::text LIKE '%1428%'" for col in cols]
        cur.execute("SELECT * FROM auditoria WHERE " + " OR ".join(where_clauses) + " ORDER BY created_at DESC LIMIT 20;")
        res = cur.fetchall()
        print("Coincidencias en auditoria:")
        for r in res:
            print(dict(r))
            
    cur.close()
    conn.close()
except Exception as e:
    print("Error de conexión o consulta:", e)
