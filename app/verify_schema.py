
import os
import sys
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Load env from .env file
load_dotenv(".env")

DATABASE_URL = os.getenv("QUOTES_DATABASE_URL")
if not DATABASE_URL:
    print("Error: QUOTES_DATABASE_URL not set")
    sys.exit(1)

print(f"Connecting to {DATABASE_URL}")
engine = create_engine(DATABASE_URL)

def check_and_create_recepciones():
    with engine.connect() as conn:
        try:
            # Check if table exists
            result = conn.execute(text("SELECT to_regclass('public.recepciones')")).fetchone()
            if result[0]:
                print("Table 'recepciones' ALREADY EXISTS.")
                
                # Optional: Check columns just in case
                cols = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='recepciones'")).fetchall()
                print("Columns found:", [c[0] for c in cols])
                
            else:
                print("Table 'recepciones' DOES NOT EXIST. Creating it...")
                conn.execute(text("""
                    CREATE TABLE recepciones (
                        id SERIAL PRIMARY KEY,
                        numero_ot VARCHAR(50),
                        numero_recepcion VARCHAR(50),
                        numero_cotizacion VARCHAR(50),
                        cliente VARCHAR(255),
                        domicilio_legal TEXT,
                        ruc VARCHAR(20),
                        persona_contacto VARCHAR(255),
                        email VARCHAR(255),
                        telefono VARCHAR(50),
                        solicitante VARCHAR(255),
                        domicilio_solicitante TEXT,
                        proyecto VARCHAR(255),
                        ubicacion TEXT,
                        
                        fecha_recepcion DATE,
                        fecha_estimada_culminacion DATE,
                        
                        emision_fisica BOOLEAN DEFAULT false,
                        emision_digital BOOLEAN DEFAULT true,
                        
                        entregado_por VARCHAR(255),
                        recibido_por VARCHAR(255),
                        
                        muestras JSONB,
                        
                        estado VARCHAR(50) DEFAULT 'PENDIENTE',
                        archivo_path VARCHAR(255),
                        
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """))
                conn.commit()
                print("Table 'recepciones' created successfully.")
                
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    check_and_create_recepciones()
