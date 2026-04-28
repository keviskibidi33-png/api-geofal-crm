from pydantic import BaseModel, Field, field_validator
from datetime import date, datetime
from typing import List, Optional
import re

class QuoteItem(BaseModel):
    codigo: str
    descripcion: str
    norma: Optional[str] = None
    acreditado: Optional[str] = None
    costo_unitario: float = Field(ge=0)
    cantidad: float = Field(ge=0)

class QuoteExportRequest(BaseModel):
    cotizacion_numero: Optional[str] = None
    fecha_emision: Optional[date] = None
    fecha_solicitud: Optional[date] = None
    cliente: Optional[str] = None
    ruc: Optional[str] = None
    contacto: Optional[str] = None
    telefono_contacto: Optional[str] = None
    correo: Optional[str] = None
    proyecto: Optional[str] = None
    ubicacion: Optional[str] = None
    personal_comercial: Optional[str] = None
    telefono_comercial: Optional[str] = None
    correo_vendedor: Optional[str] = None
    plazo_dias: Optional[int] = None
    condicion_pago: Optional[str] = None
    condiciones_ids: Optional[List[str]] = Field(default_factory=list)
    include_igv: bool = True
    igv_rate: float = 0.18
    items: List[QuoteItem] = Field(default_factory=list)
    template_id: Optional[str] = None
    user_id: Optional[str] = None
    proyecto_id: Optional[str] = None
    cliente_id: Optional[str] = None

    @field_validator("fecha_emision", "fecha_solicitud", mode="before")
    @classmethod
    def normalize_quote_dates(cls, value):
        if value is None or value == "":
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value

        raw = str(value).strip()
        if not re.fullmatch(r"\d{2}/\d{2}/\d{4}", raw):
            raise ValueError("Fecha inválida. Use el formato DD/MM/YYYY, por ejemplo 27/04/2026.")

        day, month, year = map(int, raw.split("/"))
        try:
            return date(year, month, day)
        except ValueError as exc:
            raise ValueError("Fecha inválida. Use el formato DD/MM/YYYY, por ejemplo 27/04/2026.") from exc

class NextNumberResponse(BaseModel):
    year: int
    sequential: int
    token: str

class ModulePermission(BaseModel):
    read: bool = False
    write: bool = False
    delete: bool = False

class RolePermissions(BaseModel):
    clientes: Optional[ModulePermission] = None
    proyectos: Optional[ModulePermission] = None
    cotizadora: Optional[ModulePermission] = None
    programacion: Optional[ModulePermission] = None
    usuarios: Optional[ModulePermission] = None
    auditoria: Optional[ModulePermission] = None
    configuracion: Optional[ModulePermission] = None
    laboratorio: Optional[ModulePermission] = None
    comercial: Optional[ModulePermission] = None
    administracion: Optional[ModulePermission] = None
    permisos: Optional[ModulePermission] = None

class RoleDefinition(BaseModel):
    role_id: str
    label: str
    description: Optional[str] = None
    permissions: RolePermissions
    is_system: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class RoleUpdate(BaseModel):
    label: Optional[str] = None
    description: Optional[str] = None
    permissions: Optional[RolePermissions] = None
