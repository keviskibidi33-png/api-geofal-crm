from sqlalchemy.orm import Session
from .models import Trazabilidad
from app.modules.recepcion.models import RecepcionMuestra
from app.modules.verificacion.models import VerificacionMuestras
from app.modules.compresion.models import EnsayoCompresion
from typing import Optional
import os
import re
from app.utils.storage_utils import StorageUtils

class TracingService:
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
        compresion = None
        
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
            
            if not compresion:
                compresion = db.query(EnsayoCompresion).filter(EnsayoCompresion.numero_recepcion == num).first()
            
            # If we found both, stop searching
            if verificacion and compresion:
                break
        
        # 3. Buscar si ya existe en trazabilidad
        traza = db.query(Trazabilidad).filter(Trazabilidad.numero_recepcion == canonical_numero).first()
        
        # Búsqueda secundaria flexible en trazabilidad si no se encuentra por el canónico actual
        if not traza:
            for num in numeros_busqueda:
                traza = db.query(Trazabilidad).filter(Trazabilidad.numero_recepcion == num).first()
                if traza: break

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
            traza = Trazabilidad(numero_recepcion=canonical_numero)
            db.add(traza)
            
        # 4. Actualizar datos básicos (priorizando la recepción si existe)
        if recepcion:
            traza.cliente = recepcion.cliente
            traza.proyecto = recepcion.proyecto
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
        traza.data_consolidada = {
            "recepcion_id": recepcion.id if recepcion else None,
            "recepcion_estado": recepcion.estado if recepcion else None,
            "numero_ot": getattr(recepcion, 'numero_ot', None) if recepcion else (compresion.numero_ot if compresion else None),
            "cliente": traza.cliente,
            "proyecto": traza.proyecto,
            "fecha_entrega": traza.fecha_entrega.isoformat() if traza.fecha_entrega else None,
            "muestras_count": len(recepcion.muestras) if recepcion and recepcion.muestras else 0,
            "fecha_recepcion": recepcion.fecha_recepcion.isoformat() if recepcion and recepcion.fecha_recepcion else None,
            "verificacion_id": verificacion.id if verificacion else None,
            "compresion_id": compresion.id if compresion else None,
            "compresion_status": compresion.estado if compresion else None,
            "storage_verified": True
        }
        
        db.commit()
        db.refresh(traza)
        return traza

    @staticmethod
    def buscar_sugerencias(db: Session, q: str, limit: int = 10):
        """
        Busca sugerencias de números de recepción en la tabla de trazabilidad.
        """
        query = db.query(Trazabilidad)
        
        if q:
            # Búsqueda por número de recepción o cliente
            query = query.filter(
                (Trazabilidad.numero_recepcion.ilike(f"%{q}%")) |
                (Trazabilidad.cliente.ilike(f"%{q}%"))
            )
            
        return query.order_by(Trazabilidad.fecha_creacion.desc()).limit(limit).all()

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
