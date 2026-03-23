from app.database import Base
from app.modules.common.models import LabEnsayoMixin


class SulMagnesioEnsayo(LabEnsayoMixin, Base):
    __tablename__ = "sul_magnesio_ensayos"

