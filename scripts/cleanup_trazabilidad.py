import sys
import os
from pathlib import Path

# Add project root to sys.path
root_dir = Path(__file__).resolve().parents[1]
sys.path.append(str(root_dir))

from app.database import SessionLocal
from app.modules.tracing.service import TracingService
from app.modules.tracing.models import Trazabilidad
from app.modules.recepcion.models import RecepcionMuestra
from app.modules.verificacion.models import VerificacionMuestras
from app.modules.compresion.models import EnsayoCompresion

def cleanup():
    db = SessionLocal()
    try:
        print("### Iniciando Limpieza Exhaustiva de Trazabilidad ###")
        trazas = db.query(Trazabilidad).all()
        print(f"Revisando {len(trazas)} registros...")
        
        deleted_count = 0
        for t in trazas:
            num = t.numero_recepcion
            base_num = TracingService._extraer_numero_base(num)
            
            # Variantes a buscar
            variantes = list(set([num, base_num, f"REC-{base_num}", f"{base_num}-REC"]))
            
            found = False
            for v in variantes:
                r = db.query(RecepcionMuestra).filter(RecepcionMuestra.numero_recepcion == v).first()
                if r: found = True; break
                
                v_mod = db.query(VerificacionMuestras).filter(VerificacionMuestras.numero_verificacion == v).first()
                if v_mod: found = True; break
                
                c = db.query(EnsayoCompresion).filter(EnsayoCompresion.numero_recepcion == v).first()
                if c: found = True; break
            
            if not found:
                print(f"[DELETE] {num} (huérfano real)")
                db.delete(t)
                deleted_count += 1
            else:
                print(f"[KEEP] {num} (existe en origen)")
        
        db.commit()
        print(f"\nFinalizado. Borrados: {deleted_count}")
    except Exception as e:
        print(f"Error: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    cleanup()
