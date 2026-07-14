import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import openpyxl
from app.modules.proctor.excel import generate_proctor_excel
from app.modules.proctor.schemas import ProctorRequest
from app.modules.humedad.excel import generate_humedad_excel
from app.modules.humedad.schemas import HumedadRequest
from app.modules.equi_arena.excel import generate_equi_arena_excel
from app.modules.equi_arena.schemas import EquiArenaRequest
from app.modules.llp.excel import generate_llp_excel
from app.modules.llp.schemas import LLPRequest
from app.modules.gran_suelo.excel import generate_gran_suelo_excel
from app.modules.gran_suelo.schemas import GranSueloRequest
from app.modules.cbr.excel import generate_cbr_excel
from app.modules.cbr.schemas import CBRRequest

def main():
    out_dir = ROOT / "suelos verifiacon"
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"Directorio de pruebas locales: {out_dir}")

    # 1. Proctor
    print("Generando test Proctor...")
    payload_proctor = ProctorRequest(
        muestra="PR-100-26",
        numero_ot="OT-PROCTOR-26",
        fecha_ensayo="2026/06/24",
        realizado_por="OPERADOR SUELOS",
        puntos=[
            {"prueba_numero": 1, "numero_capas": 5, "numero_golpes": 56, "masa_suelo_humedo_molde_a": 6120, "masa_molde_compactacion_b": 4250, "volumen_molde_compactacion_d": 944, "tara_numero": "T1", "masa_recipiente_suelo_humedo": 150.2, "masa_recipiente_suelo_seco_1": 138.5, "masa_recipiente_suelo_seco_2": 138.5, "masa_recipiente_suelo_seco_3_f": 138.5, "masa_recipiente": 30.1},
            {"prueba_numero": 2, "numero_capas": 5, "numero_golpes": 56, "masa_suelo_humedo_molde_a": 6250, "masa_molde_compactacion_b": 4250, "volumen_molde_compactacion_d": 944, "tara_numero": "T2", "masa_recipiente_suelo_humedo": 160.5, "masa_recipiente_suelo_seco_1": 145.2, "masa_recipiente_suelo_seco_2": 145.2, "masa_recipiente_suelo_seco_3_f": 145.2, "masa_recipiente": 30.2},
            {"prueba_numero": 3, "numero_capas": 5, "numero_golpes": 56, "masa_suelo_humedo_molde_a": 6310, "masa_molde_compactacion_b": 4250, "volumen_molde_compactacion_d": 944, "tara_numero": "T3", "masa_recipiente_suelo_humedo": 170.1, "masa_recipiente_suelo_seco_1": 150.8, "masa_recipiente_suelo_seco_2": 150.8, "masa_recipiente_suelo_seco_3_f": 150.8, "masa_recipiente": 30.3},
            {"prueba_numero": 4, "numero_capas": 5, "numero_golpes": 56, "masa_suelo_humedo_molde_a": 6280, "masa_molde_compactacion_b": 4250, "volumen_molde_compactacion_d": 944, "tara_numero": "T4", "masa_recipiente_suelo_humedo": 180.4, "masa_recipiente_suelo_seco_1": 155.6, "masa_recipiente_suelo_seco_2": 155.6, "masa_recipiente_suelo_seco_3_f": 155.6, "masa_recipiente": 30.4},
            {"prueba_numero": 5, "numero_capas": 5, "numero_golpes": 56, "masa_suelo_humedo_molde_a": 6210, "masa_molde_compactacion_b": 4250, "volumen_molde_compactacion_d": 944, "tara_numero": "T5", "masa_recipiente_suelo_humedo": 190.2, "masa_recipiente_suelo_seco_1": 160.2, "masa_recipiente_suelo_seco_2": 160.2, "masa_recipiente_suelo_seco_3_f": 160.2, "masa_recipiente": 30.5}
        ],
        tipo_muestra="SUELO SELECCIONADO",
        condicion_muestra="ALTERADA",
        tamano_maximo_particula_in="3/4\"",
        forma_particula="ANGULAR",
        clasificacion_sucs_visual="GP-GM",
        metodo_ensayo="C",
        metodo_preparacion="HUMEDO",
        tipo_apisonador="MANUAL",
        observaciones="Sin observaciones particulares en proctor.",
        tamiz_masa_retenida_g=[100, 200, 300, 400, 1000]
    )
    res_proctor = generate_proctor_excel(payload_proctor)
    (out_dir / "test_proctor.xlsx").write_bytes(res_proctor)

    # 2. Humedad
    print("Generando test Humedad...")
    payload_humedad = HumedadRequest(
        muestra="HM-101-26",
        numero_ot="OT-HUMEDAD-26",
        fecha_ensayo="2026/06/24",
        realizado_por="OPERADOR SUELOS",
        condicion_masa_menor="SI",
        condicion_capas="NO",
        condicion_temperatura="NO",
        condicion_excluido="NO",
        tipo_muestra="SUELO",
        condicion_muestra="NATURAL",
        tamano_maximo_particula="3/4\"",
        forma_particula="REDONDEADA",
        metodo_prueba="A",
        masa_recipiente_muestra_humeda=250.5,
        masa_recipiente_muestra_seca=220.1,
        masa_recipiente_muestra_seca_constante=220.1,
        masa_recipiente=35.2,
        numero_ensayo=1,
        recipiente_numero="R-20",
        equipo_balanza_01="BAL-01",
        equipo_balanza_001="BAL-02",
        equipo_horno="HOR-03",
        observaciones="Humedad uniforme.",
        revisado_por="REVISOR GEOFAL",
        revisado_fecha="2026/06/24",
        aprobado_por="Jefe de Laboratorio",
        aprobado_fecha="2026/06/24"
    )
    res_humedad = generate_humedad_excel(payload_humedad)
    (out_dir / "test_humedad.xlsx").write_bytes(res_humedad)

    # 3. Equivalente de Arena
    print("Generando test Equivalente de Arena...")
    payload_ea = EquiArenaRequest(
        muestra="EA-102-26",
        numero_ot="OT-ARENA-26",
        fecha_ensayo="2026/06/24",
        realizado_por="OPERADOR SUELOS",
        tipo_muestra="SUELO",
        metodo_agitacion="MECANICO",
        preparacion_muestra="PROCEDIMIENTO A",
        temperatura_solucion_c=22.5,
        masa_4_medidas_g=120.0,
        cronometro_entrada_saturacion_hmin=["10:00", "10:20", "10:40"],
        cronometro_salida_saturacion_hmin=["10:10", "10:30", "10:50"],
        tiempo_saturacion_min=[10, 10, 10],
        tiempo_agitacion_seg=[45, 45, 45],
        cronometro_entrada_decantacion_hmin=["11:00", "11:20", "11:40"],
        cronometro_salida_decantacion_hmin=["11:20", "11:40", "12:00"],
        tiempo_decantacion_min=[20, 20, 20],
        lectura_arcilla_in=[4.2, 4.3, 4.1],
        lectura_arena_in=[3.5, 3.6, 3.4],
        equivalente_arena_promedio_pct=84.0,
        equipo_balanza_01g_codigo="BAL-01g",
        equipo_horno_110_codigo="HOR-110",
        equipo_equivalente_arena_codigo="EQ-EA",
        equipo_agitador_ea_codigo="AG-EA",
        equipo_termometro_codigo="TERM-01",
        equipo_tamiz_no4_codigo="TAM-No4",
        observaciones="Equivalente óptimo.",
        revisado_por="REVISOR GEOFAL",
        revisado_fecha="2026/06/24",
        aprobado_por="Jefe de Laboratorio",
        aprobado_fecha="2026/06/24"
    )
    res_ea = generate_equi_arena_excel(payload_ea)
    (out_dir / "test_equivalente_arena.xlsx").write_bytes(res_ea)

    # 4. LLP
    print("Generando test LLP...")
    payload_llp = LLPRequest(
        muestra="LLP-103-26",
        numero_ot="OT-LLP-26",
        fecha_ensayo="2026/06/24",
        realizado_por="OPERADOR SUELOS",
        metodo_ensayo_limite_liquido="MULTIPUNTO",
        herramienta_ranurado_limite_liquido="PLASTICO",
        dispositivo_limite_liquido="MECANICO",
        metodo_laminacion_limite_plastico="MANUAL",
        contenido_humedad_muestra_inicial_pct=24.5,
        proceso_seleccion_muestra="HUMEDO",
        metodo_preparacion_muestra="SECADO AL AIRE",
        tamano_maximo_visual_in="No.40",
        porcentaje_retenido_tamiz_40_pct=1.2,
        forma_particula="REDONDEADA",
        tipo_muestra="LIMO",
        condicion_muestra="ALTERADO",
        puntos=[
            {"recipiente_numero": "C1", "numero_golpes": 28, "masa_recipiente_suelo_humedo": 45.2, "masa_recipiente_suelo_seco": 38.5, "masa_recipiente_suelo_seco_1": 38.5, "masa_recipiente": 15.2},
            {"recipiente_numero": "C2", "numero_golpes": 22, "masa_recipiente_suelo_humedo": 48.9, "masa_recipiente_suelo_seco": 41.2, "masa_recipiente_suelo_seco_1": 41.2, "masa_recipiente": 15.3},
            {"recipiente_numero": "C3", "numero_golpes": 16, "masa_recipiente_suelo_humedo": 52.4, "masa_recipiente_suelo_seco": 43.6, "masa_recipiente_suelo_seco_1": 43.6, "masa_recipiente": 15.4},
            {"recipiente_numero": "P1", "masa_recipiente_suelo_humedo": 35.6, "masa_recipiente_suelo_seco": 32.1, "masa_recipiente_suelo_seco_1": 32.1, "masa_recipiente": 15.1},
            {"recipiente_numero": "P2", "masa_recipiente_suelo_humedo": 36.1, "masa_recipiente_suelo_seco": 32.4, "masa_recipiente_suelo_seco_1": 32.4, "masa_recipiente": 15.2}
        ],
        balanza_001g_codigo="BAL-001g",
        horno_110_codigo="HOR-110",
        copa_casagrande_codigo="COPA-01",
        ranurador_codigo="RAN-01",
        observaciones="Límites normales.",
        revisado_por="REVISOR GEOFAL",
        revisado_fecha="2026/06/24",
        aprobado_por="Jefe de Laboratorio",
        aprobado_fecha="2026/06/24"
    )
    res_llp = generate_llp_excel(payload_llp)
    (out_dir / "test_llp.xlsx").write_bytes(res_llp)

    # 5. GranSuelo
    print("Generando test GranSuelo...")
    payload_gran = GranSueloRequest(
        muestra="GS-104-26",
        numero_ot="OT-GRAN-26",
        fecha_ensayo="2026/06/24",
        realizado_por="OPERADOR SUELOS",
        descripcion_turbo_organico="NO ORG",
        metodo_prueba="B",
        tamizado_tipo="FRACCIONADO",
        metodo_muestreo="SECADO AL AIRE",
        tipo_muestra="GRAVA ARCILLOSA",
        condicion_muestra="ALTERADO",
        tamano_maximo_particula_in="1\"",
        forma_particula="ANGULAR",
        masa_seca_porcion_gruesa_cp_md_g=450.5,
        masa_humeda_porcion_fina_fp_mm_g=150.2,
        masa_seca_porcion_fina_fp_md_g=135.4,
        masa_seca_muestra_s_md_g=585.9,
        masa_seca_global_g=2500.0,
        subespecie_masa_humeda_g=500.0,
        subespecie_masa_seca_g=450.0,
        contenido_agua_wfp_pct=11.1,
        masa_porcion_gruesa_lavada_cpwmd_g=430.2,
        masa_retenida_plato_cpmrpan_g=20.3,
        perdida_cpl_pct=0.05,
        masa_subespecimen_lavado_fina_g=390.5,
        clasificacion_visual_simbolo="GC",
        clasificacion_visual_nombre="GRAVA ARCILLOSA CON ARENA",
        excluyo_material="NO",
        excluyo_material_descripcion="-",
        problema_muestra="NO",
        problema_descripcion="-",
        proceso_dispersion="MANUAL",
        masa_retenida_primer_tamiz_g=0.0,
        masa_retenida_tamiz_g=[0, 50, 100, 150, 200, 250, 300, 100, 120, 140, 160, 180, 200, 220, 250],
        balanza_01g_codigo="BAL-01",
        horno_110_codigo="HOR-110",
        observaciones="Lavado limpio.",
        revisado_por="REVISOR GEOFAL",
        revisado_fecha="2026/06/24",
        aprobado_por="Jefe de Laboratorio",
        aprobado_fecha="2026/06/24"
    )
    res_gran = generate_gran_suelo_excel(payload_gran)
    (out_dir / "test_gran_suelo.xlsx").write_bytes(res_gran)

    # 6. CBR
    print("Generando test CBR...")
    payload_cbr = CBRRequest(
        muestra="CBR-105-26",
        numero_ot="OT-CBR-26",
        fecha_ensayo="2026/06/24",
        realizado_por="OPERADOR SUELOS",
        sobretamano_porcentaje=5.5,
        masa_grava_adicionada_g=250.0,
        condicion_muestra_saturado="SI",
        condicion_muestra_sin_saturar="NO",
        maxima_densidad_seca=2.120,
        optimo_contenido_humedad=8.5,
        temperatura_inicial_c=20.0,
        temperatura_final_c=21.5,
        tamano_maximo_visual_in="3/4\"",
        descripcion_muestra_astm="A-1-a",
        golpes_por_especimen=[56, 25, 12],
        codigo_molde_por_especimen=["M1", "M2", "M3"],
        temperatura_inicio_c_por_columna=[20.0]*6,
        temperatura_final_c_por_columna=[21.0]*6,
        masa_molde_suelo_g_por_columna=[7200, 7150, 7100, 7050, 7000, 6950],
        codigo_tara_por_columna=["T1", "T2", "T3", "T4", "T5", "T6"],
        masa_tara_g_por_columna=[50, 51, 52, 53, 54, 55],
        masa_suelo_humedo_tara_g_por_columna=[150, 152, 154, 156, 158, 160],
        masa_suelo_seco_tara_g_por_columna=[142, 143, 145, 146, 148, 149],
        masa_suelo_seco_tara_constante_g_por_columna=[142, 143, 145, 146, 148, 149],
        lecturas_penetracion=[
            {'tension_standard': 10.0, 'lectura_dial_esp_01': 1.2, 'lectura_dial_esp_02': 1.0, 'lectura_dial_esp_03': 0.8}
            for _ in range(12)
        ],
        hinchamiento=[
            {'fecha': '2026/06/24', 'hora': '08:00', 'esp_01': 0.05, 'esp_02': 0.04, 'esp_03': 0.03}
            for _ in range(5)
        ],
        profundidad_hendidura_mm_por_celda=[2.5, 2.5, 2.5],
        profundidad_hendidura_mm=2.5,
        equipo_cbr="CBR-EQ",
        equipo_dial_deformacion="DIAL-DEF",
        equipo_dial_expansion="DIAL-EXP",
        equipo_horno_110="HOR-110",
        equipo_pison="PISON-01",
        equipo_balanza_1g="BAL-1g",
        equipo_balanza_01g="BAL-01g",
        observaciones="CBR de buena capacidad soporte.",
        revisado_por="REVISOR GEOFAL",
        revisado_fecha="2026/06/24",
        aprobado_por="Jefe de Laboratorio",
        aprobado_fecha="2026/06/24"
    )
    res_cbr = generate_cbr_excel(payload_cbr)
    (out_dir / "test_cbr.xlsx").write_bytes(res_cbr)

    # 7. Densidad (SU06)
    print("Generando test Densidad (SU06)...")
    wb = openpyxl.load_workbook("app/templates/informes/Densidad/1-INF.-N-001-26-SU06-DEN-V05.xlsx")
    ws_den = wb["DENSIDAD NATURAL EMS"]
    
    # Escribir metadatos de prueba en la plantilla directamente para validación visual
    ws_den["C10"] = "CLIENTE PRUEBA LOCAL"
    ws_den["K11"] = "OT-DEN-26"
    
    wb.save(out_dir / "test_densidad.xlsx")

    print("[COMPLETED] Todos los 7 informes de prueba han sido generados en 'suelos verifiacon/'")

if __name__ == "__main__":
    main()
