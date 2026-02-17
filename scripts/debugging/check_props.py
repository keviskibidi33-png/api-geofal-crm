from app.modules.recepcion.models import RecepcionMuestra, MuestraConcreto
from sqlalchemy import inspect

mapper = inspect(MuestraConcreto)
has_recepcion = 'recepcion' in [p.key for p in mapper.all_orm_descriptors]
has_recepcion_parent = 'recepcion_parent' in [p.key for p in mapper.all_orm_descriptors]
print(f"MuestraConcreto has 'recepcion' property: {has_recepcion}")
print(f"MuestraConcreto has 'recepcion_parent' property: {has_recepcion_parent}")

mapper_r = inspect(RecepcionMuestra)
has_muestras = 'muestras' in [p.key for p in mapper_r.all_orm_descriptors]
print(f"RecepcionMuestra has 'muestras' property: {has_muestras}")
