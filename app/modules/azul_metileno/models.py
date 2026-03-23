from app.database import Base
from app.modules.common.models import LabEnsayoMixin


class AzulMetilenoEnsayo(LabEnsayoMixin, Base):
    __tablename__ = "azul_metileno_ensayos"

