from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class ControlEnsayoCatalogo(Base):
    __tablename__ = "control_ensayos_catalogo"

    id = Column(Integer, primary_key=True, index=True)
    codigo = Column(String(60), nullable=False, unique=True, index=True)
    nombre = Column(String(140), nullable=False)
    area = Column(String(80), nullable=True, index=True)
    orden = Column(Integer, nullable=False, default=0)
    activo = Column(Boolean, nullable=False, default=True, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=func.now())


class ControlEnsayoCounter(Base):
    __tablename__ = "control_ensayo_counters"

    id = Column(Integer, primary_key=True, index=True)
    ensayo_codigo = Column(
        String(60),
        ForeignKey("control_ensayos_catalogo.codigo", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    ultimo_numero = Column(Integer, nullable=False, default=0)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=func.now(), onupdate=func.now())


class ControlInforme(Base):
    __tablename__ = "control_informes"

    id = Column(Integer, primary_key=True, index=True)
    fecha = Column(Date, nullable=False)
    responsable_user_id = Column(String(80), nullable=True, index=True)
    responsable_nombre = Column(String(140), nullable=True)
    archivo_nombre = Column(String(255), nullable=False)
    archivo_url = Column(Text, nullable=True)
    observaciones = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=func.now())

    detalles = relationship("ControlInformeDetalle", back_populates="informe", cascade="all, delete-orphan")


class ControlInformeDetalle(Base):
    __tablename__ = "control_informe_detalles"
    __table_args__ = (
        UniqueConstraint("ensayo_codigo", "numero_asignado", name="uq_control_informe_detalle_numero_por_ensayo"),
        UniqueConstraint("informe_id", "ensayo_codigo", name="uq_control_informe_detalle_un_ensayo_por_informe"),
    )

    id = Column(Integer, primary_key=True, index=True)
    informe_id = Column(Integer, ForeignKey("control_informes.id", ondelete="CASCADE"), nullable=False, index=True)
    ensayo_codigo = Column(
        String(60),
        ForeignKey("control_ensayos_catalogo.codigo", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    ensayo_nombre = Column(String(140), nullable=False)
    numero_asignado = Column(Integer, nullable=False)
    enviado = Column(Boolean, nullable=False, default=False, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=func.now())

    informe = relationship("ControlInforme", back_populates="detalles")
