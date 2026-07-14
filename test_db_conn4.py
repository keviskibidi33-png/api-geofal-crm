import psycopg2

urls = [
    "postgresql://postgres:fA1xpV4Qy5vcuXcgDA5MbBQQ2Jh32CcF@db.geofal.com.pe:5432/postgres",
    "postgresql://postgres:Li4Rj2DmjJpkiZtQ@db.geofal.com.pe:5432/postgres",
    "postgresql://postgres.Li4Rj2DmjJpkiZtQ:fA1xpV4Qy5vcuXcgDA5MbBQQ2Jh32CcF@db.geofal.com.pe:5432/postgres",
    "postgresql://Li4Rj2DmjJpkiZtQ:fA1xpV4Qy5vcuXcgDA5MbBQQ2Jh32CcF@db.geofal.com.pe:5432/postgres",
]

for url in urls:
    try:
        conn = psycopg2.connect(url, connect_timeout=3)
        print(f"SUCCESS: {url.split('@')[0]}@db.geofal.com.pe")
        
        # Test query tables
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
        break
    except Exception as e:
        print(f"FAILED: {url.split('@')[0]}@db.geofal.com.pe -> {repr(e)}")
