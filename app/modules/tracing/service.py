from sqlalchemy.orm import Session
from .models import Trazabilidad
from app.modules.recepcion.models import RecepcionMuestra
from app.modules.verificacion.models import VerificacionMuestras
from app.modules.compresion.models import EnsayoCompresion
from typing import Optional

class TracingService:
    @staticmethod
    def _buscar_recepcion_flexible(db: Session, numero: str) -> Optional[tuple[Optional[RecepcionMuestra], str]]:
        """
        Busca una recepción permitiendo variaciones de formato.
        Retorna una tupla (instancia_recepcion, numero_canonico).
        """
        if not numero:
            return None, ""
            
        # 1. Búsqueda exacta
        recepcion = db.query(RecepcionMuestra).filter(RecepcionMuestra.numero_recepcion == numero).first()
        if recepcion:
            return recepcion, numero

        # 2. Búsqueda flexible (fuzzy)
        clean_num = numero.replace("REC-", "").upper()
        
        # A. Sin prefijo REC-
        recepcion = db.query(RecepcionMuestra).filter(RecepcionMuestra.numero_recepcion == clean_num).first()
        if recepcion:
            return recepcion, clean_num
            
        # B. Intentar con prefijo de año (ej: 1111 -> 1111-26)
        # Asumiendo año 26 por defecto si no tiene guión
        if "-" not in clean_num:
            recepcion = db.query(RecepcionMuestra).filter(RecepcionMuestra.numero_recepcion == f"{clean_num}-26").first()
            if recepcion:
                return recepcion, f"{clean_num}-26"

        return None, numero

    @staticmethod
    def actualizar_trazabilidad(db: Session, numero_recepcion: str):
        """
        Sincroniza el estado de una recepción en la tabla maestra de trazabilidad.
        """
        if not numero_recepcion:
            return None

        # 1. Obtener recepción con búsqueda inteligente
        recepcion, canonical_numero = TracingService._buscar_recepcion_flexible(db, numero_recepcion)

        # 2. Buscar en otros módulos usando el número canónico
        verificacion = db.query(VerificacionMuestras).filter(VerificacionMuestras.numero_verificacion == canonical_numero).first()
        compresion = db.query(EnsayoCompresion).filter(EnsayoCompresion.numero_recepcion == canonical_numero).first()
        
        # Si NO EXISTE NADA, abortar
        if not recepcion and not verificacion and not compresion:
            return None
        
        # 3. Buscar si ya existe en trazabilidad
        traza = db.query(Trazabilidad).filter(Trazabilidad.numero_recepcion == canonical_numero).first()
        
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
        
        # 5. Calcular estados
        traza.estado_recepcion = "completado" if recepcion else "pendiente"
        traza.estado_verificacion = "completado" if verificacion else "pendiente"
        
        if compresion:
            traza.estado_compresion = "completado" if compresion.estado == "COMPLETADO" else "en_proceso"
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
            "compresion_estado": compresion.estado if compresion else None
        }
        
        db.commit()
        db.refresh(traza)
        return traza
        
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
