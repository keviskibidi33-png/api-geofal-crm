"""
Router para el módulo de Humedad — ASTM D2216-19.
Endpoint para generar el Excel de Contenido de Humedad.
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from datetime import date

from .schemas import HumedadRequest
from .excel import generate_humedad_excel

router = APIRouter(prefix="/api/humedad", tags=["Laboratorio Humedad"])


@router.post("/excel")
async def generar_excel_humedad(payload: HumedadRequest):
    """
    Genera y descarga el Excel de Contenido de Humedad (ASTM D2216-19).
    
    Recibe los datos del ensayo y devuelve el archivo .xlsx rellenado
    sobre el template oficial Template_Humedad.xlsx.
    """
    try:
        excel_bytes = generate_humedad_excel(payload)

        filename = f"Humedad_{payload.numero_ot}_{date.today().strftime('%Y%m%d')}.xlsx"

        return Response(
            content=excel_bytes,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
            },
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=f"Template no encontrado: {e}")
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error generando Excel de Humedad: {str(e)}")
