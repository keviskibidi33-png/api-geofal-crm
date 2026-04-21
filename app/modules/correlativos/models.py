from sqlalchemy import Column, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.sql import func

from app.database import Base


class CorrelativoReserva(Base):
    __tablename__ = "correlativos_reserva"

    id = Column(Integer, primary_key=True, index=True)
    numero = Column(Integer, nullable=False, unique=True, index=True)
    user_id = Column(String(80), nullable=False, index=True)
    fecha = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)
    documento_referencia = Column(String(255), nullable=False)
    proposito = Column(Text, nullable=True)


class CorrelativoTurno(Base):
    __tablename__ = "correlativos_turnos"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_correlativos_turnos_user_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(80), nullable=False, index=True)
    estado = Column(String(20), nullable=False, default="waiting", index=True)
    joined_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)
    last_seen_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)
