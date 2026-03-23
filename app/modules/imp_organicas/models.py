from app.database import Base
from app.modules.common.models import LabEnsayoMixin


class ImpOrganicasEnsayo(LabEnsayoMixin, Base):
    __tablename__ = "imp_organicas_ensayos"

