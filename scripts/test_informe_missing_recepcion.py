import sys
import os

# Add root directory to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.database import SessionLocal
from app.modules.tracing.informe_service import InformeService

def test_informe_missing_recepcion():
    db = SessionLocal()
    numero = "1111-REC-26"
    try:
        print(f"--- Testing Informe Consolidation for {numero} ---")
        data = InformeService.consolidar_datos(db, numero)
        
        print("\nSUCCESS: Data consolidated without reception!")
        print(f"Cliente: {data.get('cliente')}")
        print(f"Items count: {len(data.get('items', []))}")
        
        meta = data.get("_meta", {})
        print(f"Meta Recepcion ID: {meta.get('recepcion_id')}")
        print(f"Meta Verificacion ID: {meta.get('verificacion_id')}")
        
    except Exception as e:
        print(f"\nFAILURE: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    test_informe_missing_recepcion()
