from sqlalchemy import Column, Integer, String, Date, DateTime, Text
from sqlalchemy.sql import func
from app.database import Base

class SeguimientoClienteComercial(Base):
    """
    Modelo para el Seguimiento de Clientes exclusivo del rol Comercial.
    """
    __tablename__ = "seguimiento_cliente_comercial"

    id = Column(Integer, primary_key=True, index=True)
    no = Column(Integer, nullable=True, index=True)
    fecha_contacto = Column(Date, nullable=True, index=True)
    persona_contacto = Column(String(255), nullable=True)
    numero_celular = Column(String(100), nullable=True)
    email = Column(String(255), nullable=True)
    razon_social = Column(String(255), nullable=True)
    ruc = Column(String(20), nullable=True, index=True)
    asesor = Column(String(100), nullable=True, index=True)
    contacto = Column(String(100), nullable=True)
    rubro = Column(String(100), nullable=True)
    estado_cliente = Column(String(100), nullable=True, index=True)
    servicio_solicitado = Column(Text, nullable=True)
    fecha_ultimo_contacto = Column(Date, nullable=True)
    comentarios_asistente = Column(Text, nullable=True)
    comentarios_asesor = Column(Text, nullable=True)
    numero_cotizacion = Column(String(100), nullable=True, index=True)
    estado_seguimiento = Column(Text, nullable=True)
    
    # Auditoría
    creado_por = Column(String(100), nullable=True)
    fecha_creacion = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    fecha_actualizacion = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
