import os
import sys
from pathlib import Path
from sqlalchemy import create_engine, text

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.database import DATABASE_URL

def apply_migration():
    print(f"Connecting to database...")
    engine = create_engine(DATABASE_URL)
    
    sql_path = Path(__file__).resolve().parents[1] / "migrations" / "048_add_fc_to_huanta_probetas.sql"
    if not sql_path.exists():
        print(f"Error: SQL file not found at {sql_path}")
        return
        
    with open(sql_path, "r", encoding="utf-8") as f:
        sql_content = f.read()
        
    print("Applying migration 048...")
    
    with engine.connect() as conn:
        transaction = conn.begin()
        try:
            conn.execute(text(sql_content))
            transaction.commit()
            print("Successfully applied migration 048!")
        except Exception as e:
            transaction.rollback()
            print(f"Error applying SQL: {e}")
            sys.exit(1)

if __name__ == "__main__":
    apply_migration()
