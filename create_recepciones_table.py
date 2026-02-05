import os
from dotenv import load_dotenv
from pathlib import Path

# Load env vars usually located in main dir
load_dotenv(Path(__file__).resolve().parent / ".env")

from sqlalchemy import text
from app.database import engine

def create_recepciones_table():
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS recepciones (
                id SERIAL PRIMARY KEY,
                numero_recepcion VARCHAR(50) NOT NULL,
                numero_ot VARCHAR(50) NOT NULL,
                numero_cotizacion VARCHAR(50),
                cliente VARCHAR(255),
                domicilio_legal VARCHAR(255),
                ruc VARCHAR(20),
                persona_contacto VARCHAR(255),
                email VARCHAR(255),
                telefono VARCHAR(50),
                solicitante VARCHAR(255),
                domicilio_solicitante VARCHAR(255),
                proyecto VARCHAR(255),
                ubicacion VARCHAR(255),
                
                fecha_recepcion DATE,
                fecha_estimada_culminacion DATE,
                
                emision_fisica BOOLEAN DEFAULT FALSE,
                emision_digital BOOLEAN DEFAULT TRUE,
                
                entregado_por VARCHAR(255),
                recibido_por VARCHAR(255),
                
                muestras JSONB,
                
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.commit()
        print("Table 'recepciones' created successfully (or already exists).")

if __name__ == "__main__":
    create_recepciones_table()
