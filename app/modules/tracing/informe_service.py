"""
Servicio para consolidar datos de Recepción + Verificación + Compresión
y generar el Informe (Resumen de Ensayo).

Fuente de verdad: COMPRESIÓN (cada ItemCompresion es una fila del informe).
Cross-reference: Verificación y Recepción por codigo_lem + item_numero.
"""

import re
import logging
from typing import Optional
from sqlalchemy.orm import Session

from app.modules.recepcion.models import RecepcionMuestra, MuestraConcreto
from app.modules.verificacion.models import VerificacionMuestras, MuestraVerificada
from app.modules.compresion.models import EnsayoCompresion, ItemCompresion
from .service import TracingService

logger = logging.getLogger(__name__)


def _norm_lem(code: str) -> str:
    """Normaliza un código LEM para comparación segura."""
    return (code or "").strip().upper()


def _index_by_item_numero(records, item_attr: str = "item_numero") -> dict:
    """
    Indexa registros por su número de item (1, 2, 3...).
    Cada item es único — no hay duplicados por número de item.
    Retorna {item_numero: record}.
    """
    return {getattr(r, item_attr): r for r in records if getattr(r, item_attr, None) is not None}


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


def _build_item(ic: ItemCompresion, mv: Optional[MuestraVerificada], mc: Optional[MuestraConcreto]) -> dict:
    """
    Construye un item consolidado para el informe.
    Cada campo viene directo de su tabla DB — sin reutilizar datos de otro item.
    
    Match por item_numero (posición), NO por codigo_lem.
    Compresión.item = Verificación.item_numero = Recepción.item_numero
    """
    return {
        # Identificación
        "codigo_lem": ic.codigo_lem or "",
        "codigo_cliente": (mc.identificacion_muestra if mc else "") or "",
        # Verificación — directo de DB, datos únicos de ESTE item
        "diametro_1": mv.diametro_1_mm if mv else None,
        "diametro_2": mv.diametro_2_mm if mv else None,
        "longitud_1": mv.longitud_1_mm if mv else None,
        "longitud_2": mv.longitud_2_mm if mv else None,
        "longitud_3": mv.longitud_3_mm if mv else None,
        "masa_muestra_aire": mv.masa_muestra_aire_g if mv else None,
        # Compresión — directo de DB, datos únicos de ESTE item
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

        # ── 5. Indexar verificación y recepción por item_numero (1:1 match) ──
        # Cada item tiene datos ÚNICOS — no se reutilizan entre items
        ver_by_item = _index_by_item_numero(
            verificacion.muestras_verificadas if verificacion else [],
            item_attr="item_numero"
        )
        rec_by_item = _index_by_item_numero(
            muestras_rec,
            item_attr="item_numero"
        )

        # ── 6. Construir items desde COMPRESIÓN (fuente de verdad) ──
        # Match 1:1 por item_numero: Compresión.item == Verificación.item_numero == Recepción.item_numero
        items = []
        sorted_comp = sorted(compresion.items, key=lambda x: x.item or 0)
        for ic in sorted_comp:
            item_num = ic.item  # Número de item en compresión
            items.append(_build_item(
                ic,
                mv=ver_by_item.get(item_num),  # Verificación del MISMO item
                mc=rec_by_item.get(item_num),   # Recepción del MISMO item
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
