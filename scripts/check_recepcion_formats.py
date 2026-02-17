import sys
import os

# Add root directory to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.database import SessionLocal
from app.modules.recepcion.models import RecepcionMuestra

def check_formats():
    db = SessionLocal()
    try:
        # Get last 20 receptions
        recepciones = db.query(RecepcionMuestra).order_by(RecepcionMuestra.id.desc()).limit(20).all()
        print(f"Checking {len(recepciones)} recent receptions:")
        for r in recepciones:
            print(f"ID: {r.id}, Numero: '{r.numero_recepcion}'")
            
        # Check specifically for "1111" or related
        print("\nSearching for '1111' variants:")
        variants = ["1111", "1111-26", "1111-REC-26", "REC-1111-26"]
        matches = db.query(RecepcionMuestra).filter(RecepcionMuestra.numero_recepcion.in_(variants)).all()
        for m in matches:
            print(f"FOUND: ID: {m.id}, Numero: '{m.numero_recepcion}'")
            
    finally:
        db.close()

if __name__ == "__main__":
    check_formats()
