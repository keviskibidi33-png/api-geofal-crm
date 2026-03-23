from app.database import Base
from app.modules.common.models import LabEnsayoMixin


class TerronesFinoGruesoEnsayo(LabEnsayoMixin, Base):
    __tablename__ = "terrones_fino_grueso_ensayos"

