from app.database import Base
from app.modules.common.models import LabEnsayoMixin


class ContMatOrganicaEnsayo(LabEnsayoMixin, Base):
    __tablename__ = "cont_mat_organica_ensayos"

