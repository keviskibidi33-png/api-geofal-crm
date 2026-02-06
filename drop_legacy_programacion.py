import os
import psycopg2
from dotenv import load_dotenv

def cleanup():
    load_dotenv()
    dsn = os.getenv("QUOTES_DATABASE_URL")
    if not dsn:
        print("Error: QUOTES_DATABASE_URL not found")
        return

    try:
        conn = psycopg2.connect(dsn)
        conn.autocommit = True
        with conn.cursor() as cur:
            print("Dropping legacy triggers...")
            cur.execute("DROP TRIGGER IF EXISTS trigger_programacion_updated ON programacion_servicios;")
            cur.execute("DROP TRIGGER IF EXISTS trigger_calculate_dias_atraso ON programacion_servicios;")
            
            print("Dropping legacy tables...")
            cur.execute("DROP TABLE IF EXISTS programacion_servicios_historial CASCADE;")
            cur.execute("DROP TABLE IF EXISTS programacion_servicios CASCADE;")
            
            print("Cleanup completed successfully.")
    except Exception as e:
        print(f"Cleanup failed: {e}")
    finally:
        if 'conn' in locals() and conn:
            conn.close()

if __name__ == "__main__":
    cleanup()
