from sqlalchemy.orm import configure_mappers
from app.database import Base, engine
from app.modules.recepcion.models import RecepcionMuestra, MuestraConcreto
from app.modules.verificacion.models import VerificacionMuestras, MuestraVerificada
from app.modules.compresion.models import EnsayoCompresion, ItemCompresion

try:
    print("Configuring mappers...")
    configure_mappers()
    print("Mappers configured successfully!")
except Exception as e:
    import traceback
    traceback.print_exc()
