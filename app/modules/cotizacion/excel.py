
import io
import json
from datetime import date
from typing import Any, List
from pathlib import Path
from sqlalchemy import text
from app.database import engine
from .schemas import QuoteExportRequest

# Import the proven XML-loader
# We expect app/xlsx_direct_v2.py to exist (copied from proven commit)
try:
    from app.xlsx_direct_v2 import export_xlsx_direct
except ImportError:
    # Fallback/Error if file missing - but we copied it so it should be fine
    print("CRITICAL: app.xlsx_direct_v2 not found. Excel export will fail.")
    def export_xlsx_direct(*args, **kwargs):
        raise NotImplementedError("xlsx_direct_v2 missing")

# --- Template Path Constants ---
TEMPLATE_VARIANTS = {
    'V1': 'Temp_Cotizacion.xlsx',
    'V2': 'V2 - PROBETAS.xlsx',
    'V3': 'V3 - DENSIDAD DE CAMPO Y MUESTREO.xlsx',
    'V4': 'V4 - EXTRACCIÓN DE DIAMANTINA.xlsx',
    'V5': 'V5 - DIAMANTINA PARA PASES.xlsx',
    'V6': 'V6 - ALBAÑILERÍA.xlsx',
    'V7': 'V7 - VIGA BECKELMAN.xlsx',
    'V8': 'V8 - CONTROL DE CALIDAD DE CONCRETO FRESCO EN OBRA.xlsx',
}

def _get_template_path(template_id: str | None = None) -> Path:
    """Get template path based on template_id or default"""
    filename = TEMPLATE_VARIANTS.get(template_id, 'Temp_Cotizacion.xlsx') if template_id else 'Temp_Cotizacion.xlsx'
    
    current_dir = Path(__file__).resolve().parent
    app_dir = current_dir.parents[1] # app/
    
    possible_paths = [
        app_dir / "templates" / filename,  # Standard: app/templates/
        Path("/app/templates") / filename, # Docker absolute
        current_dir.parents[2] / "app" / "templates" / filename, # Root/app/templates/
    ]
    
    for p in possible_paths:
        if p.exists():
            return p
            
    # Fallback to standard app location
    return app_dir / "templates" / filename


def generate_quote_excel(payload: QuoteExportRequest) -> io.BytesIO:
    """
    Generates Excel utilizing the 'proven' low-level XML manipulation logic.
    Ref: api-v2 (commit 85d9087) logic.
    """
    template_path = _get_template_path(payload.template_id)
    if not template_path.exists():
        raise FileNotFoundError(f"Template not found: {template_path}")
    
    # 1. Prepare export_data dictionary (as expected by export_xlsx_direct)
    # The payload is pydantic, so we convert fields.
    
    fecha_emision = payload.fecha_emision or date.today()
    cotizacion_numero = payload.cotizacion_numero or "000"
    
    items_list = []
    if payload.items:
        items_list = [
            {
                'codigo': item.codigo,
                'descripcion': item.descripcion,
                'norma': item.norma,
                'acreditado': item.acreditado,
                'costo_unitario': item.costo_unitario,
                'cantidad': item.cantidad,
            }
            for item in payload.items
        ]

    export_data = {
        'cotizacion_numero': cotizacion_numero,
        'fecha_emision': fecha_emision,
        'cliente': payload.cliente or '',
        'ruc': payload.ruc or '',
        'contacto': payload.contacto or '',
        'telefono': payload.telefono_contacto or '',
        'email': payload.correo or '',
        'correo': payload.correo_vendedor or payload.correo or '', # Logic from main.py
        'fecha_solicitud': payload.fecha_solicitud,
        'proyecto': payload.proyecto or '',
        'ubicacion': payload.ubicacion or '',
        'personal_comercial': payload.personal_comercial or '',
        'telefono_comercial': payload.telefono_comercial or '',
        'plazo_dias': payload.plazo_dias or 0,
        'condicion_pago': payload.condicion_pago or '',
        'condiciones_ids': payload.condiciones_ids or [],
        'items': items_list,
        'include_igv': payload.include_igv,
        'igv_rate': payload.igv_rate,
        # Placeholder for texts
        'condiciones_textos': []
    }
    
    # 2. Fetch Condiciones Texts from DB (Logic migrated from api-v2 main.py)
    if export_data['condiciones_ids']:
        try:
            # We use engine.connect() for a raw connection feel similar to psycopg2
            # but via SQLAlchemy to be safe with the pool
            t = text("SELECT texto FROM condiciones_especificas WHERE id = ANY(:ids) AND activo = true ORDER BY orden ASC")
            
            # Using clean list of strings for ANY(:ids)
            # Ensure the IDs are valid UUID format or strings? 
            # Postgres ANY(array) expects a list/array.
            c_ids = [str(uid) for uid in export_data['condiciones_ids']]
            
            with engine.connect() as conn:
                result = conn.execute(t, {"ids": c_ids})
                # result is iterable of Row objects
                texts = [row[0] for row in result]
                export_data['condiciones_textos'] = texts
                print(f"DEBUG EXCEL: Loaded {len(texts)} conditions")
        except Exception as e:
            print(f"Warning EXCEL: Could not load conditions: {e}")
            import traceback
            traceback.print_exc()
            export_data['condiciones_textos'] = []
    
    # 3. Call the direct XML exporter
    print(f"DEBUG EXCEL: Generating with export_xlsx_direct using {template_path}")
    return export_xlsx_direct(str(template_path), export_data)
