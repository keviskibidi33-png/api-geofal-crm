from __future__ import annotations

from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session, joinedload

from .models import (
    ControlEnsayoCatalogo,
    ControlEnsayoCounter,
    ControlInforme,
    ControlInformeDetalle,
)


class ControlInformesService:
    @staticmethod
    def obtener_dashboard(db: Session) -> dict:
        catalogo = (
            db.query(ControlEnsayoCatalogo)
            .filter(ControlEnsayoCatalogo.activo.is_(True))
            .order_by(ControlEnsayoCatalogo.area.asc(), ControlEnsayoCatalogo.orden.asc(), ControlEnsayoCatalogo.nombre.asc())
            .all()
        )
        counters_rows = db.query(ControlEnsayoCounter).all()
        counters = {row.ensayo_codigo: row.ultimo_numero for row in counters_rows}

        return {
            "catalogo": catalogo,
            "counters": [
                {"codigo": item.codigo, "ultimo_numero": int(counters.get(item.codigo, 0))}
                for item in catalogo
            ],
        }

    @staticmethod
    def listar_informes(db: Session, limit: int = 30, offset: int = 0) -> tuple[int, list[ControlInforme]]:
        base_query = db.query(ControlInforme)
        total = base_query.count()
        items = (
            base_query.options(joinedload(ControlInforme.detalles))
            .order_by(ControlInforme.created_at.desc(), ControlInforme.id.desc())
            .offset(max(0, offset))
            .limit(max(1, min(limit, 200)))
            .all()
        )
        return total, items

    @staticmethod
    def crear_informe(
        db: Session,
        *,
        responsable_user_id: str | None,
        responsable_nombre: str | None,
        archivo_nombre: str,
        archivo_url: str | None,
        observaciones: str | None,
        fecha: date | None,
        ensayos: list[str],
    ) -> ControlInforme:
        clean_codes = [str(c).strip().lower() for c in ensayos if str(c).strip()]
        clean_codes = list(dict.fromkeys(clean_codes))
        if not clean_codes:
            raise ValueError("Debes seleccionar al menos un ensayo")

        catalog_rows = (
            db.query(ControlEnsayoCatalogo)
            .filter(ControlEnsayoCatalogo.codigo.in_(clean_codes), ControlEnsayoCatalogo.activo.is_(True))
            .all()
        )
        catalog_map = {row.codigo: row for row in catalog_rows}

        missing = [code for code in clean_codes if code not in catalog_map]
        if missing:
            raise ValueError(f"Ensayos no válidos: {', '.join(missing)}")

        informe = ControlInforme(
            fecha=fecha or date.today(),
            responsable_user_id=responsable_user_id,
            responsable_nombre=responsable_nombre,
            archivo_nombre=archivo_nombre.strip(),
            archivo_url=(archivo_url or "").strip() or None,
            observaciones=(observaciones or "").strip() or None,
        )
        db.add(informe)
        db.flush()

        for code in clean_codes:
            counter = (
                db.query(ControlEnsayoCounter)
                .filter(ControlEnsayoCounter.ensayo_codigo == code)
                .with_for_update()
                .first()
            )
            if not counter:
                counter = ControlEnsayoCounter(ensayo_codigo=code, ultimo_numero=0)
                db.add(counter)
                db.flush()

            next_number = int(counter.ultimo_numero or 0) + 1
            counter.ultimo_numero = next_number

            catalog_item = catalog_map[code]
            db.add(
                ControlInformeDetalle(
                    informe_id=informe.id,
                    ensayo_codigo=code,
                    ensayo_nombre=catalog_item.nombre,
                    numero_asignado=next_number,
                )
            )

        db.flush()
        db.refresh(informe)

        informe = (
            db.query(ControlInforme)
            .options(joinedload(ControlInforme.detalles))
            .filter(ControlInforme.id == informe.id)
            .first()
        )
        return informe

    @staticmethod
    def obtener_resumen(db: Session, area: str = "PROBETAS", anio: int | None = None, mes: int | None = None) -> dict:
        today = date.today()
        y = int(anio or today.year)
        m = int(mes or today.month)
        if m < 1 or m > 12:
            raise ValueError("Mes inválido")

        start_date = date(y, 1, 1)
        if m == 12:
            end_date = date(y + 1, 1, 1)
        else:
            end_date = date(y, m + 1, 1) # Keep end_date for month context if needed, but start is annual

        area_list = [a.strip().upper() for a in area.split(",") if a.strip()]
        if not area_list:
            area_list = ["PROBETAS"]

        # Log for debugging (will show in dev-backend.log)
        print(f"DEBUG: obtener_resumen area_list={area_list}")

        catalogo = (
            db.query(ControlEnsayoCatalogo)
            .filter(
                ControlEnsayoCatalogo.activo.is_(True),
                ControlEnsayoCatalogo.area.in_(area_list),
            )
            .order_by(ControlEnsayoCatalogo.area.asc(), ControlEnsayoCatalogo.orden.asc(), ControlEnsayoCatalogo.nombre.asc())
            .all()
        )

        stats_rows = db.execute(
            text(
                """
                WITH latest_detalles AS (
                    SELECT
                        d.ensayo_codigo,
                        d.numero_asignado,
                        d.enviado,
                        i.responsable_nombre,
                        ROW_NUMBER() OVER(PARTITION BY d.ensayo_codigo ORDER BY d.numero_asignado DESC) as rn
                    FROM control_informe_detalles d
                    JOIN control_informes i ON i.id = d.informe_id
                    JOIN control_ensayos_catalogo c ON c.codigo = d.ensayo_codigo
                )
                SELECT
                    d.ensayo_codigo AS codigo,
                    MAX(d.numero_asignado) AS ultimo_numero,
                    COUNT(*) FILTER (WHERE i.fecha >= :start_date AND i.fecha < :end_date) AS total_anio,
                    bool_or(ld.enviado) FILTER (WHERE ld.rn = 1) AS ultimo_enviado,
                    MAX(ld.responsable_nombre) FILTER (WHERE ld.rn = 1) AS responsable_nombre
                FROM control_informe_detalles d
                JOIN control_informes i ON i.id = d.informe_id
                LEFT JOIN latest_detalles ld ON ld.ensayo_codigo = d.ensayo_codigo AND ld.rn = 1
                GROUP BY d.ensayo_codigo
                """
            ),
            {"start_date": start_date, "end_date": date(y + 1, 1, 1)}, # Full year end date
        ).mappings().all()
        stats_map = {str(r["codigo"]): r for r in stats_rows}

        items = []
        for item in catalogo:
            stats = stats_map.get(item.codigo)
            ultimo_numero = int(stats["ultimo_numero"]) if stats and stats.get("ultimo_numero") is not None else 0
            total_anio = int(stats["total_anio"]) if stats and stats.get("total_anio") is not None else 0
            ultimo_enviado = bool(stats["ultimo_enviado"]) if stats and stats.get("ultimo_enviado") is not None else False
            responsable = str(stats["responsable_nombre"]) if stats and stats.get("responsable_nombre") is not None else "-"
            items.append(
                {
                    "codigo": item.codigo,
                    "nombre": item.nombre,
                    "ultimo_informe": f"#{ultimo_numero}" if ultimo_numero > 0 else "-",
                    "total_anio": total_anio,
                    "ultimo_enviado": ultimo_enviado,
                    "ultimo_responsable": responsable,
                }
            )

        return {"area": area, "anio": y, "mes": m, "items": items}

    @staticmethod
    def toggle_enviado(db: Session, ensayo_codigo: str, toggle_value: bool | None = None) -> bool:
        """Toggle or set the 'enviado' status for the LATEST report of a specific ensayo_codigo."""
        latest = (
            db.query(ControlInformeDetalle)
            .filter(ControlInformeDetalle.ensayo_codigo == ensayo_codigo)
            .order_by(ControlInformeDetalle.numero_asignado.desc())
            .first()
        )
        if not latest:
            raise ValueError(f"No hay informes para el ensayo {ensayo_codigo}")

        if toggle_value is not None:
            latest.enviado = toggle_value
        else:
            latest.enviado = not latest.enviado

        db.commit()
        db.refresh(latest)
        return latest.enviado
