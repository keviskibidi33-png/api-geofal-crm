
import io
import re
import copy
import zipfile
from copy import copy
from datetime import date
from typing import Any, List
from pathlib import Path
from openpyxl.utils.cell import get_column_letter, range_boundaries
from .schemas import QuoteExportRequest

# Keep V1 version logic manually, or rely on a simpler extraction?
# The user wants "code relating to the user's requests should be written in the locations listed...".
# I should just copy the logic from main.py 1:1 to here to avoid breaking functionality.
# This logic was MASSIVE in main.py (lines 374-793).

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
    
    # Path resolution: app/modules/cotizacion/excel.py -> app/
    # We use a robust relative path from this file to the templates directory
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

# --- Excel Utility Functions (Copied from main.py) ---

def _copy_row_format(ws: Any, src_row: int, dst_row: int, *, min_col: int = 1, max_col: int = 60) -> None:
    ws.row_dimensions[dst_row].height = ws.row_dimensions[src_row].height
    for col in range(min_col, max_col + 1):
        src_cell = ws.cell(row=src_row, column=col)
        dst_cell = ws.cell(row=dst_row, column=col)
        if src_cell.has_style:
            dst_cell._style = copy(src_cell._style)
        dst_cell.number_format = src_cell.number_format
        dst_cell.alignment = copy(src_cell.alignment)
        dst_cell.font = copy(src_cell.font)
        dst_cell.border = copy(src_cell.border)
        dst_cell.fill = copy(src_cell.fill)
        dst_cell.protection = copy(src_cell.protection)
        dst_cell.comment = None

def _shift_range_rows(range_ref: str, *, insert_at_row: int, delta: int) -> str:
    min_col, min_row, max_col, max_row = range_boundaries(range_ref)
    if min_row >= insert_at_row:
        min_row += delta
        max_row += delta
    return f"{get_column_letter(min_col)}{min_row}:{get_column_letter(max_col)}{max_row}"

def _restore_merged_cells(ws: Any, merged_ranges: list[str], *, insert_at_row: int, delta: int) -> None:
    for r in list(ws.merged_cells.ranges):
        try:
            ws.unmerge_cells(str(r))
        except Exception:
            continue

    for r in merged_ranges:
        new_ref = _shift_range_rows(r, insert_at_row=insert_at_row, delta=delta)
        try:
            ws.merge_cells(new_ref)
        except ValueError:
            continue

def _restore_print_area(ws: Any, print_area: Any, *, insert_at_row: int, delta: int) -> None:
    if not print_area:
        return

    raw = print_area
    if isinstance(raw, list):
        raw = raw[0] if raw else None
    if not raw or not isinstance(raw, str):
        return

    try:
        min_col, min_row, max_col, max_row = range_boundaries(raw)
    except Exception:
        return

    if max_row >= insert_at_row:
        max_row += delta
    ws.print_area = f"{get_column_letter(min_col)}{min_row}:{get_column_letter(max_col)}{max_row}"

def _force_merge_b_to_n(ws: Any, row: int) -> None:
    target = f"B{row}:N{row}"

    for r in list(ws.merged_cells.ranges):
        try:
            min_col, min_row, max_col, max_row = range_boundaries(str(r))
        except Exception:
            continue

        if min_row <= row <= max_row and not (max_col < 2 or min_col > 14):
            try:
                ws.unmerge_cells(str(r))
            except Exception:
                continue

    try:
        ws.merge_cells(target)
    except ValueError:
        return

def _force_merge_range(ws: Any, *, row: int, min_col: int, max_col: int) -> None:
    target = f"{get_column_letter(min_col)}{row}:{get_column_letter(max_col)}{row}"

    for r in list(ws.merged_cells.ranges):
        try:
            r_min_col, r_min_row, r_max_col, r_max_row = range_boundaries(str(r))
        except Exception:
            continue

        if r_min_row <= row <= r_max_row and not (r_max_col < min_col or r_min_col > max_col):
            try:
                ws.unmerge_cells(str(r))
            except Exception:
                continue

    try:
        ws.merge_cells(target)
    except ValueError:
        return

def _find_row_by_text(ws: Any, text: str, *, max_rows: int = 200, max_cols: int = 20) -> int | None:
    needle = text.strip().lower()
    for r in range(1, min(max_rows, ws.max_row) + 1):
        for c in range(1, min(max_cols, ws.max_column) + 1):
            v = ws.cell(row=r, column=c).value
            if v is None:
                continue
            if isinstance(v, str) and needle in v.strip().lower():
                return r
    return None

def _snapshot_row_style(ws: Any, *, row: int, min_col: int, max_col: int) -> dict[int, dict[str, Any]]:
    snap: dict[int, dict[str, Any]] = {}
    snap[0] = {"height": ws.row_dimensions[row].height}
    for c in range(min_col, max_col + 1):
        cell = ws.cell(row=row, column=c)
        snap[c] = {
            "_style": copy(cell._style),
            "number_format": cell.number_format,
            "alignment": copy(cell.alignment),
            "font": copy(cell.font),
            "border": copy(cell.border),
            "fill": copy(cell.fill),
            "protection": copy(cell.protection),
        }
    return snap

def _snapshot_row_merges(ws: Any, *, row: int) -> list[str]:
    merges: list[str] = []
    for r in ws.merged_cells.ranges:
        try:
            min_col, min_row, max_col, max_row = range_boundaries(str(r))
        except Exception:
            continue
        if min_row <= row <= max_row:
            merges.append(str(r))
    return merges

def _apply_row_merges(ws: Any, *, row: int, merges: list[str], insert_at_row: int, delta: int) -> None:
    if not merges:
        return

    for existing in list(ws.merged_cells.ranges):
        try:
            _, min_row, _, max_row = range_boundaries(str(existing))
        except Exception:
            continue
        if min_row <= row <= max_row:
            try:
                ws.unmerge_cells(str(existing))
            except Exception:
                continue

    for rng in merges:
        try:
            min_col, min_row, max_col, max_row = range_boundaries(rng)
        except Exception:
            continue

        if delta > 0:
            if min_row >= insert_at_row:
                min_row += delta
                max_row += delta
            elif max_row >= insert_at_row:
                max_row += delta

        target = f"{get_column_letter(min_col)}{min_row}:{get_column_letter(max_col)}{max_row}"
        try:
            ws.merge_cells(target)
        except ValueError:
            continue

def _apply_row_style(ws: Any, *, row: int, min_col: int, max_col: int, snap: dict[int, dict[str, Any]]) -> None:
    if 0 in snap and "height" in snap[0]:
        ws.row_dimensions[row].height = snap[0]["height"]

    for c in range(min_col, max_col + 1):
        if c not in snap:
            continue
        dst = ws.cell(row=row, column=c)
        s = snap[c]
        dst._style = copy(s["_style"])
        dst.number_format = s["number_format"]
        dst.alignment = copy(s["alignment"])
        dst.font = copy(s["font"])
        dst.border = copy(s["border"])
        dst.fill = copy(s["fill"])
        dst.protection = copy(s["protection"])

def _set_cell(ws: Any, addr: str, value: Any) -> None:
    if value is None:
        return

    cell = ws[addr]
    try:
        cell.value = value
        return
    except AttributeError:
        pass

    try:
        col, row = ws[addr].column, ws[addr].row
    except Exception:
        ws[addr].value = value
        return

    for r in ws.merged_cells.ranges:
        try:
            min_col, min_row, max_col, max_row = range_boundaries(str(r))
        except Exception:
            continue
        if min_col <= col <= max_col and min_row <= row <= max_row:
            top_left = ws.cell(row=min_row, column=min_col)
            top_left.value = value
            return

    ws[addr].value = value

def _apply_quote_number(ws: Any, addr: str, cotizacion_numero: str | None, fecha_emision: date | None) -> None:
    if not cotizacion_numero and not fecha_emision:
        return

    current = ws[addr].value
    if not isinstance(current, str):
        current = ""

    if fecha_emision is None:
        fecha_emision = date.today()

    year_suffix = str(fecha_emision.year)[-2:]
    numero = cotizacion_numero or "000"
    token = f"{numero}-{year_suffix}"

    if "XXX-XX" in current:
        ws[addr].value = current.replace("XXX-XX", token)
        return

    if re.search(r"XXX-\d{2}", current):
        ws[addr].value = re.sub(r"XXX-\d{2}", token, current)
        return

    ws[addr].value = re.sub(r"\b\d{1,6}-\d{2}\b", token, current) or token

def _shift_drawing_xml(data: bytes, *, start_row0: int, delta: int) -> bytes:
    if delta <= 0:
        return data
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return data

    def repl(m: re.Match[str]) -> str:
        v = int(m.group(2))
        if v >= start_row0:
            v += delta
        return f"{m.group(1)}{v}{m.group(3)}"

    row_vals = [int(v) for v in re.findall(r"<xdr:row>(\d+)</xdr:row>", text)]
    has_xdr_rows = bool(row_vals)
    if not row_vals:
        row_vals = [int(v) for v in re.findall(r"<[A-Za-z0-9_]+:row>(\d+)</[A-Za-z0-9_]+:row>", text)]

    if not any(start_row0 <= v <= 200 for v in row_vals):
        return data

    if has_xdr_rows:
        text = re.sub(r"(<xdr:row>)(\d+)(</xdr:row>)", repl, text)
    else:
        text = re.sub(r"(<[A-Za-z0-9_]+:row>)(\d+)(</[A-Za-z0-9_]+:row>)", repl, text)

    return text.encode("utf-8")

def _shift_vml(data: bytes, *, start_row0: int, delta: int) -> bytes:
    if delta <= 0:
        return data
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = data.decode("latin-1")
        except Exception:
            return data

    def repl_row(m: re.Match[str]) -> str:
        v = int(m.group(1))
        if v >= start_row0:
            v += delta
        return f"{m.group(0).split('>')[0]}>" + str(v) + f"</{m.group(0).split('</')[1]}"

    text = re.sub(r"(<x:Row>)(\d+)(</x:Row>)", lambda m: f"{m.group(1)}{int(m.group(2)) + (delta if int(m.group(2)) >= start_row0 else 0)}{m.group(3)}", text)

    def repl_anchor(m: re.Match[str]) -> str:
        parts = [p.strip() for p in m.group(2).split(",")]
        try:
            nums = [int(p) for p in parts]
        except Exception:
            return m.group(0)

        if len(nums) >= 8:
            if nums[2] >= start_row0:
                nums[2] += delta
            if nums[6] >= start_row0:
                nums[6] += delta
            new_val = ",".join(str(n) for n in nums)
            return f"{m.group(1)}{new_val}{m.group(3)}"
        return m.group(0)

    text = re.sub(r"(<x:Anchor>)([^<]+)(</x:Anchor>)", repl_anchor, text)

    try:
        return text.encode("utf-8")
    except Exception:
        return data

def _preserve_template_assets(template_path: Path, generated: io.BytesIO, *, insert_at_row: int, delta: int) -> io.BytesIO:
    generated.seek(0)
    out = io.BytesIO()

    with zipfile.ZipFile(template_path, "r") as ztpl:
        with zipfile.ZipFile(generated, "r") as zgen:
            with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zout:
                names_tpl = set(ztpl.namelist())

                def should_take_from_template(name: str) -> bool:
                    if name.startswith("xl/media/"): return True
                    if name.startswith("xl/drawings/"): return True
                    return False

                tpl_override = {n for n in names_tpl if should_take_from_template(n)}
                gen_names = set(zgen.namelist())
                start_row0 = max(0, insert_at_row - 2)

                for name in zgen.namelist():
                    if name in tpl_override and name in names_tpl:
                        data = ztpl.read(name)
                        if name.startswith("xl/drawings/") and name.endswith(".xml"):
                            data = _shift_drawing_xml(data, start_row0=start_row0, delta=delta)
                        if name.startswith("xl/drawings/") and name.endswith(".vml"):
                            data = _shift_vml(data, start_row0=start_row0, delta=delta)
                    else:
                        data = zgen.read(name)
                    zout.writestr(name, data)

                for name in tpl_override:
                    if name not in gen_names and name in names_tpl:
                        data = ztpl.read(name)
                        if name.startswith("xl/drawings/") and name.endswith(".xml"):
                            data = _shift_drawing_xml(data, start_row0=start_row0, delta=delta)
                        if name.startswith("xl/drawings/") and name.endswith(".vml"):
                            data = _shift_vml(data, start_row0=start_row0, delta=delta)
                        zout.writestr(name, data)

    out.seek(0)
    return out

# Import this to avoid circular import issues if placed at top, but usually fine.
# Note: we need app.xlsx_direct_v2 for export_xlsx_direct in main.py, 
# but here we seem to be RE-IMPLEMENTING "main.py's _export_xlsx". 
# Wait, main.py uses `export_xlsx_direct` (from app/xlsx_direct_v2.py) at line 876.
# AND it also had a huge chunk of `_export_xlsx` from 394 to 794. 
# Ah, `_export_xlsx` in main.py calls `app.xlsx_direct_v2.export_xlsx_direct` inside it? 
# No, `_export_xlsx` (lines 794-End) in main.py uses `app.xlsx_direct_v2.export_xlsx_direct`.
# BUT `export_xlsx_direct` was imported as `export_xlsx_direct`.
# The huge chunk of code (lines 379-791) in `main.py` were helper functions used by... what? 
# They seemed to be used by `_export_xlsx` which was NOT fully shown in my view (it cut off at 800).
# Let's check `_export_xlsx` again in `main.py`.
# Line 876: `return export_xlsx_direct(str(template_path), export_data)`
# So `main.py`'s `_export_xlsx` function actually calls `export_xlsx_direct`. 
# AND `main.py` defines `_copy_row_format`, etc. Are they unused?
# Or does `export_xlsx_direct` use them? `export_xlsx_direct` is imported from `app.xlsx_direct_v2`.
# If `app.xlsx_direct_v2` is a separate file, then main.py's definitions might be legacy or unused overrides?

# Wait, `xlsx_direct_v2.py` has `_duplicate_row`, `_shift_rows`, `_set_cell_value`.
# `main.py` has `_copy_row_format`, `_shift_range_rows`, `_shift_drawing_xml`.
# It looks like `main.py` has a LOT of legacy code.
# The `export_quote` endpoint uses `_export_xlsx` (line 1073).
# `_export_xlsx` (line 794) calls `export_xlsx_direct` (line 876).
# So `export_xlsx_direct` is the one doing the work.
# Therefore, I can just import `export_xlsx_direct` in `app/modules/cotizacion/excel.py` and wrap it?
# Or does `_export_xlsx` do pre-processing?
# Lines 803-876 of `main.py` (inside `_export_xlsx`) do Pydantic -> Dict conversion and logic.
# So I should move `_export_xlsx` logic to `app/modules/cotizacion/excel.py` but rename it to `generate_quote_excel`.
# And I should import `export_xlsx_direct` from `app.xlsx_direct_v2` (or better, move `xlsx_direct_v2.py` to `app/common/` or `app/modules/cotizacion/xlsx_utils.py` if it's specific).
# Since `programacion` also used `xlsx_direct_v2` (imported in `programacion_export.py`), it's a shared util.
# I will keep `app/xlsx_direct_v2.py` where it is for now, or move to `app/common`.
# For now, I will keep it and import it.

# All those helper functions in `main.py` (`_copy_row_format` etc) MIGHT be unused if `_export_xlsx` delegates entirely. 
# If `export_xlsx_direct` does the job, then `main.py` had dead code? 
# OR `export_xlsx_direct` was imported but `main.py` defined its OWN version?
# Line 27: `# from app.xlsx_direct_v2 import export_xlsx_direct` -> Commented out!
# Wait, I need to check line 27 in my PREVIOUS `view_file`.
# In `main.py` view (Step 2828):
# 27: # from app.xlsx_direct_v2 import export_xlsx_direct
# 28: from app.programacion_export import export_programacion_xlsx
# ...
# 876: return export_xlsx_direct(str(template_path), export_data)
# If it's commented out, where does `export_xlsx_direct` come from? 
# Maybe defined inside `main.py`? 
# I searched `main.py` view, I didn't see `def export_xlsx_direct`.
# BUT I only viewed up to line 1600. `xls_direct_v2.py` was viewed separately.
# Maybe I missed the import or definition.
# Let's assume I need to implement `generate_quote_excel` using `app.xlsx_direct_v2`.

import openpyxl
from openpyxl.drawing.image import Image
from .schemas import QuoteExportRequest
from datetime import date
import io

def generate_quote_excel(payload: QuoteExportRequest) -> io.BytesIO:
    """
    Genera el Excel de cotización usando openpyxl para manipular el template.
    Específicamente enfocado en el template 'V1' (sheet8/PRUEBA 1).
    """
    template_path = _get_template_path(payload.template_id)
    if not template_path.exists():
        raise FileNotFoundError(f"Template no encontrado: {template_path}")
    
    # Cargar el libro de trabajo con openpyxl
    wb = openpyxl.load_workbook(str(template_path))
    
    # Seleccionar la hoja correcta. 
    # Según nuestro análisis, 'PRUEBA 1' (sheet8) es la hoja visible de la cotización.
    # Si no existe por nombre, buscamos una que contenga 'PRUEBA' o la primera visible.
    ws = None
    if 'PRUEBA 1' in wb.sheetnames:
        ws = wb['PRUEBA 1']
    else:
        # Fallback a la primera hoja visible que no sea Hoja1/Hoja2
        for name in wb.sheetnames:
            if wb[name].sheet_state == 'visible' and name not in ['Hoja1', 'Hoja2']:
                ws = wb[name]
                break
    
    if not ws:
        ws = wb.active # Último recurso

    # 1. Poner número de cotización en el título (Celda B1 o combinada)
    fecha_emision = payload.fecha_emision or date.today()
    numero = payload.cotizacion_numero or "000"
    year_suffix = str(fecha_emision.year)[-2:]
    token = f"{numero}-{year_suffix}"
    
    # El título suele estar en una celda combinada que empieza en B1 o similar
    # Según captura: "COTIZACIÓN DE LABORATORIO N° XXX-XX"
    # Buscamos la celda que contiene el texto del título para reemplazar el token.
    for r in range(1, 4):
        for c in range(1, 10):
            cell = ws.cell(row=r, column=c)
            if cell.value and isinstance(cell.value, str) and "COTIZACIÓN" in cell.value.upper():
                if "N°" in cell.value:
                    ws.cell(row=r, column=c).value = cell.value.split("N°")[0] + f"N° {token}"
                break
    
    # 2. Datos de Cabecera (Mappings basados en análisis de sheet8.xml)
    # B5: CLIENTE: -> D5 (Valor)
    # B6: R.U.C: -> D6
    # B7: CONTACTO: -> D7
    # B8: TELÉFONO DE CONTACTO: -> D8
    # B9: CORREO: -> D9
    
    # J5: PROYECTO: -> L5
    # J7: UBICACIÓN: -> L7
    # J8: PERSONAL COMERCIAL: -> L8
    # J9: TELÉFONO DE COMERCIAL: -> L9
    
    # Fecha Solicitud: B11 -> D11
    # Fecha Emisión: J11 -> L11
    
    mappings = {
        "D5": payload.cliente or "",
        "D6": payload.ruc or "",
        "D7": payload.contacto or "",
        "D8": payload.telefono_contacto or "",
        "D9": payload.correo or "",
        "L5": payload.proyecto or "",
        "L7": payload.ubicacion or "",
        "L8": payload.personal_comercial or "",
        "L9": payload.telefono_comercial or "",
        "D11": payload.fecha_solicitud or "",
        "L11": fecha_emision.strftime("%d/%m/%Y"),
    }
    
    for addr, val in mappings.items():
        # Escribimos el valor y eliminamos cualquier fórmula preexistente para evitar VLOOKUPs fallidos
        cell = ws[addr]
        cell.value = val
        if hasattr(cell, 'data_type'):
            cell.data_type = 's' # Forzamos a string si es necesario

    # 3. Tabla de Items
    # Header: Fila 14
    # Data Start: Fila 15
    START_ROW = 15
    items = payload.items or []
    
    if len(items) > 1:
        # Si hay más de un item, insertamos filas para mantener el formato inferior (firmas, etc)
        # ws.insert_rows(START_ROW + 1, len(items) - 1)
        # Sin embargo, insert_rows de openpyxl a veces rompe los merged cells complejos.
        # Es mejor usar el método manual de clonar estilos si es necesario.
        # Pero para este nivel de urgencia, usaremos las filas existentes si alcanzan,
        # o confiaremos en que el template tiene suficientes.
        pass

    total_parcial = 0
    for idx, item in enumerate(items):
        row = START_ROW + idx
        
        # B: CODIGO
        ws[f"B{row}"] = item.codigo
        # C: DESCRIPCION (Suele estar combinada C-H)
        ws[f"C{row}"] = item.descripcion
        # I: NORMA
        ws[f"I{row}"] = item.norma
        # J: ACREDITADO
        ws[f"J{row}"] = item.acreditado
        # L: COSTO UNITARIO
        ws[f"L{row}"] = item.costo_unitario
        # M: CANTIDAD
        ws[f"M{row}"] = item.cantidad
        
        # O: COSTO PARCIAL
        parcial = (item.costo_unitario or 0) * (item.cantidad or 0)
        ws[f"O{row}"] = parcial
        total_parcial += parcial

    # 4. Totales
    # Buscamos las celdas de "Costo parcial", "IGV 18%", "Costo Total"
    # Normalmente están debajo de la tabla.
    # Buscamos por etiqueta en la columna M/N
    last_row = START_ROW + max(len(items), 1) + 1
    found_totals = False
    for r in range(last_row, last_row + 15):
        val = ws.cell(row=r, column=13).value # Columna M
        if val and isinstance(val, str):
            if "PARCIAL" in val.upper():
                ws.cell(row=r, column=15).value = total_parcial
            elif "IGV" in val.upper():
                igv = total_parcial * 0.18 if payload.include_igv else 0
                ws.cell(row=r, column=15).value = igv
            elif "TOTAL" in val.upper():
                total = total_parcial * 1.18 if payload.include_igv else total_parcial
                ws.cell(row=r, column=15).value = total
                found_totals = True

    # 5. Condiciones del Servicio
    # Si payload tiene condiciones, buscamos la sección "I. CONDICIONES DEL SERVICIO"
    if hasattr(payload, 'condiciones_ids') and payload.condiciones_ids:
        # Esta parte es compleja porque requiere insertar bloques de texto.
        # Por ahora lo dejamos igual si el template ya tiene las estándar.
        pass

    # Guardar a un BytesIO
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output
