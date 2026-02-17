import sys
from pathlib import Path
from sqlalchemy.orm import Session
from sqlalchemy import create_engine

# Add app to path
sys.path.append(str(Path(__file__).resolve().parents[0]))

from app.database import SessionLocal
from app.modules.tracing.service import TracingService
from app.modules.tracing.models import Trazabilidad
from app.modules.recepcion.models import RecepcionMuestra
from app.modules.verificacion.models import VerificacionMuestras
from app.modules.compresion.models import EnsayoCompresion

def debug_traza(numero: str):
    db = SessionLocal()
    try:
        print(f"--- Debugging Trace for: {numero} ---")
        
        # 1. Search in source modules
        rec, can = TracingService._buscar_recepcion_flexible(db, numero)
        print(f"Recepcion Found: {rec.id if rec else 'None'} (Canonical: {can})")
        
        # Manually search variants for Verificacion and Compresion
        base_num = TracingService._extraer_numero_base(numero)
        print(f"Base Num: {base_num}")
        
        verif = db.query(VerificacionMuestras).filter(VerificacionMuestras.numero_verificacion.ilike(f"%{base_num}%")).all()
        print(f"Verificacion Matches ({len(verif)}): {[v.numero_verificacion for v in verif]}")
        
        comp = db.query(EnsayoCompresion).filter(EnsayoCompresion.numero_recepcion.ilike(f"%{base_num}%")).all()
        print(f"Compresion Matches ({len(comp)}): {[c.numero_recepcion for c in comp]}")
        
        # 2. Check Tracing table
        traza = db.query(Trazabilidad).filter(Trazabilidad.numero_recepcion == can).first()
        if traza:
            print(f"Existing Trazabilidad Record found: ID {traza.id}")
            print(f"States: REC={traza.estado_recepcion}, VER={traza.estado_verificacion}, COM={traza.estado_compresion}, INF={traza.estado_informe}")
            print(f"Data Consolidada: {traza.data_consolidada}")
        else:
            print("No Trazabilidad record for this canonical number.")
            
        # 3. Simulate Update
        print("\n--- Simulating Update ---")
        updated_traza = TracingService.actualizar_trazabilidad(db, numero)
        if updated_traza:
            print(f"After Update States: REC={updated_traza.estado_recepcion}, VER={updated_traza.estado_verificacion}, COM={updated_traza.estado_compresion}")
        else:
            print("Update returned None")
            
    finally:
        db.close()

if __name__ == "__main__":
    test_nums = ["1111-26", "11122", "4545-26"]
    for n in test_nums:
        debug_traza(n)
        print("="*40)
