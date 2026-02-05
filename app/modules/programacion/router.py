from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from datetime import date
from pathlib import Path
from .schemas import ProgramacionExportRequest
from .excel import export_programacion_xlsx

router = APIRouter(prefix="/programacion", tags=["Programacion"])

@router.post("/export")
async def export_programacion(payload: ProgramacionExportRequest):
    """
    Export Programación data to Excel using the specified template.
    """
    # Locate template
    filename = "Template_Programacion.xlsx"
    # Logic copied from main.py to find template relative to app root or current file
    # We are in app/modules/programacion/router.py
    # app/ is parents[2]
    
    base_path = Path(__file__).resolve().parents[3] # api-geofal-crm root
    
    possible_paths = [
        base_path / filename,
        base_path / "app" / filename,
        Path("/app") / filename,
    ]
    
    template_path = None
    for p in possible_paths:
        if p.exists():
            template_path = p
            break
            
    if not template_path:
        # Fallback hardcoded path from legacy code
        fallback = Path("c:/Users/Lenovo/Documents/crmnew/api-geofal-crm/Template_Programacion.xlsx")
        if fallback.exists():
            template_path = fallback
        else:
             raise HTTPException(status_code=500, detail=f"Template {filename} not found.")

    try:
        # Convert Pydantic models to list of dicts
        items_dict = [item.model_dump() for item in payload.items]
        
        output = export_programacion_xlsx(str(template_path), items_dict)
        
        export_filename = f"Programacion_{date.today().strftime('%Y%m%d')}.xlsx"
        
        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={export_filename}"}
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")
