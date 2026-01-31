import psycopg2
import os
from dotenv import load_dotenv

def sync_data():
    load_dotenv()
    dsn = os.getenv("QUOTES_DATABASE_URL")
    if not dsn:
        print("Error: QUOTES_DATABASE_URL not found")
        return

    try:
        conn = psycopg2.connect(dsn)
        cur = conn.cursor()

        print("Syncing dates and delays from programacion_lab to programacion_comercial...")
        
        # Syncing fecha_entrega_com with fecha_entrega_estimada to ensure identical delay calculations
        sql = """
            UPDATE programacion_comercial pc
            SET dias_atraso_envio_coti = pl.dias_atraso_lab,
                motivo_dias_atraso_com = pl.motivo_dias_atraso_lab,
                fecha_entrega_com = COALESCE(pc.fecha_entrega_com, pl.fecha_entrega_estimada)
            FROM programacion_lab pl
            WHERE pc.programacion_id = pl.id;
        """
        
        cur.execute(sql)
        conn.commit()
        print("Data synchronization completed successfully.")
        cur.close()
        conn.close()

    except Exception as e:
        print(f"Sync failed: {e}")

if __name__ == "__main__":
    sync_data()
