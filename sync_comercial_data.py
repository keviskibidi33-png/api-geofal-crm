import psycopg2
import os
from dotenv import load_dotenv

def sync_delays():
    load_dotenv()
    dsn = os.getenv("QUOTES_DATABASE_URL")
    if not dsn:
        print("Error: QUOTES_DATABASE_URL not found")
        return

    try:
        conn = psycopg2.connect(dsn)
        cur = conn.cursor()

        print("Synchronizing fecha_entrega_com and dias_atraso_envio_coti from Lab defaults if NULL...")
        
        # 1. Update fecha_entrega_com from fecha_entrega_estimada if it's currently NULL
        # This gives a starting point for calculation
        cur.execute("""
            UPDATE programacion_comercial pc
            SET fecha_entrega_com = pl.fecha_entrega_estimada
            FROM programacion_lab pl
            WHERE pc.programacion_id = pl.id
              AND pc.fecha_entrega_com IS NULL
              AND pl.fecha_entrega_estimada IS NOT NULL;
        """)
        print(f"Updated {cur.rowcount} records with default delivery dates.")

        # 2. Update dias_atraso_envio_coti from dias_atraso_lab for existing records 
        # to ensure the view isn't empty after the split.
        cur.execute("""
            UPDATE programacion_comercial pc
            SET dias_atraso_envio_coti = pl.dias_atraso_lab,
                motivo_dias_atraso_com = pl.motivo_dias_atraso_lab
            FROM programacion_lab pl
            WHERE pc.programacion_id = pl.id;
        """)
        print(f"Updated {cur.rowcount} records with synced delay data.")

        conn.commit()
        print("Data synchronization completed successfully.")
        cur.close()
        conn.close()

    except Exception as e:
        print(f"Sync failed: {e}")

if __name__ == "__main__":
    sync_delays()
