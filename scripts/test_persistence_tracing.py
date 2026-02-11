
import sys
import os

# Añadir el directorio raíz al path para poder importar módulos de la app
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.modules.tracing.service import TracingService
from app.modules.recepcion.models import RecepcionMuestra
from app.modules.tracing.models import Trazabilidad

def test_persistence():
    db = SessionLocal()
    test_numero = "99999-TEST"
    
    try:
        print(f"--- Iniciando prueba de persistencia para {test_numero} ---")
        
        # 1. Crear recepción
        recepcion = RecepcionMuestra(
            numero_ot="OT-99999-TEST",
            numero_recepcion=test_numero,
            cliente="CLIENTE TEST PERSISTENCIA",
            domicilio_legal="CALLE TEST 123",
            ruc="20123456789",
            persona_contacto="JUAN PEREZ",
            email="juan@test.com",
            telefono="987654321",
            solicitante="SOLICITANTE TEST",
            domicilio_solicitante="DOMICILIO SOLICITANTE",
            proyecto="PROYECTO TEST PERSISTENCIA",
            ubicacion="LIMA, PERU",
            emision_fisica=True,
            emision_digital=True
        )
        db.add(recepcion)
        db.commit()
        print("1. Recepción creada.")
        
        # 2. Actualizar trazabilidad (debe crear fila verde)
        traza = TracingService.actualizar_trazabilidad(db, test_numero)
        print(f"2. Trazabilidad creada. Estado Recepción: {traza.estado_recepcion}")
        
        # 3. Borrar recepción
        db.delete(recepcion)
        db.commit()
        print("3. Recepción borrada.")
        
        # 4. Actualizar trazabilidad de nuevo (DEBE PERSISTIR EN GRIS/PENDIENTE)
        traza_post = TracingService.actualizar_trazabilidad(db, test_numero)
        
        if traza_post:
            print(f"4. ÉXITO: La traza persiste. Estado Recepción: {traza_post.estado_recepcion}")
        else:
            print("4. FALLO: La traza fue borrada automáticamente (comportamiento antiguo).")
            
        # 5. Borrar traza manualmente (simulando el nuevo endpoint)
        if traza_post:
            db.delete(traza_post)
            db.commit()
            print("5. Traza borrada manualmente.")
            
        # 6. Verificar que ya no existe
        traza_final = db.query(Trazabilidad).filter(Trazabilidad.numero_recepcion == test_numero).first()
        if not traza_final:
            print("6. Verificación final OK: El registro ya no existe.")
        else:
            print("6. ERROR: El registro persiste tras borrado manual.")

    finally:
        db.close()

if __name__ == "__main__":
    test_persistence()
