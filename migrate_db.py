
import os
import psycopg2
from dotenv import load_dotenv

def migrate():
    load_dotenv()
    dsn = os.getenv("QUOTES_DATABASE_URL")
    if not dsn:
        print("Error: QUOTES_DATABASE_URL not found")
        return

    try:
        conn = psycopg2.connect(dsn)
        conn.autocommit = True
        with conn.cursor() as cur:
            print("Dropping legacy table 'recepciones' if exists...")
            cur.execute("DROP TABLE IF EXISTS recepciones;")
            
            print("Cleaning up 'url_excel' and adding 'object_key'/'bucket' columns...")
            # Remove the previous attempt column if it exists to keep it clean
            cur.execute("ALTER TABLE recepcion DROP COLUMN IF EXISTS url_excel;")
            
            cur.execute("ALTER TABLE recepcion ADD COLUMN IF NOT EXISTS bucket TEXT;")
            cur.execute("ALTER TABLE recepcion ADD COLUMN IF NOT EXISTS object_key TEXT;")
            
            print("Migration completed successfully.")
    except Exception as e:
        print(f"Migration failed: {e}")
    finally:
        if 'conn' in locals() and conn:
            conn.close()

if __name__ == "__main__":
    migrate()
