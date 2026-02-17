"""
Servicio para consolidar datos de Recepción + Verificación + Compresión
y generar el Informe (Resumen de Ensayo).

Fuente de verdad: COMPRESIÓN (cada ItemCompresion es una fila del informe).
Si compresión no existe, usa RECEPCIÓN como fuente de filas.
Cross-reference: Verificación y Recepción por codigo_lem + item_numero.

Permite generar informe con datos parciales (módulos pendientes)
para control y verificación por versiones.
"""

import re
import logging
from typing import Optional
from sqlalchemy.orm import Session

from app.modules.recepcion.models import RecepcionMuestra, MuestraConcreto
from app.modules.verificacion.models import VerificacionMuestras, MuestraVerificada
from app.modules.compresion.models import EnsayoCompresion, ItemCompresion
from .service import TracingService
from .models import Trazabilidad, InformeVersion

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


def _extraer_hora_rotura(compresion: EnsayoCompresion) -> str:
    """Obtiene la hora de rotura real desde compresión (hora_ensayo del primer item válido)."""
    if compresion and compresion.items:
        for ic in sorted(compresion.items, key=lambda x: x.item or 0):
            if ic.hora_ensayo:
                return ic.hora_ensayo
    return ""


def _build_item(ic: Optional[ItemCompresion], mv: Optional[MuestraVerificada], mc: Optional[MuestraConcreto]) -> dict:
    """
    Construye un item consolidado para el informe.
    Acepta datos parciales — campos faltantes quedan como None/"".
    
    Match por item_numero (posición), NO por codigo_lem.
    Compresión.item = Verificación.item_numero = Recepción.item_numero
    """
    # Identificación inteligente (Prioridad: Compresión > Recepción > Verificación)
    lem = (ic.codigo_lem if ic else (mc.codigo_muestra_lem if mc else (mv.codigo_lem if mv else ""))) or ""
    # Código Cliente (Prioridad: Recepción > Verificación > Compresión [si tuviera])
    # Verificación tiene campo legacy 'codigo_cliente'
    cod_cliente = (mc.identificacion_muestra if mc else (mv.codigo_cliente if mv else "")) or ""

    return {
        # Identificación
        "codigo_lem": lem,
        "codigo_cliente": cod_cliente,
        "estructura": (mc.estructura if mc else (mv.tipo_testigo if mv else "")) or "",
        "fc_kg_cm2": (mc.fc_kg_cm2 if mc else None),
        # Verificación — directo de DB, datos únicos de ESTE item
        "diametro_1": mv.diametro_1_mm if mv else None,
        "diametro_2": mv.diametro_2_mm if mv else None,
        "longitud_1": mv.longitud_1_mm if mv else None,
        "longitud_2": mv.longitud_2_mm if mv else None,
        "longitud_3": mv.longitud_3_mm if mv else None,
        "masa_muestra_aire": mv.masa_muestra_aire_g if mv else None,
        # Compresión — directo de DB, datos únicos de ESTE item
        "carga_maxima": ic.carga_maxima if ic else None,
        "tipo_fractura": ic.tipo_fractura if ic else None,
        "fecha_ensayo": ic.fecha_ensayo if ic else None,
    }


class InformeService:
    """Consolida datos de los 3 módulos para generar el Informe."""

    @staticmethod
    def consolidar_datos(db: Session, numero_recepcion: str) -> dict:
        """
        Consolida datos de Recepción + Verificación + Compresión.
        
        Permite datos parciales: si un módulo no está completo, los campos
        correspondientes quedan vacíos. Esto permite descargar el informe
        en cualquier momento para control y verificación.
        
        Fuente de filas:
        - Si existe compresión → sus items son la fuente de verdad
        - Si no → se usan las muestras de recepción como base
        """
        # ── 1. Buscar recepción (base principal) ──
        recepcion, canonical = TracingService._buscar_recepcion_flexible(db, numero_recepcion)

        # ── 2. Buscar verificación y compresión ──
        verificacion, compresion = _buscar_modulos(db, numero_recepcion, canonical)
        
        # ── 2b. Validar existencia mínima ──
        # Si no existe NADA en ningún módulo, no podemos generar informe
        if not recepcion and not verificacion and not compresion:
             raise ValueError(f"No se encontró información para '{numero_recepcion}' en ningún módulo")

        # ── 3. Registrar qué módulos están disponibles (para metadata) ──
        modulos_estado = {
            "recepcion": "completado" if recepcion else "pendiente",
            "verificacion": "completado" if verificacion else "pendiente",
            "compresion": "completado" if (compresion and compresion.estado == "COMPLETADO") else
                          "en_proceso" if compresion else "pendiente",
        }
        
        modulos_faltantes = []
        if not recepcion:
             modulos_faltantes.append("Recepción (Datos base)")
        if not verificacion:
            modulos_faltantes.append("Verificación de Muestras")
        if not compresion:
            modulos_faltantes.append("Ensayo de Compresión")
        elif compresion.estado != "COMPLETADO":
            modulos_faltantes.append(f"Ensayo de Compresión (estado: {compresion.estado})")

        # ── 4. Datos de cabecera (Prioridad: Recepción > Verificación > Compresión) ──
        muestras_rec = recepcion.muestras if recepcion else []
        m0 = muestras_rec[0] if muestras_rec else None

        # Helper para extraer dato de cualquier fuente disponible
        def get_header_val(attr, fallback=""):
             if recepcion and getattr(recepcion, attr, None): return getattr(recepcion, attr)
             if verificacion and getattr(verificacion, attr, None): return getattr(verificacion, attr)
             if compresion and getattr(compresion, attr, None): return getattr(compresion, attr)
             return fallback

        direccion = (get_header_val("domicilio_legal") or (recepcion.domicilio_solicitante if recepcion else ""))
        
        header = {
            "cliente": get_header_val("cliente"),
            "direccion": direccion,
            "proyecto": get_header_val("proyecto"),
            "ubicacion": get_header_val("ubicacion"),
            "recepcion_numero": (recepcion.numero_recepcion if recepcion else (verificacion.numero_verificacion if verificacion else (compresion.numero_recepcion if compresion else numero_recepcion))),
            "ot_numero": get_header_val("numero_ot"),
            "estructura": m0.estructura if m0 else "",
            "fc_kg_cm2": m0.fc_kg_cm2 if m0 else None,
            "fecha_recepcion": recepcion.fecha_recepcion if recepcion else None,
            "fecha_moldeo": m0.fecha_moldeo if m0 else "",
            "hora_moldeo": m0.hora_moldeo if m0 else "",
            "fecha_rotura": _extraer_fecha_rotura(compresion, m0) if compresion else (m0.fecha_rotura if m0 else ""),
            "hora_rotura": _extraer_hora_rotura(compresion),
            "densidad": m0.requiere_densidad if m0 else False,
        }

        # ── 5. Indexar verificación y recepción por item_numero (1:1 match) ──
        ver_by_item = _index_by_item_numero(
            verificacion.muestras_verificadas if verificacion else [],
            item_attr="item_numero"
        )
        rec_by_item = _index_by_item_numero(
            muestras_rec,
            item_attr="item_numero"
        )

        # ── 6. Construir items ──
        items = []
        
        if compresion and compresion.items:
            # Fuente de verdad: COMPRESIÓN
            sorted_comp = sorted(compresion.items, key=lambda x: x.item or 0)
            for ic in sorted_comp:
                item_num = ic.item
                items.append(_build_item(
                    ic,
                    mv=ver_by_item.get(item_num),
                    mc=rec_by_item.get(item_num),
                ))
        elif muestras_rec:
            # Sin compresión: usar muestras de recepción como base
            sorted_rec = sorted(muestras_rec, key=lambda x: x.item_numero or 0)
            for mc in sorted_rec:
                item_num = mc.item_numero
                items.append(_build_item(
                    ic=None,
                    mv=ver_by_item.get(item_num),
                    mc=mc,
                ))
        elif verificacion and verificacion.muestras_verificadas:
             # Fallback: Solo existe verificación
             sorted_ver = sorted(verificacion.muestras_verificadas, key=lambda x: x.item_numero or 0)
             for mv in sorted_ver:
                 item_num = mv.item_numero
                 items.append(_build_item(
                     ic=None,
                     mv=mv,
                     mc=None,
                 ))

        # ── 7. Metadata y estado de completitud ──
        datos_completos = not modulos_faltantes
        
        header["items"] = items
        header["_meta"] = {
            "recepcion_id": recepcion.id if recepcion else None,
            "verificacion_id": verificacion.id if verificacion else None,
            "compresion_id": compresion.id if compresion else None,
            "total_muestras": len(items),
            "muestras_con_verificacion": sum(1 for i in items if i["diametro_1"] is not None),
            "muestras_con_compresion": sum(1 for i in items if i["carga_maxima"] is not None),
            "datos_completos": datos_completos,
            "modulos_faltantes": modulos_faltantes,
            "modulos_estado": modulos_estado,
        }
        return header

    @staticmethod
    def registrar_version(db: Session, numero_recepcion: str, data: dict, notas: str = None, generado_por: str = None) -> InformeVersion:
        """
        Registra una nueva versión del informe generado.
        Cada descarga/generación crea un registro de versión.
        """
        # Buscar trazabilidad
        traza = db.query(Trazabilidad).filter(
            Trazabilidad.numero_recepcion == numero_recepcion
        ).first()
        
        if not traza:
            # Si no existe, sincronizar primero
            traza = TracingService.actualizar_trazabilidad(db, numero_recepcion)
        
        if not traza:
            raise ValueError(f"No se encontró trazabilidad para '{numero_recepcion}'")

        # Obtener la última versión
        ultima_version = db.query(InformeVersion).filter(
            InformeVersion.trazabilidad_id == traza.id
        ).order_by(InformeVersion.version.desc()).first()
        
        nueva_version = (ultima_version.version + 1) if ultima_version else 1
        
        meta = data.get("_meta", {})
        
        version = InformeVersion(
            trazabilidad_id=traza.id,
            numero_recepcion=numero_recepcion,
            version=nueva_version,
            estado_recepcion=meta.get("modulos_estado", {}).get("recepcion", "pendiente"),
            estado_verificacion=meta.get("modulos_estado", {}).get("verificacion", "pendiente"),
            estado_compresion=meta.get("modulos_estado", {}).get("compresion", "pendiente"),
            total_muestras=meta.get("total_muestras", 0),
            muestras_con_verificacion=meta.get("muestras_con_verificacion", 0),
            muestras_con_compresion=meta.get("muestras_con_compresion", 0),
            notas=notas,
            generado_por=generado_por,
            data_snapshot=meta,
        )
        
        db.add(version)
        db.commit()
        db.refresh(version)
        
        logger.info(f"Informe v{nueva_version} registrado para {numero_recepcion}")
        return version

    @staticmethod
    def obtener_versiones(db: Session, numero_recepcion: str) -> list:
        """Obtiene el historial de versiones de un informe."""
        return db.query(InformeVersion).filter(
            InformeVersion.numero_recepcion == numero_recepcion
        ).order_by(InformeVersion.version.desc()).all()

    @staticmethod
    def preview_datos(db: Session, numero_recepcion: str) -> dict:
        """Vista previa de los datos consolidados sin generar Excel."""
        try:
            return {"success": True, "data": InformeService.consolidar_datos(db, numero_recepcion)}
        except ValueError as e:
            return {"success": False, "error": str(e)}
