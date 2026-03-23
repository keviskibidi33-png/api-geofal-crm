from app.database import Base
from app.modules.common.models import LabEnsayoMixin


class PartLivianasEnsayo(LabEnsayoMixin, Base):
    __tablename__ = "part_livianas_ensayos"

