import psycopg2
import os
from dotenv import load_dotenv

def update_trigger():
    load_dotenv()
    dsn = os.getenv("QUOTES_DATABASE_URL")
    if not dsn:
        print("Error: QUOTES_DATABASE_URL not found")
        return

    try:
        conn = psycopg2.connect(dsn)
        cur = conn.cursor()

        print("Updating calculate_dias_atraso_com function...")
        
        sql = """
        CREATE OR REPLACE FUNCTION calculate_dias_atraso_com()
        RETURNS TRIGGER AS $$
        BEGIN
            -- Logic matching Lab version: allow negative values
            IF NEW.fecha_entrega_com IS NOT NULL THEN
                NEW.dias_atraso_envio_coti := CURRENT_DATE - NEW.fecha_entrega_com;
            ELSE
                NEW.dias_atraso_envio_coti := 0;
            END IF;
            
            NEW.updated_at := NOW();
            
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
        
        cur.execute(sql)
        conn.commit()
        print("Trigger function updated successfully.")
        cur.close()
        conn.close()

    except Exception as e:
        print(f"Update failed: {e}")

if __name__ == "__main__":
    update_trigger()
