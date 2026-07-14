from app.database import Base
from app.modules.common.models import LabEnsayoMixin


class DensidadHuantarEnsayo(LabEnsayoMixin, Base):
    __tablename__ = "densidad_huantar_ensayos"
