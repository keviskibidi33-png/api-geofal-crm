from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from datetime import date
from pathlib import Path
from .schemas import ProgramacionExportRequest
from .excel import export_programacion_xlsx, export_programacion_comercial_xlsx, export_programacion_administracion_xlsx

router = APIRouter(prefix="/programacion", tags=["Programacion"])


def _find_template(filename: str) -> Path:
    """Helper to locate a template file in possible locations."""
    current_dir = Path(__file__).resolve().parent
    app_dir = current_dir.parents[1]  # app/
    
    possible_paths = [
        app_dir / "templates" / filename,
        Path("/app/templates") / filename,
        current_dir.parents[2] / "app" / "templates" / filename,
    ]
    
    for p in possible_paths:
        if p.exists():
            return p
    
    raise HTTPException(status_code=500, detail=f"Template {filename} not found in any expected location.")


@router.post("/export")
async def export_programacion(payload: ProgramacionExportRequest):
    """Export Programación LAB data to Excel."""
    template_path = _find_template("Template_Programacion.xlsx")
    
    try:
        items_dict = [item.model_dump() for item in payload.items]
        output = export_programacion_xlsx(str(template_path), items_dict)
        export_filename = f"Programacion_Lab_{date.today().strftime('%Y%m%d')}.xlsx"
        
        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={export_filename}"}
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")


@router.post("/export/comercial")
async def export_programacion_comercial(payload: ProgramacionExportRequest):
    """Export Programación COMERCIAL data to Excel."""
    template_path = _find_template("Template_Programacion_Comercial.xlsx")
    
    try:
        items_dict = [item.model_dump() for item in payload.items]
        output = export_programacion_comercial_xlsx(str(template_path), items_dict)
        export_filename = f"Programacion_Comercial_{date.today().strftime('%Y%m%d')}.xlsx"
        
        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={export_filename}"}
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")


@router.post("/export/administracion")
async def export_programacion_administracion(payload: ProgramacionExportRequest):
    """Export Programación ADMINISTRACIÓN data to Excel."""
    template_path = _find_template("Template_Programacion_Administracion.xlsx")
    
    try:
        items_dict = [item.model_dump() for item in payload.items]
        output = export_programacion_administracion_xlsx(str(template_path), items_dict)
        export_filename = f"Programacion_Administracion_{date.today().strftime('%Y%m%d')}.xlsx"
        
        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={export_filename}"}
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")

