from sqlalchemy.orm import Session
from .models import Trazabilidad
from app.modules.recepcion.models import RecepcionMuestra
from app.modules.verificacion.models import VerificacionMuestras
from app.modules.compresion.models import EnsayoCompresion
from typing import Optional

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
        import re
        clean = re.sub(r'-REC$', '', clean, flags=re.IGNORECASE)
        clean = re.sub(r'-REC-(\d{2})$', r'-\1', clean, flags=re.IGNORECASE)

        # Quitar sufijo de año si existe (formato: NNNN-YY donde YY son 2 dígitos)
        match = re.match(r'^(.+)-(\d{2})$', clean)
        if match:
            return match.group(1)
        return clean

    @staticmethod
    def _buscar_recepcion_flexible(db: Session, numero: str) -> Optional[tuple[Optional[RecepcionMuestra], str]]:
        """
        Busca una recepción permitiendo variaciones de formato.
        Ignora automáticamente prefijos (REC-) y sufijos de año (-26).
        Retorna una tupla (instancia_recepcion, numero_canonico).
        """
        if not numero:
            return None, ""
        
        # Extraer el número base limpio (sin REC- ni -YY)
        base_num = TracingService._extraer_numero_base(numero)
        
        # Generar todas las variantes posibles del número
        variantes = []
        # Orden de prioridad: exacto, limpio, base, base con año
        variantes.append(numero)                    # Exacto como viene
        clean_num = numero.replace("REC-", "").replace("rec-", "").strip()
        if clean_num != numero:
            variantes.append(clean_num)             # Sin prefijo REC-
        if base_num != clean_num:
            variantes.append(base_num)              # Sin sufijo de año
        
        # Eliminar duplicados manteniendo orden
        seen = set()
        variantes_unicas = []
        for v in variantes:
            if v not in seen:
                seen.add(v)
                variantes_unicas.append(v)
        
        # Buscar en orden de prioridad
        for variante in variantes_unicas:
            recepcion = db.query(RecepcionMuestra).filter(
                RecepcionMuestra.numero_recepcion == variante
            ).first()
            if recepcion:
                return recepcion, recepcion.numero_recepcion

        return None, base_num

    @staticmethod
    def actualizar_trazabilidad(db: Session, numero_recepcion: str):
        """
        Sincroniza el estado de una recepción en la tabla maestra de trazabilidad.
        """
        if not numero_recepcion:
            return None

        # 1. Obtener recepción con búsqueda inteligente
        recepcion, canonical_numero = TracingService._buscar_recepcion_flexible(db, numero_recepcion)
        
        # Extraer número base para búsquedas cruzadas entre módulos
        base_num = TracingService._extraer_numero_base(numero_recepcion)
        numeros_busqueda = list(set([canonical_numero, base_num, numero_recepcion]))

        # 2. Buscar en otros módulos usando todas las variantes del número
        verificacion = None
        compresion = None
        for num in numeros_busqueda:
            if not verificacion:
                verificacion = db.query(VerificacionMuestras).filter(VerificacionMuestras.numero_verificacion == num).first()
            if not compresion:
                compresion = db.query(EnsayoCompresion).filter(EnsayoCompresion.numero_recepcion == num).first()
        
        # 3. Buscar si ya existe en trazabilidad
        traza = db.query(Trazabilidad).filter(Trazabilidad.numero_recepcion == canonical_numero).first()

        # --- PERSISTENCE FIX ---
        # Si NO EXISTE NADA en los módulos origen, MANTENEMOS la fila como histórico (gris)
        # pero ya no la borramos automáticamente. El usuario la borrará manualmente si desea.
        if not recepcion and not verificacion and not compresion:
            if not traza:
                return None # No crear trazas vacías de la nada, pero si ya existe se queda
        
        if not traza:
            traza = Trazabilidad(numero_recepcion=canonical_numero)
            db.add(traza)
            
        # 4. Actualizar datos básicos (priorizando la recepción si existe)
        if recepcion:
            traza.cliente = recepcion.cliente
            traza.proyecto = recepcion.proyecto
        elif verificacion:
            traza.cliente = verificacion.cliente
            traza.proyecto = "Cargado desde Verificación"
        elif compresion:
            # Intentar obtener de metadatos de compresión si existe vinculación previa
            traza.cliente = "Cargado desde Compresión"
            traza.proyecto = "Proyecto no identificado"
        
        # 5. Calcular estados con verificación de almacenamiento
        from app.utils.storage_utils import StorageUtils
        
        # Recepción
        if recepcion:
            has_file = True
            if recepcion.object_key:
                has_file = StorageUtils.verify_supabase_file(recepcion.bucket, recepcion.object_key)
            traza.estado_recepcion = "completado" if has_file else "en_proceso"
        else:
            traza.estado_recepcion = "pendiente"

        # Verificación
        if verificacion:
            has_file = False
            # Verificar en Supabase
            if verificacion.object_key:
                # El object_key en verificación a veces incluye el bucket: "verificaciones/file.xlsx"
                parts = verificacion.object_key.split('/')
                if len(parts) > 1:
                    has_file = StorageUtils.verify_supabase_file(parts[0], "/".join(parts[1:]))
                else:
                    has_file = StorageUtils.verify_supabase_file("verificaciones", verificacion.object_key)
            
            # Si no está en Supabase, verificar localmente (archivo_excel)
            if not has_file and verificacion.archivo_excel:
                if os.path.exists(verificacion.archivo_excel):
                    has_file = True
            
            traza.estado_verificacion = "completado" if has_file else "en_proceso"
        else:
            traza.estado_verificacion = "pendiente"
        
        # Compresión
        if compresion:
            has_file = True
            if compresion.object_key:
                has_file = StorageUtils.verify_supabase_file(compresion.bucket, compresion.object_key)
            
            if has_file and compresion.estado == "COMPLETADO":
                traza.estado_compresion = "completado"
            else:
                traza.estado_compresion = "en_proceso"
        else:
            traza.estado_compresion = "pendiente"
            
        # 6. Guardar metadata extra en JSON
        traza.data_consolidada = {
            "recepcion_id": recepcion.id if recepcion else None,
            "recepcion_estado": recepcion.estado if recepcion else None,
            "numero_ot": getattr(recepcion, 'numero_ot', None) if recepcion else (compresion.numero_ot if compresion else None),
            "cliente": traza.cliente,
            "proyecto": traza.proyecto,
            "verificacion_id": verificacion.id if verificacion else None,
            "compresion_id": compresion.id if compresion else None,
            "compresion_estado": compresion.estado if compresion else None,
            "storage_verified": True
        }
        
        import os # Asegurar que os esté disponible para la verificación local
        db.commit()
        db.refresh(traza)
        return traza

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
