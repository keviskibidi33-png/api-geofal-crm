import sys
import os

# Add root directory to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.database import SessionLocal
from app.modules.verificacion.models import VerificacionMuestras
from app.modules.compresion.models import EnsayoCompresion

def check_other_modules():
    db = SessionLocal()
    try:
        print("\nChecking Verificacion for '1111' variants:")
        # We need to manually check because exact match might fail
        # Let's list all verificaciones
        vers = db.query(VerificacionMuestras).limit(10).all()
        for v in vers:
            print(f"VER: ID: {v.id}, Num: '{v.numero_verificacion}'")
            
        print("\nChecking Compresion for '1111' variants:")
        comps = db.query(EnsayoCompresion).limit(10).all()
        for c in comps:
            print(f"COM: ID: {c.id}, Num: '{c.numero_recepcion}'")

    finally:
        db.close()

if __name__ == "__main__":
    check_other_modules()
