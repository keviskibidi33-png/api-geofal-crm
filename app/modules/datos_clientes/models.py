"""
Modelos SQLAlchemy para el módulo Datos Clientes e Informes.
"""
from __future__ import annotations

from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, func
from app.database import Base


class DatosCliente(Base):
    """
    Registro maestro de perfiles de Clientes y Proyectos para Informes de Laboratorio.
    """
    __tablename__ = "datos_clientes"

    id = Column(Integer, primary_key=True, index=True)
    
    # DATOS CLIENTE
    cliente = Column(String(255), nullable=False, index=True, comment="Razón Social del Cliente")
    ruc = Column(String(20), nullable=False, index=True, comment="RUC o documento de identidad")
    domicilio_legal = Column(Text, nullable=False, comment="Dirección legal / fiscal del cliente")
    persona_contacto = Column(String(255), nullable=True, comment="Persona de contacto en obra / proyecto")
    email = Column(String(255), nullable=True, comment="Correo electrónico de contacto")
    telefono = Column(String(50), nullable=True, comment="Teléfono de contacto")
    
    # DATOS DEL INFORME
    solicitante = Column(String(255), nullable=False, comment="Entidad o persona solicitante")
    domicilio_solicitante = Column(Text, nullable=False, comment="Domicilio legal del solicitante")
    proyecto = Column(String(500), nullable=False, index=True, comment="Nombre del proyecto u obra")
    ubicacion = Column(Text, nullable=False, comment="Ubicación física del proyecto")
    
    # METADATOS Y CONTROL
    estado = Column(String(20), nullable=False, default="INCOMPLETO", index=True, comment="COMPLETO o INCOMPLETO")
    activo = Column(Boolean, nullable=False, default=True, comment="Estado activo para borrado lógico")
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
