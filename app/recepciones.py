from fastapi import APIRouter, HTTPException, Depends, Response
from pydantic import BaseModel, Field
from typing import List, Optional, Any
from datetime import date, datetime
from sqlalchemy import text
from app.database import get_db, get_db_session, _upload_to_supabase_storage

router = APIRouter(
    prefix="/recepciones",
    tags=["Laboratorio Recepciones"]
)

# --- Pydantic Models ---

class SampleCreate(BaseModel):
    item_numero: int
    codigo_muestra_lem: Optional[str] = None
    identificacion_muestra: str
    estructura: str
    fc_kg_cm2: float = 280
    edad: int = 7
    fecha_moldeo: Optional[str] = None
    hora_moldeo: Optional[str] = None
    fecha_rotura: Optional[str] = None
    requiere_densidad: bool = False

class ReceptionCreate(BaseModel):
    numero_ot: str
    numero_recepcion: str
    numero_cotizacion: Optional[str] = None
    cliente: str
    domicilio_legal: str
    ruc: str
    persona_contacto: str
    email: Optional[str] = None
    telefono: Optional[str] = None
    solicitante: str
    domicilio_solicitante: str
    proyecto: str
    ubicacion: str
    
    fecha_recepcion: Optional[str] = None  # Receives string dd/mm/yyyy
    fecha_estimada_culminacion: Optional[str] = None
    
    emision_fisica: bool = False
    emision_digital: bool = True
    
    entregado_por: str
    recibido_por: str
    
    muestras: List[SampleCreate]

class ReceptionResponse(ReceptionCreate):
    id: int
    created_at: datetime
    updated_at: datetime
    
    class Config:
        orm_mode = True

# --- Helper to parse date dd/mm/yyyy to yyyy-mm-dd ---
def parse_date(date_str: Optional[str]) -> Optional[date]:
    if not date_str:
        return None
    try:
        # Expecting dd/mm/yyyy
        return datetime.strptime(date_str, "%d/%m/%Y").date()
    except ValueError:
        return None

# --- Endpoints ---

@router.post("/", response_model=dict)
def create_recepcion(reception: ReceptionCreate, db=Depends(get_db_session)):
    try:
        # Convert Pydantic model to dict for JSON storage of samples
        muestras_json = [s.dict() for s in reception.muestras]
        
        # Parse dates
        f_recepcion = parse_date(reception.fecha_recepcion)
        f_culminacion = parse_date(reception.fecha_estimada_culminacion)

        # Insert using raw SQL for simplicity given existing pattern
        query = text("""
            INSERT INTO recepciones (
                numero_recepcion, numero_ot, numero_cotizacion, cliente,
                domicilio_legal, ruc, persona_contacto, email, telefono,
                solicitante, domicilio_solicitante, proyecto, ubicacion,
                fecha_recepcion, fecha_estimada_culminacion,
                emision_fisica, emision_digital,
                entregado_por, recibido_por, muestras
            ) VALUES (
                :num_rec, :ot, :cot, :cli, :dom_leg, :ruc, :cont, :email, :tel,
                :sol, :dom_sol, :proy, :ubic,
                :f_rec, :f_culm,
                :e_fis, :e_dig,
                :entr, :recib, :muestras
            ) RETURNING id
        """)
        
        params = {
            "num_rec": reception.numero_recepcion,
            "ot": reception.numero_ot,
            "cot": reception.numero_cot,
            "cli": reception.cliente,
            "dom_leg": reception.domicilio_legal,
            "ruc": reception.ruc,
            "cont": reception.persona_contacto,
            "email": reception.email,
            "tel": reception.telefono,
            "sol": reception.solicitante,
            "dom_sol": reception.domicilio_solicitante,
            "proy": reception.proyecto,
            "ubic": reception.ubicacion,
            "f_rec": f_recepcion,
            "f_culm": f_culminacion,
            "e_fis": reception.emision_fisica,
            "e_dig": reception.emision_digital,
            "entr": reception.entregado_por,
            "recib": reception.recibido_por,
            "muestras": start_json_dump(muestras_json) # Need json.dumps? SQLAlchemy handles JSONB with dict usually if using ORM, but raw SQL might need dumps.
            # Actually, psycopg2 usually adapts dict to jsonb automatically. Let's try passing dict/list directly.
        }
        
        # Note: SQLAlchemy key-value binding with text() usually handles basic types.
        # For JSONB, we might need json.dumps if the driver doesn't support list/dict direct binding in text mode easily.
        # Let's import json to be safe.
        import json
        params["muestras"] = json.dumps(muestras_json)

        result = db.execute(query, params)
        new_id = result.fetchone()[0]
        db.commit()
        
        return {"status": "success", "id": new_id, "message": "Recepción creada exitosamente"}

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/", response_model=List[dict])
def list_recepciones(limit: int = 50, db=Depends(get_db_session)):
    try:
        query = text("""
            SELECT * FROM recepciones ORDER BY created_at DESC LIMIT :limit
        """)
        result = db.execute(query, {"limit": limit})
        
        # Robust conversion compatible with most SQLAlchemy versions
        keys = result.keys()
        rows = []
        for row in result:
            rows.append(dict(zip(keys, row)))
            
        return rows
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{id}/excel")
def download_recepcion_excel(id: int, db=Depends(get_db_session)):
    # 1. Get Reception
    query = text("SELECT * FROM recepciones WHERE id = :id")
    result = db.execute(query, {"id": id}).fetchone()
    
    if not result:
        raise HTTPException(status_code=404, detail="Recepción no encontrada")
    
    # Convert Row directly to dict for use
    recepcion = dict(result._mapping)
    
    # 2. Generate Excel
    from app.recepcion_export import export_recepcion_xlsx
    try:
        excel_file = export_recepcion_xlsx(recepcion)
    except Exception as e:
        print(f"Error generating Excel: {e}")
        raise HTTPException(status_code=500, detail=f"Error generando Excel: {str(e)}")
        
    # 3. Upload to Supabase Storage
    # Bucket name: "recepciones" (User needs to ensure this bucket exists, or we use "public")
    # Using "cotizaciones" for now if we want to share? No, better separate. 
    # Let's assume "recepciones" bucket exists or use "archivos".
    bucket = "recepciones" 
    filename = f"OT-{recepcion['numero_ot']}.xlsx"
    
    from app.database import _upload_to_supabase_storage
    
    # Try upload
    try:
        path = _upload_to_supabase_storage(excel_file, bucket, filename)
        if path:
            # 4. Update DB
            update_q = text("UPDATE recepciones SET archivo_path = :path WHERE id = :id")
            db.execute(update_q, {"path": path, "id": id})
            db.commit()
    except Exception as e:
        print(f"Upload failed: {e}")
        # Continue to download even if upload fails? Yes.
        
    # Reset buffer for download
    excel_file.seek(0)
    
    # 5. Return File
    headers = {
        'Content-Disposition': f'attachment; filename="{filename}"'
    }
    return Response(content=excel_file.read(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers=headers)

@router.delete("/{id}")
def delete_recepcion(id: int, db=Depends(get_db_session)):
    try:
        # Check existence
        check = db.execute(text("SELECT id FROM recepciones WHERE id = :id"), {"id": id}).fetchone()
        if not check:
             raise HTTPException(status_code=404, detail="Recepción no encontrada")
        
        # Delete
        db.execute(text("DELETE FROM recepciones WHERE id = :id"), {"id": id})
        db.commit()
        return {"status": "success", "message": "Recepción eliminada"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
