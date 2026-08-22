"""
Capa de servicio para la gestión de Datos Clientes e Informes.
"""
from __future__ import annotations

import logging
from typing import Optional, Tuple, List
from sqlalchemy.orm import Session
from sqlalchemy import or_, desc, asc

from app.modules.datos_clientes.models import DatosCliente
from app.modules.datos_clientes.schemas import DatosClienteCreate, DatosClienteUpdate
from app.modules.common.notifications import log_audit_action

logger = logging.getLogger(__name__)


def evaluar_estado_datos_cliente(data: dict | DatosCliente) -> str:
    """
    Evalúa si un registro de cliente/informe tiene todos los campos obligatorios
    para considerarse COMPLETO o INCOMPLETO.
    """
    def _val(attr: str) -> str:
        if isinstance(data, dict):
            v = data.get(attr)
        else:
            v = getattr(data, attr, None)
        return str(v or "").strip()

    required_fields = [
        "cliente",
        "ruc",
        "domicilio_legal",
        "persona_contacto",
        "email",
        "telefono",
        "solicitante",
        "domicilio_solicitante",
        "proyecto",
        "ubicacion",
    ]

    for field in required_fields:
        val = _val(field)
        if not val or val == "-":
            return "INCOMPLETO"

    return "COMPLETO"


class DatosClientesService:

    @staticmethod
    def listar(
        db: Session,
        search: str = "",
        estado: str = "",
        page: int = 1,
        page_size: int = 25,
    ) -> Tuple[List[DatosCliente], int]:
        """
        Lista registros paginados con filtro por texto y estado.
        """
        query = db.query(DatosCliente).filter(DatosCliente.activo.is_(True))

        if search:
            clean_search = f"%{search.strip()}%"
            query = query.filter(
                or_(
                    DatosCliente.cliente.ilike(clean_search),
                    DatosCliente.ruc.ilike(clean_search),
                    DatosCliente.proyecto.ilike(clean_search),
                    DatosCliente.persona_contacto.ilike(clean_search),
                    DatosCliente.solicitante.ilike(clean_search),
                    DatosCliente.ubicacion.ilike(clean_search),
                )
            )

        if estado:
            clean_estado = estado.strip().upper()
            if clean_estado in ("COMPLETO", "INCOMPLETO"):
                query = query.filter(DatosCliente.estado == clean_estado)

        total = query.count()
        offset = max(0, (page - 1) * page_size)
        items = query.order_by(desc(DatosCliente.id)).offset(offset).limit(page_size).all()

        return items, total

    @staticmethod
    def buscar_autocomplete(
        db: Session,
        search: str = "",
        limit: int = 15,
    ) -> List[DatosCliente]:
        """
        Búsqueda ultrarrápida para autocompletado en Recepción y Ensayos.
        """
        query = db.query(DatosCliente).filter(DatosCliente.activo.is_(True))

        if search:
            clean_search = f"%{search.strip()}%"
            query = query.filter(
                or_(
                    DatosCliente.cliente.ilike(clean_search),
                    DatosCliente.ruc.ilike(clean_search),
                    DatosCliente.proyecto.ilike(clean_search),
                    DatosCliente.persona_contacto.ilike(clean_search),
                )
            )

        return query.order_by(desc(DatosCliente.updated_at)).limit(limit).all()

    @staticmethod
    def obtener_por_id(db: Session, cliente_id: int) -> Optional[DatosCliente]:
        """
        Obtiene un registro por ID.
        """
        return db.query(DatosCliente).filter(
            DatosCliente.id == cliente_id,
            DatosCliente.activo.is_(True)
        ).first()

    @staticmethod
    def crear(
        db: Session,
        obj_in: DatosClienteCreate,
        user_info: Optional[dict] = None,
    ) -> DatosCliente:
        """
        Crea un nuevo registro y calcula su estado.
        """
        data = obj_in.model_dump()
        data["estado"] = evaluar_estado_datos_cliente(data)
        data["activo"] = True

        nuevo_registro = DatosCliente(**data)
        db.add(nuevo_registro)
        db.commit()
        db.refresh(nuevo_registro)

        # Auditoría
        try:
            log_audit_action(
                action="CREAR_DATOS_CLIENTE",
                module="DATOS_CLIENTES",
                user_id=user_info.get("id") if user_info else None,
                user_name=user_info.get("nombre") if user_info else None,
                details={
                    "id": nuevo_registro.id,
                    "cliente": nuevo_registro.cliente,
                    "proyecto": nuevo_registro.proyecto,
                    "estado": nuevo_registro.estado,
                }
            )
        except Exception as err:
            logger.warning("No se pudo emitir log de auditoría: %s", err)

        return nuevo_registro

    @staticmethod
    def actualizar(
        db: Session,
        cliente_id: int,
        obj_in: DatosClienteUpdate,
        user_info: Optional[dict] = None,
    ) -> Optional[DatosCliente]:
        """
        Actualiza un registro existente y recalcula su estado.
        """
        registro = DatosClientesService.obtener_por_id(db, cliente_id)
        if not registro:
            return None

        cambios_antes = {
            "cliente": registro.cliente,
            "ruc": registro.ruc,
            "proyecto": registro.proyecto,
            "persona_contacto": registro.persona_contacto,
            "estado": registro.estado,
        }

        update_data = obj_in.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(registro, key, value)

        registro.estado = evaluar_estado_datos_cliente(registro)
        db.commit()
        db.refresh(registro)

        # Auditoría
        try:
            log_audit_action(
                action="ACTUALIZAR_DATOS_CLIENTE",
                module="DATOS_CLIENTES",
                user_id=user_info.get("id") if user_info else None,
                user_name=user_info.get("nombre") if user_info else None,
                details={
                    "id": registro.id,
                    "antes": cambios_antes,
                    "despues": {
                        "cliente": registro.cliente,
                        "ruc": registro.ruc,
                        "proyecto": registro.proyecto,
                        "persona_contacto": registro.persona_contacto,
                        "estado": registro.estado,
                    }
                }
            )
        except Exception as err:
            logger.warning("No se pudo emitir log de auditoría: %s", err)

        return registro

    @staticmethod
    def eliminar(
        db: Session,
        cliente_id: int,
        user_info: Optional[dict] = None,
    ) -> bool:
        """
        Elimina lógicamente un registro de datos_clientes.
        """
        registro = DatosClientesService.obtener_por_id(db, cliente_id)
        if not registro:
            return False

        registro.activo = False
        db.commit()

        # Auditoría
        try:
            log_audit_action(
                action="ELIMINAR_DATOS_CLIENTE",
                module="DATOS_CLIENTES",
                user_id=user_info.get("id") if user_info else None,
                user_name=user_info.get("nombre") if user_info else None,
                details={
                    "id": registro.id,
                    "cliente": registro.cliente,
                    "proyecto": registro.proyecto,
                }
            )
        except Exception as err:
            logger.warning("No se pudo emitir log de auditoría: %s", err)

        return True


datos_clientes_service = DatosClientesService()
