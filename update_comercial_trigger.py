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

        print("Creating function calculate_dias_atraso_com...")
        cur.execute("""
            CREATE OR REPLACE FUNCTION public.calculate_dias_atraso_com()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $function$
            BEGIN
                -- Logic for Comercial delays:
                -- dias_atraso_envio_coti = CURRENT_DATE - fecha_entrega_com
                
                IF NEW.fecha_entrega_com IS NOT NULL THEN
                    IF CURRENT_DATE > NEW.fecha_entrega_com THEN
                        NEW.dias_atraso_envio_coti := CURRENT_DATE - NEW.fecha_entrega_com;
                    ELSE
                        NEW.dias_atraso_envio_coti := 0;
                    END IF;
                ELSE
                    NEW.dias_atraso_envio_coti := 0;
                END IF;
                
                NEW.updated_at := NOW();
                
                RETURN NEW;
            END;
            $function$;
        """)

        print("Creating trigger trigger_calculate_dias_atraso_com...")
        cur.execute("DROP TRIGGER IF EXISTS trigger_calculate_dias_atraso_com ON programacion_comercial;")
        cur.execute("""
            CREATE TRIGGER trigger_calculate_dias_atraso_com
            BEFORE INSERT OR UPDATE OF fecha_entrega_com ON programacion_comercial
            FOR EACH ROW EXECUTE FUNCTION calculate_dias_atraso_com();
        """)

        conn.commit()
        print("Triggers updated successfully.")
        cur.close()
        conn.close()

    except Exception as e:
        print(f"Update failed: {e}")

if __name__ == "__main__":
    update_trigger()
