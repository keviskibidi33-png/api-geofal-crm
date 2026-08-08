"""Pydantic models for Roles & Permissions module."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ModulePermission(BaseModel):
    read: bool = False
    write: bool = False
    delete: bool = False


class RolePermissions(BaseModel):
    clientes: ModulePermission | None = None
    proyectos: ModulePermission | None = None
    cotizadora: ModulePermission | None = None
    programacion: ModulePermission | None = None
    recepcion: ModulePermission | None = None
    verificacion_muestras: ModulePermission | None = None
    compresion: ModulePermission | None = None
    tracing: ModulePermission | None = None
    control_probetas: ModulePermission | None = None
    densidad_huantar: ModulePermission | None = None
    humedad: ModulePermission | None = None
    cont_humedad: ModulePermission | None = None
    planas: ModulePermission | None = None
    caras: ModulePermission | None = None
    cbr: ModulePermission | None = None
    proctor: ModulePermission | None = None
    llp: ModulePermission | None = None
    gran_suelo: ModulePermission | None = None
    gran_agregado: ModulePermission | None = None
    abra: ModulePermission | None = None
    abrass: ModulePermission | None = None
    peso_unitario: ModulePermission | None = None
    tamiz: ModulePermission | None = None
    equi_arena: ModulePermission | None = None
    ge_fino: ModulePermission | None = None
    ge_grueso: ModulePermission | None = None
    cd: ModulePermission | None = None
    ph: ModulePermission | None = None
    cloro_soluble: ModulePermission | None = None
    sales_solubles: ModulePermission | None = None
    sulfatos_solubles: ModulePermission | None = None
    compresion_no_confinada: ModulePermission | None = None
    cont_mat_organica: ModulePermission | None = None
    terrones_fino_grueso: ModulePermission | None = None
    azul_metileno: ModulePermission | None = None
    part_livianas: ModulePermission | None = None
    imp_organicas: ModulePermission | None = None
    sul_magnesio: ModulePermission | None = None
    angularidad: ModulePermission | None = None
    ingenieria_archivos: ModulePermission | None = None
    control_informes: ModulePermission | None = None
    correlativos: ModulePermission | None = None
    usuarios: ModulePermission | None = None
    auditoria: ModulePermission | None = None
    configuracion: ModulePermission | None = None
    laboratorio: ModulePermission | None = None
    oficina_tecnica: ModulePermission | None = None
    comercial: ModulePermission | None = None
    administracion: ModulePermission | None = None
    permisos: ModulePermission | None = None


class RoleDefinition(BaseModel):
    role_id: str
    label: str
    description: str | None = None
    permissions: RolePermissions
    is_system: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None


class RoleUpdate(BaseModel):
    label: str | None = None
    description: str | None = None
    permissions: RolePermissions | None = None


class UserPermissionOverrideUpdate(BaseModel):
    enabled: bool = True
    permissions: dict[str, ModulePermission] = Field(default_factory=dict)


class HeartbeatRequest(BaseModel):
    user_id: str
