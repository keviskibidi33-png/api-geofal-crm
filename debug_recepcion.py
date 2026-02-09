from app.database import SessionLocal
from app.modules.recepcion.models import RecepcionMuestra

db = SessionLocal()
try:
    print("--- FIRST 10 RECEPCIONES ---")
    recepciones = db.query(RecepcionMuestra).limit(10).all()
    for r in recepciones:
        print(f"ID: {r.id}, Numero: '{r.numero_recepcion}'")

    print("\n--- SEARCHING FOR '1111' ---")
    matches = db.query(RecepcionMuestra).filter(RecepcionMuestra.numero_recepcion.like("%1111%")).all()
    for r in matches:
        print(f"MATCH: '{r.numero_recepcion}'")

except Exception as e:
    print(f"Error: {e}")
finally:
    db.close()
