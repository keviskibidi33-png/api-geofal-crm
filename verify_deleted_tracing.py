import sys
from pathlib import Path
from sqlalchemy.orm import Session

# Add app to path
sys.path.append(str(Path(__file__).resolve().parents[0]))

from app.database import SessionLocal
from app.modules.tracing.models import Trazabilidad

def verify_deleted(nums):
    db = SessionLocal()
    try:
        for n in nums:
            # Flexible search to be sure
            traza = db.query(Trazabilidad).filter(Trazabilidad.numero_recepcion.ilike(f"%{n}%")).first()
            if traza:
                print(f"FAILED: Record {n} still exists (ID {traza.id}) as {traza.numero_recepcion}")
            else:
                print(f"SUCCESS: Record {n} is gone from Trazabilidad table.")
    finally:
        db.close()

if __name__ == "__main__":
    verify_deleted(["1111-26", "11122", "4545-26"])
