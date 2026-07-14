import os
import sys
from pathlib import Path
from sqlalchemy import create_engine, text

# Add parent directory to sys.path
sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.database import DATABASE_URL

def apply_migration():
    print(f"Connecting to database: {DATABASE_URL.split('@')[-1] if '@' in DATABASE_URL else DATABASE_URL}")
    engine = create_engine(DATABASE_URL)
    
    sql_path = Path(__file__).resolve().parents[1] / "migrations" / "045_add_control_probetas_fields.sql"
    if not sql_path.exists():
        print(f"Error: SQL file not found at {sql_path}")
        return
        
    with open(sql_path, "r", encoding="utf-8") as f:
        sql_content = f.read()
        
    print("Applying migration 045...")
    
    with engine.connect() as conn:
        transaction = conn.begin()
        try:
            conn.execute(text(sql_content))
            transaction.commit()
            print("Successfully applied migration 045!")
        except Exception as e:
            transaction.rollback()
            print(f"Error applying SQL: {e}")
            sys.exit(1)

if __name__ == "__main__":
    apply_migration()
