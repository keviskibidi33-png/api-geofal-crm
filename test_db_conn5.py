import psycopg2

urls = [
    # Local host with the new passwords
    "postgresql://postgres:fA1xpV4Qy5vcuXcgDA5MbBQQ2Jh32CcF@192.168.18.250:5432/postgres",
    "postgresql://postgres:Li4Rj2DmjJpkiZtQ@192.168.18.250:5432/postgres",
    "postgresql://directus:fA1xpV4Qy5vcuXcgDA5MbBQQ2Jh32CcF@192.168.18.250:5432/postgres",
    "postgresql://directus:Li4Rj2DmjJpkiZtQ@192.168.18.250:5432/postgres",
    # Remote host with port 6543 (Supabase pooler)
    "postgresql://postgres:fA1xpV4Qy5vcuXcgDA5MbBQQ2Jh32CcF@db.geofal.com.pe:6543/postgres",
    "postgresql://postgres:Li4Rj2DmjJpkiZtQ@db.geofal.com.pe:6543/postgres",
    "postgresql://postgres.Li4Rj2DmjJpkiZtQ:fA1xpV4Qy5vcuXcgDA5MbBQQ2Jh32CcF@db.geofal.com.pe:6543/postgres",
    "postgresql://postgres.Li4Rj2DmjJpkiZtQ:Li4Rj2DmjJpkiZtQ@db.geofal.com.pe:6543/postgres",
]

for url in urls:
    try:
        conn = psycopg2.connect(url, connect_timeout=3)
        print(f"SUCCESS: {url.split('@')[0]}@{url.split('@')[1]}")
        # Test query
        cur = conn.cursor()
        cur.execute("SELECT 1;")
        print("Test query: SUCCESS")
        cur.close()
        conn.close()
        break
    except Exception as e:
        print(f"FAILED: {url.split('@')[0]}@{url.split('@')[1]} -> {repr(e)}")
