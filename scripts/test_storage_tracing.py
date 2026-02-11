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

def test_storage_awareness():
    db = SessionLocal()
    try:
        print("### Testing Storage Awareness in Tracing ###")
        
        # 1. Create a mock record in Recepcion with a non-existent object_key
        mock_num = "TEST-9999"
        recepcion = RecepcionMuestra(
            numero_recepcion=mock_num,
            numero_ot="OT-TEST-9999",
            cliente="TEST CLIENT",
            domicilio_legal="Test",
            ruc="12345678901",
            persona_contacto="Test",
            email="test@test.com",
            telefono="123",
            solicitante="Test",
            domicilio_solicitante="Test",
            proyecto="TEST PROJECT",
            ubicacion="Test",
            bucket="recepciones",
            object_key="non_existent_file_12345.xlsx", # This doesn't exist
            estado="PENDIENTE"
        )
        db.add(recepcion)
        db.commit()
        print(f"Record created: {mock_num}")
        
        # 2. Update Trazabilidad
        traza = TracingService.actualizar_trazabilidad(db, mock_num)
        
        print(f"Status in Tracing: {traza.estado_recepcion}")
        if traza.estado_recepcion == "en_proceso": # Should be en_proceso, not completado
            print("[SUCCESS] Tracking correctly detected missing file and set status to 'en_proceso'")
        elif traza.estado_recepcion == "completado":
            print("[FAILURE] Tracking marked as 'completado' even with missing file")
        else:
            print(f"[ERROR] Unexpected status: {traza.estado_recepcion}")
            
        # Cleanup
        db.delete(recepcion)
        db.delete(traza)
        db.commit()
        print("Cleanup done.")
        
    except Exception as e:
        print(f"Error: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    test_storage_awareness()
