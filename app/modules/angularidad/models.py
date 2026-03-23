from app.database import Base
from app.modules.common.models import LabEnsayoMixin


class AngularidadEnsayo(LabEnsayoMixin, Base):
    __tablename__ = "angularidad_ensayos"

