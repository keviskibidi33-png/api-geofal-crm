"""
Servicio para consolidar datos de Recepción + Verificación + Compresión
y generar el Informe (Resumen de Ensayo).

Fuente de verdad: COMPRESIÓN (cada ItemCompresion es una fila del informe).
Cross-reference: Verificación y Recepción por codigo_lem + item_numero.
"""

import re
import logging
from typing import Optional, List, Dict
from sqlalchemy.orm import Session

from app.modules.recepcion.models import RecepcionMuestra, MuestraConcreto
from app.modules.verificacion.models import VerificacionMuestras, MuestraVerificada
from app.modules.compresion.models import EnsayoCompresion, ItemCompresion
from .service import TracingService

logger = logging.getLogger(__name__)


def _norm_lem(code: str) -> str:
    """Normaliza un código LEM para comparación segura."""
    return (code or "").strip().upper()


def _index_by_lem_and_item(records, lem_attr: str, item_attr: str = "item_numero") -> Dict[str, list]:
    """
    Indexa registros por codigo_lem.
    Retorna {LEM_UPPER: [record, ...]} — lista para manejar duplicados.
    """
    index: Dict[str, list] = {}
    for r in records:
        key = _norm_lem(getattr(r, lem_attr, ""))
        if key:
            index.setdefault(key, []).append(r)
    return index


def _buscar_modulos(db: Session, numero_recepcion: str, canonical: str):
    """Busca verificación y compresión con variantes de número."""
    base_num = TracingService._extraer_numero_base(numero_recepcion)
    source = canonical or numero_recepcion or ""
    year_match = re.search(r'-(\d{2})$', source)
    year_suffix = year_match.group(1) if year_match else ""

    search_nums = list(dict.fromkeys(filter(None, [
        canonical, base_num, numero_recepcion,
        f"{base_num}-REC",
        f"{base_num}-REC-{year_suffix}" if year_suffix else None,
    ])))

    verificacion = None
    compresion = None
    for num in search_nums:
        if not verificacion:
            verificacion = db.query(VerificacionMuestras).filter(
                VerificacionMuestras.numero_verificacion == num
            ).first()
        if not compresion:
            compresion = db.query(EnsayoCompresion).filter(
                EnsayoCompresion.numero_recepcion == num
            ).first()
        if verificacion and compresion:
            break

    return verificacion, compresion


def _extraer_fecha_rotura(compresion: EnsayoCompresion, primera_muestra) -> str:
    """Obtiene la fecha de rotura real desde compresión, con fallback a recepción."""
    if compresion and compresion.items:
        for ic in sorted(compresion.items, key=lambda x: x.item or 0):
            if ic.fecha_ensayo:
                return ic.fecha_ensayo
    if primera_muestra:
        return primera_muestra.fecha_rotura or ""
    return ""


def _build_item(ic: ItemCompresion, ver_list: list, rec_list: list, item_idx: int) -> dict:
    """
    Construye un item consolidado para el informe.
    
    Para códigos LEM duplicados (ej: 15314-CO-26 aparece 2 veces),
    usa item_idx para seleccionar el registro correcto de verificación/recepción.
    """
    # Seleccionar el registro que corresponde por posición en la lista de duplicados
    mv = ver_list[item_idx] if item_idx < len(ver_list) else (ver_list[0] if ver_list else None)
    mc = rec_list[item_idx] if item_idx < len(rec_list) else (rec_list[0] if rec_list else None)

    return {
        # Identificación
        "codigo_lem": ic.codigo_lem or "",
        "codigo_cliente": (mc.identificacion_muestra if mc else "") or "",
        # Verificación — directo de DB
        "diametro_1": mv.diametro_1_mm if mv else None,
        "diametro_2": mv.diametro_2_mm if mv else None,
        "longitud_1": mv.longitud_1_mm if mv else None,
        "longitud_2": mv.longitud_2_mm if mv else None,
        "longitud_3": mv.longitud_3_mm if mv else None,
        "masa_muestra_aire": mv.masa_muestra_aire_g if mv else None,
        # Compresión — directo de DB, cada item tiene sus propios valores
        "carga_maxima": ic.carga_maxima,
        "tipo_fractura": ic.tipo_fractura,
        "fecha_ensayo": ic.fecha_ensayo,
    }


class InformeService:
    """Consolida datos de los 3 módulos para generar el Informe."""

    @staticmethod
    def consolidar_datos(db: Session, numero_recepcion: str) -> dict:
        """
        Consolida datos de Recepción + Verificación + Compresión.
        
        Fuente de verdad: items de Compresión (cada fila = un item del informe).
        Cross-ref: Verificación y Recepción por codigo_lem para datos complementarios.
        Duplicados: códigos LEM repetidos se manejan por orden de aparición.
        """
        # ── 1. Buscar recepción ──
        recepcion, canonical = TracingService._buscar_recepcion_flexible(db, numero_recepcion)
        if not recepcion:
            raise ValueError(f"No se encontró recepción para '{numero_recepcion}'")

        # ── 2. Buscar verificación y compresión ──
        verificacion, compresion = _buscar_modulos(db, numero_recepcion, canonical)

        # ── 3. Validar que los 3 módulos estén completos ──
        faltantes = []
        if not verificacion:
            faltantes.append("Verificación de Muestras")
        if not compresion:
            faltantes.append("Ensayo de Compresión")
        elif compresion.estado != "COMPLETADO":
            faltantes.append(f"Ensayo de Compresión (estado: {compresion.estado})")
        if faltantes:
            raise ValueError(
                f"No se puede generar el Informe. "
                f"Faltan o no están completados: {', '.join(faltantes)}. "
                f"Los 3 formatos deben estar completados."
            )

        # ── 4. Datos de cabecera (desde recepción) ──
        muestras_rec = recepcion.muestras or []
        m0 = muestras_rec[0] if muestras_rec else None

        header = {
            "cliente": recepcion.cliente or "",
            "direccion": recepcion.domicilio_legal or "",
            "proyecto": recepcion.proyecto or "",
            "ubicacion": recepcion.ubicacion or "",
            "recepcion_numero": recepcion.numero_recepcion or "",
            "ot_numero": recepcion.numero_ot or "",
            "estructura": m0.estructura if m0 else "",
            "fc_kg_cm2": m0.fc_kg_cm2 if m0 else None,
            "fecha_recepcion": recepcion.fecha_recepcion,
            "fecha_moldeo": m0.fecha_moldeo if m0 else "",
            "fecha_rotura": _extraer_fecha_rotura(compresion, m0),
            "densidad": m0.requiere_densidad if m0 else False,
        }

        # ── 5. Indexar verificación y recepción por codigo_lem (listas para duplicados) ──
        ver_index = _index_by_lem_and_item(
            verificacion.muestras_verificadas if verificacion else [],
            lem_attr="codigo_lem"
        )
        rec_index = _index_by_lem_and_item(
            muestras_rec,
            lem_attr="codigo_muestra_lem"
        )

        # ── 6. Construir items desde COMPRESIÓN (fuente de verdad) ──
        # Contador por LEM para manejar duplicados (ej: 15314-CO-26 aparece 2 veces)
        lem_counter: Dict[str, int] = {}
        items = []

        sorted_comp = sorted(compresion.items, key=lambda x: x.item or 0)
        for ic in sorted_comp:
            lem = _norm_lem(ic.codigo_lem)
            idx = lem_counter.get(lem, 0)
            lem_counter[lem] = idx + 1

            items.append(_build_item(
                ic,
                ver_list=ver_index.get(lem, []),
                rec_list=rec_index.get(lem, []),
                item_idx=idx,
            ))

        header["items"] = items
        header["_meta"] = {
            "recepcion_id": recepcion.id,
            "verificacion_id": verificacion.id if verificacion else None,
            "compresion_id": compresion.id if compresion else None,
            "total_muestras": len(items),
            "muestras_con_verificacion": sum(1 for i in items if i["diametro_1"] is not None),
            "muestras_con_compresion": sum(1 for i in items if i["carga_maxima"] is not None),
        }
        return header

    @staticmethod
    def preview_datos(db: Session, numero_recepcion: str) -> dict:
        """Vista previa de los datos consolidados sin generar Excel."""
        try:
            return {"success": True, "data": InformeService.consolidar_datos(db, numero_recepcion)}
        except ValueError as e:
            return {"success": False, "error": str(e)}
