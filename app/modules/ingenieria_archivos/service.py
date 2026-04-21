from sqlalchemy import or_
from sqlalchemy.orm import Session

from .models import IngenieriaArchivo
from .schemas import IngenieriaArchivoCreate, IngenieriaArchivoUpdate


class IngenieriaArchivosService:
    @staticmethod
    def listar(
        db: Session,
        q: str | None = None,
        categoria: str | None = None,
        modulo_crm: str | None = None,
        estado: str | None = None,
        limit: int = 200,
    ) -> list[IngenieriaArchivo]:
        query = db.query(IngenieriaArchivo)

        if q:
            like_q = f"%{q.strip()}%"
            query = query.filter(
                or_(
                    IngenieriaArchivo.codigo_referencia.ilike(like_q),
                    IngenieriaArchivo.nombre_archivo.ilike(like_q),
                    IngenieriaArchivo.ruta_archivo.ilike(like_q),
                    IngenieriaArchivo.responsable.ilike(like_q),
                )
            )

        if categoria:
            query = query.filter(IngenieriaArchivo.categoria == categoria)
        if modulo_crm:
            query = query.filter(IngenieriaArchivo.modulo_crm == modulo_crm)
        if estado:
            query = query.filter(IngenieriaArchivo.estado == estado)

        return (
            query.order_by(IngenieriaArchivo.fecha_creacion.desc())
            .limit(max(1, min(limit, 500)))
            .all()
        )

    @staticmethod
    def obtener(db: Session, archivo_id: int) -> IngenieriaArchivo | None:
        return db.query(IngenieriaArchivo).filter(IngenieriaArchivo.id == archivo_id).first()

    @staticmethod
    def crear(db: Session, payload: IngenieriaArchivoCreate) -> IngenieriaArchivo:
        data = payload.model_dump()
        data["estado"] = (data.get("estado") or "activo").strip().lower()
        record = IngenieriaArchivo(**data)
        db.add(record)
        db.flush()
        db.refresh(record)
        return record

    @staticmethod
    def actualizar(
        db: Session, record: IngenieriaArchivo, payload: IngenieriaArchivoUpdate
    ) -> IngenieriaArchivo:
        updates = payload.model_dump(exclude_unset=True)
        if "estado" in updates and updates["estado"] is not None:
            updates["estado"] = updates["estado"].strip().lower()

        for key, value in updates.items():
            setattr(record, key, value)

        db.flush()
        db.refresh(record)
        return record

    @staticmethod
    def eliminar(db: Session, record: IngenieriaArchivo) -> None:
        db.delete(record)
        db.flush()
