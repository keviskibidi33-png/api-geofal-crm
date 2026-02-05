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
    
    # Path resolution: app/modules/programacion/router.py -> app/
    current_dir = Path(__file__).resolve().parent
    app_dir = current_dir.parents[1] # app/
    
    possible_paths = [
        app_dir / "templates" / filename,  # Standard: app/templates/
        Path("/app/templates") / filename, # Docker absolute
        current_dir.parents[2] / "app" / "templates" / filename, # Root/app/templates/
    ]
    
    template_path = None
    for p in possible_paths:
        if p.exists():
            template_path = p
            break
            
    if not template_path:
        # Final fallback/error
        raise HTTPException(status_code=500, detail=f"Template {filename} not found in any expected location.")

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
