import os, sys
from datetime import datetime

print("=== INICIANDO VALIDACIÓN DE PLANTILLAS Y GENERACIÓN EXCEL ===")

# 1. Validar existencia física de templates
from app.modules.common.excel_xml import find_template_path

templates_to_test = [
    ("OT Concreto", "OT/OT-CONCRETO/OT-CONCRETO-Geofal.xlsx"),
    ("OT Muestras", "OT/OT-MUESTRAS/OT-MUESTRAS-Geofal.xlsx"),
    ("Recepción Concreto", "Recepciones/F-LEM-P-01.02 V07 RECEPCIÓN CONCRETO.xlsx"),
    ("Recepción Muestras", "Recepciones/F-LEM-P-01.13 V01 RECEP DE MUESTRA.XLSX"),
]

for name, rel_path in templates_to_test:
    resolved = find_template_path(rel_path)
    exists = os.path.exists(resolved)
    print(f"[{'OK' if exists else 'ERR'}] {name}: {resolved} (Existe: {exists})")
    assert exists, f"Template {name} no encontrado en {resolved}"

# 2. Validar generación de OT Muestras
from app.modules.ot.models import OrdenTrabajo
from app.modules.ot.excel import generar_excel_ot_su_ag, generar_excel_ot_concreto

ot_sample = OrdenTrabajo(
    numero_ot="OT-2079-26",
    numero_recepcion="2075-26",
    cliente="R PROYECTOS S.A.C",
    proyecto="Vial Alterno o Base de Rescate",
    fecha_recepcion="2026-08-21",
    inicio_programado="2026-08-21",
    fin_programado="2026-08-24",
    ot_aperturada_por="BETZABETH SARAVIA",
    ot_designada_a="EDWIN HUAMAN",
    items=[
        {
            "item": 1,
            "codigo_muestra": "245-AG-26",
            "identificacion": "MUESTRA 1",
            "procedencia": "CANTERA",
            "cantera": "CARRASCO",
            "cantidad_kg": "50 KG",
            "codigo_ensayo": "AG01",
            "descripcion": "ANALISIS GRANULOMETRICO POR TAMIZADO",
            "norma": "MTC E 204",
            "cantidad": 1
        }
    ]
)

try:
    buf_ot_muestras = generar_excel_ot_su_ag(ot_sample)
    size_ot_m = len(buf_ot_muestras.getvalue())
    print(f"[OK] Generar Excel OT Muestras exitoso! Tamaño: {size_ot_m} bytes")
except Exception as e:
    print(f"[ERR] Error generando OT Muestras: {e}")
    raise

# 3. Validar generación de OT Concreto
ot_concreto = OrdenTrabajo(
    numero_ot="OT-1980-26",
    numero_recepcion="1980-26",
    cliente="CLIENTE CONCRETO S.A.",
    proyecto="PROYECTO EDIFICIO",
    fecha_recepcion="2026-08-21",
    inicio_programado="2026-08-21",
    fin_programado="2026-08-28",
    ot_aperturada_por="BETZABETH SARAVIA",
    ot_designada_a="INGENIERO LAB",
    items=[
        {
            "item": 1,
            "codigo_muestra": "15334-CO-26",
            "descripcion": "COMPRESION PROBETAS ASTM C39/C39M",
            "cantidad": 1,
            "elemento": "COLUMNA",
            "fecha_rotura": "2026-08-28",
            "densidad": "SI",
            "edad": 7,
            "fc_kg_cm2": 280
        }
    ]
)

try:
    buf_ot_concreto = generar_excel_ot_concreto(ot_concreto)
    size_ot_c = len(buf_ot_concreto.getvalue())
    print(f"[OK] Generar Excel OT Concreto exitoso! Tamaño: {size_ot_c} bytes")
except Exception as e:
    print(f"[ERR] Error generando OT Concreto: {e}")
    raise

# 4. Validar generación de Recepción Muestras (F-LEM-P-01.13)
from app.modules.recepcion.models import RecepcionMuestra, MuestraConcreto
from app.modules.recepcion.excel import ExcelLogic

class DummyMuestra:
    def __init__(self, item_numero, identificacion, codigo_lem, procedencia, cantera, cantidad, codigo_ensayo, ensayos_req, norma_req, ensayos_json=None):
        self.item_numero = item_numero
        self.identificacion_muestra = identificacion
        self.codigo_muestra_lem = codigo_lem
        self.procedencia = procedencia
        self.cantera = cantera
        self.cantidad = cantidad
        self.tamano_peso = cantidad
        self.codigo_ensayo = codigo_ensayo
        self.ensayos_requeridos = ensayos_req
        self.norma_requerida = norma_req
        self.ensayos_json = ensayos_json
        self.descripcion_muestra = ensayos_req
        self.fecha_moldeo = ""
        self.fecha_rotura = ""
        self.edad = None
        self.fc_kg_cm2 = None
        self.elemento = "-"
        self.densidad = "-"
        self.status_ensayo = "-"
        self.status_entrega = "-"
        self.fecha_entrega = "-"

    @property
    def ensayos_lista(self):
        import json
        if self.ensayos_json:
            try:
                return json.loads(self.ensayos_json)
            except Exception:
                pass
        return [{"codigo": self.codigo_ensayo, "descripcion": self.ensayos_requeridos, "norma": self.norma_requerida}]

rec_sample = RecepcionMuestra(
    numero_recepcion="2075-26",
    numero_ot="2079-26",
    numero_cotizacion="1799-26",
    cliente="R PROYECTOS S.A.C",
    proyecto="Vial Alterno o Base de Rescate",
    ubicacion="AEROPUERTO JORGE CHAVEZ-CALLAO",
    domicilio_legal="Calle Anicota N 106",
    solicitante="R PROYECTOS S.A.C",
    domicilio_solicitante="Calle Anicota N 106",
    ruc="20601234567",
    persona_contacto="DIEGO LAZO R.",
    email="contacto@rproyectos.pe",
    telefono="999888777",
    fecha_recepcion=datetime(2026, 8, 21),
    fecha_estimada_culminacion=datetime(2026, 8, 24),
    emision_digital=True,
    emision_fisica=False,
    entregado_por="DIEGO LAZO R. / ALEX VICENTE J.",
    recibido_por="BETZABETH SARAVIA",
    tipo_recepcion="SUELO_AGREGADO"
)
rec_sample.muestras = [
    MuestraConcreto(
        item_numero=1,
        identificacion_muestra="1 MUESTRA DE AFIRMADO",
        codigo_muestra_lem="245-AG-26",
        procedencia="CANTERA",
        cantera="CARRASCO",
        cantidad="50 KG",
        codigo_ensayo="AG01",
        ensayos_requeridos="ANALISIS GRANULOMETRICO POR TAMIZADO",
        norma_requerida="MTC E 204",
        ensayos_json='[{"codigo":"AG01","descripcion":"ANALISIS GRANULOMETRICO POR TAMIZADO","norma":"MTC E 204"}]'
    )
]

try:
    excel_logic = ExcelLogic()
    rec_excel_bytes = excel_logic.generar_excel_recepcion(rec_sample)
    print(f"[OK] Generar Excel Recepción Muestras exitoso! Tamaño: {len(rec_excel_bytes)} bytes")
except Exception as e:
    print(f"[ERR] Error generando Recepción Muestras: {e}")
    raise

# 5. Validar tipos alternativos que mapean a Recepción Muestras (ROCA, ALBANILERIA, AGUA)
for t in ["ROCA", "ALBANILERIA", "AGUA"]:
    rec_sample.tipo_recepcion = t
    try:
        t_bytes = excel_logic.generar_excel_recepcion(rec_sample)
        print(f"[OK] Generar Excel Recepción tipo {t} exitoso! Tamaño: {len(t_bytes)} bytes")
    except Exception as e:
        print(f"[ERR] Error generando tipo {t}: {e}")
        raise

print("\n=== TODAS LAS PRUEBAS DE PLANTILLAS Y GENERACIÓN PASARON EXITOSAMENTE ===")
