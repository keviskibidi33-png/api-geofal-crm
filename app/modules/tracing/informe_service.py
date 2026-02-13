"""
Servicio para consolidar datos de Recepción + Verificación + Compresión
y generar el Resumen de Ensayo (Informe Final).
"""

import logging
from typing import Optional
from sqlalchemy.orm import Session

from app.modules.recepcion.models import RecepcionMuestra, MuestraConcreto
from app.modules.verificacion.models import VerificacionMuestras, MuestraVerificada
from app.modules.compresion.models import EnsayoCompresion, ItemCompresion
from .service import TracingService

logger = logging.getLogger(__name__)


class InformeService:
    """Consolida datos de los 3 módulos para generar el Resumen de Ensayo."""

    @staticmethod
    def consolidar_datos(db: Session, numero_recepcion: str) -> dict:
        """
        Busca datos en los 3 módulos y los consolida en un dict
        listo para el generador Excel.
        
        Correlación de muestras:
            - MuestraConcreto.codigo_muestra_lem (recepción)
            - MuestraVerificada.codigo_lem (verificación)
            - ItemCompresion.codigo_lem (compresión)
        
        Returns:
            dict con toda la data consolidada o raises ValueError si faltan módulos.
        """
        # 1. Buscar recepción con búsqueda flexible
        recepcion, canonical = TracingService._buscar_recepcion_flexible(db, numero_recepcion)
        if not recepcion:
            raise ValueError(f"No se encontró recepción para '{numero_recepcion}'")

        # 2. Buscar verificación y compresión
        base_num = TracingService._extraer_numero_base(numero_recepcion)
        import re
        
        verificacion = None
        compresion = None
        
        # Build search variants
        source_str = canonical or numero_recepcion or ""
        year_match = re.search(r'-(\d{2})$', source_str)
        year_suffix = year_match.group(1) if year_match else ""
        
        search_nums = list(dict.fromkeys([
            canonical, base_num, numero_recepcion,
            f"{base_num}-REC",
            f"{base_num}-REC-{year_suffix}" if year_suffix else None,
        ]))
        search_nums = [n for n in search_nums if n]  # Remove None
        
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

        # 2b. VALIDACIÓN ESTRICTA: Los 3 módulos deben existir Y estar completados
        modulos_faltantes = []
        if not verificacion:
            modulos_faltantes.append("Verificación de Muestras")
        if not compresion:
            modulos_faltantes.append("Ensayo de Compresión")
        elif compresion.estado != "COMPLETADO":
            modulos_faltantes.append(f"Ensayo de Compresión (estado actual: {compresion.estado})")
        
        if modulos_faltantes:
            raise ValueError(
                f"No se puede generar el Resumen de Ensayo. "
                f"Faltan o no están completados: {', '.join(modulos_faltantes)}. "
                f"Los 3 formatos (Recepción, Verificación y Compresión) deben estar completados."
            )

        # 3. Extract header data from recepción
        muestras_concreto = recepcion.muestras or []
        primera_muestra = muestras_concreto[0] if muestras_concreto else None

        header = {
            "cliente": recepcion.cliente or "",
            "direccion": recepcion.domicilio_legal or "",
            "proyecto": recepcion.proyecto or "",
            "ubicacion": recepcion.ubicacion or "",
            "recepcion_numero": recepcion.numero_recepcion or "",
            "ot_numero": recepcion.numero_ot or "",
            "estructura": primera_muestra.estructura if primera_muestra else "",
            "fc_kg_cm2": primera_muestra.fc_kg_cm2 if primera_muestra else None,
            "fecha_recepcion": recepcion.fecha_recepcion,
            "fecha_moldeo": primera_muestra.fecha_moldeo if primera_muestra else "",
            "fecha_rotura": primera_muestra.fecha_rotura if primera_muestra else "",
            "densidad": primera_muestra.requiere_densidad if primera_muestra else False,
        }

        # 4. Build cross-referenced items by codigo_lem
        # Index verificación muestras by codigo_lem
        ver_by_lem = {}
        if verificacion and verificacion.muestras_verificadas:
            for mv in verificacion.muestras_verificadas:
                if mv.codigo_lem:
                    ver_by_lem[mv.codigo_lem.strip().upper()] = mv

        # Index compresión items by codigo_lem
        comp_by_lem = {}
        if compresion and compresion.items:
            for ic in compresion.items:
                if ic.codigo_lem:
                    comp_by_lem[ic.codigo_lem.strip().upper()] = ic

        # 5. Build consolidated items list (one per muestra de recepción)
        items = []
        for mc in muestras_concreto:
            lem_code = (mc.codigo_muestra_lem or mc.codigo_muestra or "").strip().upper()
            
            # Find matching verification data
            mv = ver_by_lem.get(lem_code)
            # Find matching compression data
            ic = comp_by_lem.get(lem_code)

            item = {
                # Recepción
                "codigo_lem": mc.codigo_muestra_lem or mc.codigo_muestra or "",
                "codigo_cliente": mc.identificacion_muestra or mc.codigo_muestra or "",
                # Verificación (diámetros, longitudes, masa)
                "diametro_1": mv.diametro_1_mm if mv else None,
                "diametro_2": mv.diametro_2_mm if mv else None,
                "longitud_1": mv.longitud_1_mm if mv else None,
                "longitud_2": mv.longitud_2_mm if mv else None,
                "longitud_3": mv.longitud_3_mm if mv else None,
                "masa_muestra_aire": mv.masa_muestra_aire_g if mv else None,
                # Compresión (carga, fractura)
                "carga_maxima": ic.carga_maxima if ic else None,
                "tipo_fractura": ic.tipo_fractura if ic else None,
            }
            items.append(item)

        header["items"] = items

        # Add metadata for the response
        header["_meta"] = {
            "recepcion_id": recepcion.id,
            "verificacion_id": verificacion.id if verificacion else None,
            "compresion_id": compresion.id if compresion else None,
            "total_muestras": len(muestras_concreto),
            "muestras_con_verificacion": sum(1 for i in items if i["diametro_1"] is not None),
            "muestras_con_compresion": sum(1 for i in items if i["carga_maxima"] is not None),
            "modulos_completos": {
                "recepcion": True,
                "verificacion": verificacion is not None,
                "compresion": compresion is not None,
            }
        }

        return header

    @staticmethod
    def preview_datos(db: Session, numero_recepcion: str) -> dict:
        """
        Vista previa de los datos consolidados sin generar Excel.
        Útil para que el frontend muestre qué datos se incluirán.
        """
        try:
            data = InformeService.consolidar_datos(db, numero_recepcion)
            return {
                "success": True,
                "data": data,
            }
        except ValueError as e:
            return {
                "success": False,
                "error": str(e),
            }
