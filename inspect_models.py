from app.modules.recepcion.models import RecepcionMuestra, MuestraConcreto
from sqlalchemy import inspect

print("Inspecting MuestraConcreto properties...")
mapper = inspect(MuestraConcreto)
print(f"Properties: {[p.key for p in mapper.all_orm_descriptors]}")
if 'recepcion' in [p.key for p in mapper.all_orm_descriptors]:
    print("Property 'recepcion' found!")
else:
    print("Property 'recepcion' NOT found!")

print("\nInspecting RecepcionMuestra properties...")
mapper_r = inspect(RecepcionMuestra)
print(f"Properties: {[p.key for p in mapper_r.all_orm_descriptors]}")
