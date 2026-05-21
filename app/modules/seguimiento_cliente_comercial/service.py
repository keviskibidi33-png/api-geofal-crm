from __future__ import annotations

import io
import os
from datetime import date, datetime
from typing import List, Tuple, Optional
import openpyxl
from sqlalchemy import or_, and_, func
from sqlalchemy.orm import Session

from .models import SeguimientoClienteComercial
from .schemas import SeguimientoClienteComercialCreate, SeguimientoClienteComercialUpdate, SeguimientoClienteComercialPatch

# Predefined catalogs from the LISTA sheet to merge with dynamic values
PREDEFINED_ASESORES = ["Silvia Peralta", "Juan Garcia", "SILVIA"]
PREDEFINED_CONTACTOS = ["WHATSAPP", "LLAMADA", "CORREO", "EN PROSPECTO"]
PREDEFINED_RUBROS = ["LABORATORIO", "INGENIERÍA", "ALQUILER", "EN ESPERA"]
PREDEFINED_ESTADOS = [
    "EN ESPERA DE ATENCIÓN",
    "SE SOLICITÓ INFORMACIÓN",
    "EN ESPERA DE INFORMACIÓN",
    "NO ENVIÓ LA INFORMACIÓN",
    "DESCARTO El SERVICIO",
    "COTIZACIÓN REALIZADA",
    "PROSPECTO",
    "CONTACTADO",
    "INFORMACIÓN RECIBIDA",
    "COTIZACIÓN EN PROCESO",
    "COTIZACIÓN ENVIADA",
    "1. SOLICITUD INFORMACION",
    "2. PROCESANDO INFORMACION",
    "3. COTIZACION",
    "4. SEG. COTIZACION",
]

class SeguimientoClienteComercialService:
    @staticmethod
    def listar_seguimientos(
        db: Session,
        *,
        search: Optional[str] = None,
        asesor: Optional[str] = None,
        estado_cliente: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Tuple[int, List[SeguimientoClienteComercial]]:
        """
        Retrieves paginated and filtered tracking records from the database.
        """
        query = db.query(SeguimientoClienteComercial)
        
        # Apply search filter (search across razon_social, persona_contacto, ruc, email, celular, n_cotizacion)
        if search:
            search_pattern = f"%{search.strip()}%"
            query = query.filter(
                or_(
                    SeguimientoClienteComercial.razon_social.ilike(search_pattern),
                    SeguimientoClienteComercial.persona_contacto.ilike(search_pattern),
                    SeguimientoClienteComercial.ruc.ilike(search_pattern),
                    SeguimientoClienteComercial.email.ilike(search_pattern),
                    SeguimientoClienteComercial.numero_celular.ilike(search_pattern),
                    SeguimientoClienteComercial.numero_cotizacion.ilike(search_pattern)
                )
            )
            
        # Apply advisor filter
        if asesor:
            query = query.filter(SeguimientoClienteComercial.asesor.ilike(asesor.strip()))
            
        # Apply state filter
        if estado_cliente:
            query = query.filter(SeguimientoClienteComercial.estado_cliente.ilike(estado_cliente.strip()))
            
        # Order by: first by 'no' descending or 'id' descending to show newest first
        query = query.order_by(
            SeguimientoClienteComercial.no.desc().nullslast(),
            SeguimientoClienteComercial.id.desc()
        )
        
        total = query.count()
        items = query.offset(max(0, offset)).limit(max(1, min(limit, 200))).all()
        return total, items

    @staticmethod
    def obtener_seguimiento(db: Session, id: int) -> Optional[SeguimientoClienteComercial]:
        """
        Finds a single record by ID.
        """
        return db.query(SeguimientoClienteComercial).filter(SeguimientoClienteComercial.id == id).first()

    @staticmethod
    def crear_seguimiento(
        db: Session,
        *,
        data: SeguimientoClienteComercialCreate,
        creado_por: Optional[str] = None
    ) -> SeguimientoClienteComercial:
        """
        Creates a new tracking record.
        Auto-increments the 'no' field based on the maximum 'no' currently in the table.
        """
        max_no = db.query(func.max(SeguimientoClienteComercial.no)).scalar() or 0
        
        db_item = SeguimientoClienteComercial(
            no=max_no + 1,
            fecha_contacto=data.fecha_contacto or date.today(),
            persona_contacto=data.persona_contacto,
            numero_celular=data.numero_celular,
            email=data.email,
            razon_social=data.razon_social,
            ruc=data.ruc,
            asesor=data.asesor,
            contacto=data.contacto,
            rubro=data.rubro,
            estado_cliente=data.estado_cliente,
            servicio_solicitado=data.servicio_solicitado,
            fecha_ultimo_contacto=data.fecha_ultimo_contacto,
            observaciones=data.observaciones,
            numero_cotizacion=data.numero_cotizacion,
            estado_seguimiento=data.estado_seguimiento,
            creado_por=creado_por
        )
        db.add(db_item)
        db.commit()
        db.refresh(db_item)
        return db_item

    @staticmethod
    def actualizar_seguimiento(
        db: Session,
        id: int,
        data: SeguimientoClienteComercialUpdate
    ) -> Optional[SeguimientoClienteComercial]:
        """
        Updates an entire record.
        """
        db_item = SeguimientoClienteComercialService.obtener_seguimiento(db, id)
        if not db_item:
            return None
            
        update_data = data.dict(exclude_unset=True)
        for key, val in update_data.items():
            setattr(db_item, key, val)
            
        db.commit()
        db.refresh(db_item)
        return db_item

    @staticmethod
    def patch_seguimiento(
        db: Session,
        id: int,
        data: dict
    ) -> Optional[SeguimientoClienteComercial]:
        """
        Partially updates a record (used for inline grid edits).
        """
        db_item = SeguimientoClienteComercialService.obtener_seguimiento(db, id)
        if not db_item:
            return None
            
        # Define allowed fields for patching (excluding metadata)
        allowed_fields = {
            "no", "fecha_contacto", "persona_contacto", "numero_celular",
            "email", "razon_social", "ruc", "asesor", "contacto", "rubro",
            "estado_cliente", "servicio_solicitado", "fecha_ultimo_contacto",
            "observaciones", "numero_cotizacion", "estado_seguimiento"
        }
        
        for key, val in data.items():
            if key in allowed_fields:
                # Type conversions if necessary
                if key in ("fecha_contacto", "fecha_ultimo_contacto") and val:
                    if isinstance(val, str):
                        try:
                            val = datetime.strptime(val.split("T")[0], "%Y-%m-%d").date()
                        except ValueError:
                            val = None
                setattr(db_item, key, val)
                
        db.commit()
        db.refresh(db_item)
        return db_item

    @staticmethod
    def eliminar_seguimiento(db: Session, id: int) -> bool:
        """
        Deletes a record.
        """
        db_item = SeguimientoClienteComercialService.obtener_seguimiento(db, id)
        if not db_item:
            return False
        db.delete(db_item)
        db.commit()
        return True

    @staticmethod
    def obtener_catalogos(db: Session) -> dict:
        """
        Returns merged distinct catalog values for autocomplete dropdowns.
        """
        # Query distinct values from db
        db_asesores = db.query(SeguimientoClienteComercial.asesor).distinct().all()
        db_contactos = db.query(SeguimientoClienteComercial.contacto).distinct().all()
        db_rubros = db.query(SeguimientoClienteComercial.rubro).distinct().all()
        db_estados = db.query(SeguimientoClienteComercial.estado_cliente).distinct().all()

        # Merge utility helper
        def merge_catalogs(predefined: list, db_results: list) -> list[str]:
            merged = set()
            # Add predefined first
            for item in predefined:
                if item:
                    merged.add(item.strip())
            # Add database results
            for row in db_results:
                val = row[0]
                if val:
                    merged.add(val.strip())
            return sorted(list(merged))

        return {
            "asesores": merge_catalogs(PREDEFINED_ASESORES, db_asesores),
            "contactos": merge_catalogs(PREDEFINED_CONTACTOS, db_contactos),
            "rubros": merge_catalogs(PREDEFINED_RUBROS, db_rubros),
            "estados": merge_catalogs(PREDEFINED_ESTADOS, db_estados),
        }

    @staticmethod
    def importar_excel(db: Session, file_content: bytes, creado_por: Optional[str] = None) -> int:
        """
        Imports database records from the Excel file contents.
        This deletes all existing records in 'seguimiento_cliente_comercial' and inserts from row 5 onwards.
        """
        # Load workbook
        wb = openpyxl.load_workbook(io.BytesIO(file_content), data_only=True)
        if 'SEG.CLIENTE' not in wb.sheetnames:
            raise ValueError("La hoja 'SEG.CLIENTE' no fue encontrada en el archivo de Excel.")
            
        sheet = wb['SEG.CLIENTE']
        
        # Clear existing table data to prevent duplicate keys
        db.query(SeguimientoClienteComercial).delete()
        db.commit()
        
        inserted_count = 0
        
        def to_str(val) -> Optional[str]:
            if val is None:
                return None
            val_str = str(val).strip()
            if not val_str:
                return None
            # Handle float representation (e.g. RUC, cellular converted to float with .0)
            if isinstance(val, float) and val.is_integer():
                return str(int(val))
            return val_str
            
        def to_int(val) -> Optional[int]:
            if val is None:
                return None
            try:
                return int(float(val))
            except (ValueError, TypeError):
                return None

        def to_date(val) -> Optional[date]:
            if val is None:
                return None
            if isinstance(val, datetime):
                return val.date()
            if isinstance(val, date):
                return val
            if isinstance(val, str):
                val_str = val.strip()
                if not val_str:
                    return None
                for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
                    try:
                        return datetime.strptime(val_str, fmt).date()
                    except ValueError:
                        continue
            return None

        # Parse rows starting from row 5
        for r in range(5, sheet.max_row + 1):
            no_val = sheet.cell(row=r, column=1).value
            fecha_contacto_val = sheet.cell(row=r, column=2).value
            persona_contacto_val = sheet.cell(row=r, column=3).value
            celular_val = sheet.cell(row=r, column=4).value
            email_val = sheet.cell(row=r, column=5).value
            razon_social_val = sheet.cell(row=r, column=6).value
            ruc_val = sheet.cell(row=r, column=7).value
            asesor_val = sheet.cell(row=r, column=8).value
            contacto_val = sheet.cell(row=r, column=9).value
            rubro_val = sheet.cell(row=r, column=10).value
            estado_cliente_val = sheet.cell(row=r, column=11).value
            servicio_val = sheet.cell(row=r, column=12).value
            fecha_ultimo_val = sheet.cell(row=r, column=13).value
            observaciones_val = sheet.cell(row=r, column=14).value
            cotizacion_val = sheet.cell(row=r, column=15).value
            estado_seg_val = sheet.cell(row=r, column=16).value
            
            # If the row is entirely empty, skip it. Specifically check if crucial fields are missing
            if not any([no_val, fecha_contacto_val, persona_contacto_val, razon_social_val, ruc_val]):
                continue
                
            db_item = SeguimientoClienteComercial(
                no=to_int(no_val),
                fecha_contacto=to_date(fecha_contacto_val),
                persona_contacto=to_str(persona_contacto_val),
                numero_celular=to_str(celular_val),
                email=to_str(email_val),
                razon_social=to_str(razon_social_val),
                ruc=to_str(ruc_val),
                asesor=to_str(asesor_val),
                contacto=to_str(contacto_val),
                rubro=to_str(rubro_val),
                estado_cliente=to_str(estado_cliente_val),
                servicio_solicitado=to_str(servicio_val),
                fecha_ultimo_contacto=to_date(fecha_ultimo_val),
                observaciones=to_str(observaciones_val),
                numero_cotizacion=to_str(cotizacion_val),
                estado_seguimiento=to_str(estado_seg_val),
                creado_por=creado_por
            )
            db.add(db_item)
            inserted_count += 1
            
            # Flush periodically to avoid huge memory use
            if inserted_count % 100 == 0:
                db.flush()
                
        db.commit()
        return inserted_count

    @staticmethod
    def exportar_excel(db: Session, template_path: str) -> io.BytesIO:
        """
        Loads the template file, populates columns A-P starting from row 5 with database records,
        and returns the result as a BytesIO file.
        """
        if not os.path.exists(template_path):
            raise FileNotFoundError(f"El template del excel no existe en {template_path}")
            
        # Load template
        wb = openpyxl.load_workbook(template_path, data_only=False)
        if 'SEG.CLIENTE' not in wb.sheetnames:
            raise ValueError("La hoja 'SEG.CLIENTE' no fue encontrada en el template de Excel.")
            
        sheet = wb['SEG.CLIENTE']
        
        # Get all records sorted by 'no' ascending
        records = db.query(SeguimientoClienteComercial).order_by(
            SeguimientoClienteComercial.no.asc().nullslast(),
            SeguimientoClienteComercial.id.asc()
        ).all()
        
        # Clean existing template data rows (from row 5 onwards, up to sheet.max_row)
        for r in range(5, max(sheet.max_row + 1, len(records) + 10)):
            for col in range(1, 17):
                sheet.cell(row=r, column=col).value = None

        # Write data keeping styles
        for idx, rec in enumerate(records):
            r = 5 + idx
            sheet.cell(row=r, column=1).value = rec.no
            sheet.cell(row=r, column=2).value = rec.fecha_contacto
            sheet.cell(row=r, column=3).value = rec.persona_contacto
            sheet.cell(row=r, column=4).value = rec.numero_celular
            sheet.cell(row=r, column=5).value = rec.email
            sheet.cell(row=r, column=6).value = rec.razon_social
            sheet.cell(row=r, column=7).value = rec.ruc
            sheet.cell(row=r, column=8).value = rec.asesor
            sheet.cell(row=r, column=9).value = rec.contacto
            sheet.cell(row=r, column=10).value = rec.rubro
            sheet.cell(row=r, column=11).value = rec.estado_cliente
            sheet.cell(row=r, column=12).value = rec.servicio_solicitado
            sheet.cell(row=r, column=13).value = rec.fecha_ultimo_contacto
            sheet.cell(row=r, column=14).value = rec.observaciones
            sheet.cell(row=r, column=15).value = rec.numero_cotizacion
            sheet.cell(row=r, column=16).value = rec.estado_seguimiento

        # Save workbook to BytesIO
        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        return output
