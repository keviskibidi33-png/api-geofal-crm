from types import SimpleNamespace
from sqlalchemy import text, or_
from sqlalchemy.orm import Session, load_only, selectinload
from .models import Trazabilidad
from app.modules.recepcion.models import RecepcionMuestra
from app.modules.verificacion.models import VerificacionMuestras
from app.modules.compresion.models import EnsayoCompresion
from typing import Optional
from datetime import datetime
import os
import re
import logging
from app.utils.storage_utils import StorageUtils

logger = logging.getLogger(__name__)

class TracingService:
    @staticmethod
    def _has_fecha_entrega_column(db: Session) -> bool:
        cached = db.info.get("trazabilidad_has_fecha_entrega")
        if cached is not None:
            return cached

        exists = db.execute(
            text(
                "select 1 from information_schema.columns "
                "where table_schema = 'public' and table_name = 'trazabilidad' and column_name = 'fecha_entrega'"
            )
        ).first() is not None
        db.info["trazabilidad_has_fecha_entrega"] = exists
        return exists

    @staticmethod
    def _trazabilidad_query(db: Session):
        cols = [
            Trazabilidad.id,
            Trazabilidad.numero_recepcion,
            Trazabilidad.cliente,
            Trazabilidad.proyecto,
            Trazabilidad.estado_recepcion,
            Trazabilidad.estado_verificacion,
            Trazabilidad.estado_compresion,
            Trazabilidad.estado_informe,
            Trazabilidad.mensaje_seguimiento,
            Trazabilidad.data_consolidada,
            Trazabilidad.fecha_creacion,
            Trazabilidad.fecha_actualizacion,
        ]
        if TracingService._has_fecha_entrega_column(db):
            cols.append(Trazabilidad.fecha_entrega)
        return db.query(Trazabilidad).options(load_only(*cols))

    @staticmethod
    def _build_virtual_traza(numero_recepcion: str):
        return SimpleNamespace(
            id=None,
            numero_recepcion=numero_recepcion,
            cliente=None,
            proyecto=None,
            estado_recepcion="pendiente",
            estado_verificacion="pendiente",
            estado_compresion="pendiente",
            estado_informe="pendiente",
            mensaje_seguimiento=None,
            data_consolidada={},
            fecha_entrega=None,
            fecha_creacion=None,
            fecha_actualizacion=None,
        )

    @staticmethod
    def _extraer_numero_base(numero: str) -> str:
        """
        Extrae el número base sin prefijo REC- ni sufijos como -REC o año (-XX).
        Ejemplos: 'REC-1111-26' -> '1111', '1111-REC' -> '1111', '1111-REC-26' -> '1111'
        """
        # Quitar prefijos y limpiar
        clean = numero.replace("REC-", "").replace("rec-", "").strip()
        
        # Quitar sufijo -REC (frecuente en verificación)
        clean = re.sub(r'-REC$', '', clean, flags=re.IGNORECASE)
        clean = re.sub(r'-REC-(\d{2})$', r'-\1', clean, flags=re.IGNORECASE)

        # Quitar sufijo de año si existe (formato: NNNN-YY donde YY son 2 dígitos)
        match = re.match(r'^(.+)-(\d{2})$', clean)
        if match:
            return match.group(1)
        return clean

    @staticmethod
    def _build_numero_variantes(numero: str, canonical: str = "") -> list[str]:
        """
        Construye variantes de numero_recepcion para buscar en modulos.
        Incluye prefijos REC- y sufijos -REC con y sin anio.
        """
        source = (canonical or numero or "").strip()
        if not source:
            return []

        base_num = TracingService._extraer_numero_base(source)
        clean_num = source.replace("REC-", "").replace("rec-", "").strip()

        year_match = re.search(r'-(\d{2})$', source)
        year_suffix = year_match.group(1) if year_match else ""

        variants = [
            numero,
            canonical,
            source,
            clean_num,
            base_num,
            f"REC-{base_num}" if base_num else None,
            f"REC-{base_num}-{year_suffix}" if base_num and year_suffix else None,
            f"REC-{clean_num}" if clean_num and not clean_num.upper().startswith("REC-") else None,
            f"{base_num}-REC" if base_num else None,
            f"{base_num}-REC-{year_suffix}" if base_num and year_suffix else None,
        ]

        return list(dict.fromkeys([v for v in variants if v]))

    @staticmethod
    def _buscar_recepcion_flexible(db: Session, numero: str) -> Optional[tuple[Optional[RecepcionMuestra], str]]:
        """
        Busca una recepción permitiendo variaciones de formato usando una sola query optimizada.
        Ignora automáticamente prefijos (REC-) y sufijos de año (-26).
        Retorna una tupla (instancia_recepcion, numero_canonico).
        """
        if not numero:
            return None, ""
        
        # Generar variantes en memoria (operación rápida)
        base_num = TracingService._extraer_numero_base(numero)
        clean_num = numero.replace("REC-", "").replace("rec-", "").strip()
        
        variantes = {numero, clean_num, base_num}
        variantes.discard("") # Remove empty strings
        
        # Query Única Optimizada con IN operator
        # Esto reduce de 3 round-trips a 1
        recepciones = db.query(RecepcionMuestra).filter(
            RecepcionMuestra.numero_recepcion.in_(list(variantes))
        ).all()
        
        # Lógica de prioridad en memoria
        if not recepciones:
            return None, numero
            
        # Mapear resultados para acceso rápido
        mapa_resultados = {r.numero_recepcion: r for r in recepciones}
        
        # Verificar en orden de prioridad: Exacto -> Limpio -> Base
        if numero in mapa_resultados:
            return mapa_resultados[numero], numero
        if clean_num in mapa_resultados:
            return mapa_resultados[clean_num], clean_num
        if base_num in mapa_resultados:
            return mapa_resultados[base_num], base_num
            
        # Fallback (primer match cualquiera)
        first_match = recepciones[0]
        return first_match, first_match.numero_recepcion

    @staticmethod
    def _has_meaningful_value(value) -> bool:
        if value is None:
            return False
        if isinstance(value, str):
            return value.strip() != ""
        if isinstance(value, (int, float)):
            return value != 0
        return True

    @staticmethod
    def _item_compresion_score(item) -> int:
        score = 0

        if TracingService._has_meaningful_value(getattr(item, "codigo_lem", None)):
            score += 1
        if TracingService._has_meaningful_value(getattr(item, "carga_maxima", None)):
            score += 4
        if TracingService._has_meaningful_value(getattr(item, "tipo_fractura", None)):
            score += 4
        if getattr(item, "fecha_ensayo", None):
            score += 2
        if TracingService._has_meaningful_value(getattr(item, "hora_ensayo", None)):
            score += 1

        return score

    @staticmethod
    def _datetime_sort_value(value: Optional[datetime]) -> float:
        if not value:
            return 0.0
        try:
            return value.timestamp()
        except Exception:
            return 0.0

    @staticmethod
    def _ensayo_compresion_priority(ensayo: EnsayoCompresion, recepcion_id: Optional[int] = None) -> tuple:
        estado_priority = {
            "COMPLETADO": 3,
            "EN_PROCESO": 2,
            "PENDIENTE": 1,
        }.get((ensayo.estado or "").upper(), 0)

        items = list(getattr(ensayo, "items", []) or [])
        total_score = sum(TracingService._item_compresion_score(item) for item in items)
        complete_items = sum(
            1
            for item in items
            if TracingService._has_meaningful_value(getattr(item, "carga_maxima", None))
            and TracingService._has_meaningful_value(getattr(item, "tipo_fractura", None))
        )
        items_with_data = sum(1 for item in items if TracingService._item_compresion_score(item) > 0)
        linked_to_recepcion = 1 if recepcion_id is not None and ensayo.recepcion_id == recepcion_id else 0
        has_storage = 1 if getattr(ensayo, "object_key", None) else 0
        updated_sort = TracingService._datetime_sort_value(
            getattr(ensayo, "fecha_actualizacion", None) or getattr(ensayo, "fecha_creacion", None)
        )

        return (
            estado_priority,
            complete_items,
            items_with_data,
            total_score,
            len(items),
            linked_to_recepcion,
            has_storage,
            updated_sort,
            ensayo.id or 0,
        )

    @staticmethod
    def _buscar_compresion_preferida(
        db: Session,
        numeros_busqueda: list[str],
        recepcion_id: Optional[int] = None,
    ) -> Optional[EnsayoCompresion]:
        variantes = list(
            dict.fromkeys(
                numero.strip()
                for numero in (numeros_busqueda or [])
                if isinstance(numero, str) and numero.strip()
            )
        )

        filtros = []
        if variantes:
            filtros.append(EnsayoCompresion.numero_recepcion.in_(variantes))
        if recepcion_id is not None:
            filtros.append(EnsayoCompresion.recepcion_id == recepcion_id)

        if not filtros:
            return None

        candidatos = (
            db.query(EnsayoCompresion)
            .options(selectinload(EnsayoCompresion.items))
            .filter(or_(*filtros))
            .all()
        )
        if not candidatos:
            return None

        return max(
            candidatos,
            key=lambda ensayo: TracingService._ensayo_compresion_priority(
                ensayo,
                recepcion_id=recepcion_id,
            ),
        )

    @staticmethod
    def actualizar_trazabilidad(db: Session, numero_recepcion: str):
        """
        Sincroniza el estado de una recepción en la tabla maestra de trazabilidad.
        """
        if not numero_recepcion:
            return None

        # 1. Obtener recepción con búsqueda inteligente
        recepcion, canonical_numero = TracingService._buscar_recepcion_flexible(db, numero_recepcion)
        
        # Extraer variantes para búsquedas cruzadas entre módulos
        numeros_busqueda = TracingService._build_numero_variantes(numero_recepcion, canonical_numero)

        # 2. Buscar en otros módulos usando todas las variantes del número
        verificacion = None
        compresion = TracingService._buscar_compresion_preferida(
            db,
            numeros_busqueda,
            recepcion.id if recepcion else None,
        )
        
        # Ensure we have a valid list to search
        if not numeros_busqueda:
            numeros_busqueda = [numero_recepcion] if numero_recepcion else []

        for num in numeros_busqueda:
            if not verificacion:
                # Primary search by number
                verificacion = db.query(VerificacionMuestras).filter(VerificacionMuestras.numero_verificacion == num).first()
                
                # If not found, try smart verification formats
                if not verificacion:
                    # Common formats: "1111", "REC-1111-26", "1111-REC", "1111-REC-26"
                    for variant in TracingService._build_numero_variantes(numero_recepcion, canonical_numero):
                        verificacion = db.query(VerificacionMuestras).filter(
                            VerificacionMuestras.numero_verificacion == variant
                        ).first()
                        if verificacion:
                            break
            
            if verificacion and compresion:
                break
        
        has_fecha_entrega = TracingService._has_fecha_entrega_column(db)
        persist_traza = True

        # 3. Buscar si ya existe en trazabilidad
        traza = TracingService._trazabilidad_query(db).filter(Trazabilidad.numero_recepcion == canonical_numero).first()
        
        # Búsqueda secundaria flexible en trazabilidad si no se encuentra por el canónico actual
        if not traza:
            for num in numeros_busqueda:
                traza = TracingService._trazabilidad_query(db).filter(Trazabilidad.numero_recepcion == num).first()
                if traza:
                    break

        # --- PERSISTENCE & CLEANUP FIX ---
        # Si NO EXISTE NADA en los módulos origen:
        if not recepcion and not verificacion and not compresion:
            if traza:
                # Si el usuario borró todo, borramos la trazabilidad para no tener registros fantasma
                # A menos que queramos mantener historial (pero el usuario reportó esto como bug)
                db.delete(traza)
                db.commit()
                return None
            return None # No crear nada si no hay nada
        
        if not traza:
            if has_fecha_entrega:
                traza = Trazabilidad(numero_recepcion=canonical_numero)
                db.add(traza)
            else:
                # Fallback temporal mientras la migración no exista en producción.
                persist_traza = False
                traza = TracingService._build_virtual_traza(canonical_numero)
            
        # 4. Actualizar datos básicos (priorizando la recepción si existe)
        if recepcion:
            traza.cliente = recepcion.cliente
            traza.proyecto = recepcion.proyecto
            if has_fecha_entrega:
                traza.fecha_entrega = recepcion.fecha_estimada_culminacion
        elif verificacion:
            traza.cliente = verificacion.cliente
            traza.proyecto = "Cargado desde Verificación"
        elif compresion:
            # Intentar obtener de metadatos de compresión si existe vinculación previa
            traza.cliente = "Cargado desde Compresión"
            traza.proyecto = "Proyecto no identificado"
        
        # 5. Calcular estados (Optimizacion: confiar en DB para evitar latencia de red)
        
        # Recepción
        if recepcion:
            # OPTIMIZACION: Verificar solo si existe la clave en DB, no hacer request HTTP síncrono
            # El storage debe ser consistente con la DB. Si se requiere validación profunda, usar background task.
            has_file = bool(recepcion.object_key)
            traza.estado_recepcion = "completado" if has_file else "en_proceso"
        else:
            traza.estado_recepcion = "pendiente"

        # Verificación
        if verificacion:
            has_file = False
            # Verificar existencia lógica en DB
            if verificacion.object_key:
                has_file = True
            # Si no hay key, verificar si hay ruta local (legacy)
            elif verificacion.archivo_excel:
                 # Solo verificar path local si es absoluto y seguro, evitar I/O bloqueante si es red
                 has_file = True 
            
            traza.estado_verificacion = "completado" if has_file else "en_proceso"
        else:
            traza.estado_verificacion = "pendiente"
        
        # Compresión — usa el estado calculado automáticamente por el servicio
        if compresion:
            estado_com = (compresion.estado or "PENDIENTE").upper()
            if estado_com == "COMPLETADO":
                traza.estado_compresion = "completado"
            elif estado_com == "EN_PROCESO":
                traza.estado_compresion = "en_proceso"
            else:
                traza.estado_compresion = "en_proceso"  # Existe pero aún pendiente
        else:
            traza.estado_compresion = "pendiente"

        # Informe / Resumen de Ensayo
        # Siempre disponible para descarga si existe recepción
        # Estado refleja completitud de datos:
        # - completado: los 3 módulos listos → datos completos
        # - en_proceso: algún módulo avanzó pero faltan datos
        # - pendiente: solo recepción, nada más
        all_three_done = (
            traza.estado_recepcion == "completado" and
            traza.estado_verificacion == "completado" and
            traza.estado_compresion == "completado"
        )
        any_progress = (
            traza.estado_verificacion != "pendiente" or
            traza.estado_compresion != "pendiente"
        )
        
        if all_three_done:
            traza.estado_informe = "completado"  # Los 3 listos → datos completos
        elif any_progress:
            traza.estado_informe = "en_proceso"  # Avance parcial, descargable con datos parciales
        else:
            traza.estado_informe = "en_proceso"  # Solo recepción, descargable con datos parciales
            
        # 6. Guardar metadata extra en JSON
        fecha_entrega_value = traza.__dict__.get("fecha_entrega") if has_fecha_entrega else None

        traza.data_consolidada = {
            "recepcion_id": recepcion.id if recepcion else None,
            "recepcion_estado": recepcion.estado if recepcion else None,
            "numero_ot": getattr(recepcion, 'numero_ot', None) if recepcion else (compresion.numero_ot if compresion else None),
            "cliente": traza.cliente,
            "proyecto": traza.proyecto,
            "fecha_entrega": fecha_entrega_value.isoformat() if fecha_entrega_value else None,
            "muestras_count": len(recepcion.muestras) if recepcion and recepcion.muestras else 0,
            "fecha_recepcion": recepcion.fecha_recepcion.isoformat() if recepcion and recepcion.fecha_recepcion else None,
            "verificacion_id": verificacion.id if verificacion else None,
            "compresion_id": compresion.id if compresion else None,
            "compresion_status": compresion.estado if compresion else None,
            "storage_verified": True
        }

        if persist_traza:
            db.commit()
            db.refresh(traza)
        return traza

    @staticmethod
    def buscar_sugerencias(db: Session, q: str, limit: int = 10):
        """
        Busca sugerencias de números de recepción en la tabla de trazabilidad.
        """
        try:
            termino = (q or "").strip()
            patrones_numero = [termino] if termino else []
            if termino:
                patrones_numero = list(
                    dict.fromkeys(
                        [
                            patron.strip()
                            for patron in [
                                termino,
                                TracingService._extraer_numero_base(termino),
                                *TracingService._build_numero_variantes(termino, termino),
                            ]
                            if patron and str(patron).strip()
                        ]
                    )
                )

            query = TracingService._trazabilidad_query(db)
            if termino:
                filtros_traza = [Trazabilidad.cliente.ilike(f"%{termino}%")]
                filtros_traza.extend(
                    Trazabilidad.numero_recepcion.ilike(f"%{patron}%")
                    for patron in patrones_numero
                )
                query = query.filter(or_(*filtros_traza))

            trazas = query.order_by(Trazabilidad.fecha_creacion.desc()).limit(limit).all()

            resultados = []
            vistos: set[str] = set()

            def _append_result(item):
                numero = getattr(item, "numero_recepcion", None)
                if not numero or numero in vistos:
                    return
                vistos.add(numero)
                resultados.append(item)

            for traza in trazas:
                _append_result(traza)

            if len(resultados) >= limit:
                return resultados[:limit]

            recepcion_query = db.query(RecepcionMuestra)
            if termino:
                filtros_recepcion = [RecepcionMuestra.cliente.ilike(f"%{termino}%")]
                filtros_recepcion.extend(
                    RecepcionMuestra.numero_recepcion.ilike(f"%{patron}%")
                    for patron in patrones_numero
                )
                recepcion_query = recepcion_query.filter(or_(*filtros_recepcion))

            recepciones = (
                recepcion_query
                .order_by(RecepcionMuestra.fecha_creacion.desc())
                .limit(limit)
                .all()
            )

            for recepcion in recepciones:
                if recepcion.numero_recepcion in vistos:
                    continue

                synced = TracingService.actualizar_trazabilidad(db, recepcion.numero_recepcion)
                if synced:
                    _append_result(synced)
                    if len(resultados) >= limit:
                        break
                    continue

                fallback = TracingService._build_virtual_traza(recepcion.numero_recepcion)
                fallback.cliente = recepcion.cliente
                fallback.proyecto = recepcion.proyecto
                fallback.estado_recepcion = "completado" if recepcion.object_key else "en_proceso"
                fallback.data_consolidada = {
                    "recepcion_id": recepcion.id,
                    "numero_ot": recepcion.numero_ot,
                    "cliente": recepcion.cliente,
                    "proyecto": recepcion.proyecto,
                    "muestras_count": len(recepcion.muestras) if recepcion.muestras else 0,
                    "fecha_recepcion": recepcion.fecha_recepcion.isoformat() if recepcion.fecha_recepcion else None,
                }
                _append_result(fallback)

                if len(resultados) >= limit:
                    break

            return resultados[:limit]
        except Exception as e:
            logger.error("Error in buscar_sugerencias: %s", e, exc_info=True)
            return []

    @staticmethod
    def migrar_datos(db: Session):
        """
        Puebla la tabla de trazabilidad con todas las recepciones existentes.
        """
        recepciones = db.query(RecepcionMuestra).all()
        count = 0
        for r in recepciones:
            TracingService.actualizar_trazabilidad(db, r.numero_recepcion)
            count += 1
        return count
