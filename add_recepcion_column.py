import os
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).resolve().parent / ".env")

from sqlalchemy import text
from app.database import engine

def add_archivo_path():
    with engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE recepciones ADD COLUMN IF NOT EXISTS archivo_path VARCHAR(500);"))
            conn.commit()
            print("Column 'archivo_path' added successfully to 'recepciones'.")
        except Exception as e:
            print(f"Error adding column: {e}")

if __name__ == "__main__":
    add_archivo_path()
