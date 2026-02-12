import os
import sys
from pathlib import Path
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Add parent directory to sys.path
sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.database import DATABASE_URL

def apply_sql():
    print(f"Connecting to database: {DATABASE_URL.split('@')[-1]}")
    engine = create_engine(DATABASE_URL)
    
    sql_path = Path(__file__).resolve().parent / "storage_setup.sql"
    if not sql_path.exists():
        print(f"Error: SQL file not found at {sql_path}")
        return
        
    with open(sql_path, "r", encoding="utf-8") as f:
        sql_content = f.read()
        
    print("Applying storage policies...")
    
    # Split the SQL into individual statements if necessary, 
    # but SQLAlchemy text() can handle some multi-statement blocks 
    # if the driver supports it. For PostgreSQL, it's safer to execute 
    # as one block or split by semicolon.
    
    with engine.connect() as conn:
        transaction = conn.begin()
        try:
            # We use a raw connection for potentially complex Supabase Storage SQL
            conn.execute(text(sql_content))
            transaction.commit()
            print("Successfully applied storage policies!")
        except Exception as e:
            transaction.rollback()
            print(f"Error applying SQL: {e}")
            sys.exit(1)

if __name__ == "__main__":
    apply_sql()
