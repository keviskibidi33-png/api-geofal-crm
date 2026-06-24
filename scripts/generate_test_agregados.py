import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.modules.ge_fino.excel import generate_ge_fino_excel
from app.modules.ge_fino.schemas import GeFinoRequest

from app.modules.gran_agregado.excel import generate_gran_agregado_excel
from app.modules.gran_agregado.schemas import GranAgregadoRequest

from app.modules.cont_humedad.excel import generate_cont_humedad_excel
from app.modules.cont_humedad.schemas import ContHumedadRequest

from app.modules.peso_unitario.excel import generate_peso_unitario_excel
from app.modules.peso_unitario.schemas import PesoUnitarioRequest

from app.modules.tamiz.excel import generate_tamiz_excel
from app.modules.tamiz.schemas import TamizRequest

from app.modules.abrass.excel import generate_abrass_excel
from app.modules.abrass.schemas import AbrassRequest

from app.modules.ge_grueso.excel import generate_ge_grueso_excel
from app.modules.ge_grueso.schemas import GeGruesoRequest

from app.modules.planas.excel import generate_planas_excel
from app.modules.planas.schemas import PlanasRequest, PlanasGradacionRow, PlanasMetodoRow

from app.modules.caras.excel import generate_caras_excel
from app.modules.caras.schemas import CarasRequest

from app.modules.abra.excel import generate_abra_excel
from app.modules.abra.schemas import AbraRequest

def main():
    out_dir = ROOT / "suelos verifiacon" / "informes agregados"
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"Directorio de destino: {out_dir}")

    # 1. Ge Fino
    print("Generando Ge Fino...")
    fino_req = GeFinoRequest(
        muestra="147-AG-26",
        numero_ot="OT-FINO-26",
        fecha_ensayo="2026/06/24",
        realizado_por="ANDRES SANCHEZ",
        revisado_por="FABIAN LA ROSA",
        revisado_fecha="2026/06/24",
        aprobado_por="IRMA COAQUIRA",
        aprobado_fecha="2026/06/24",
        masa_humeda_g=500.0,
        masa_seca_g=490.0,
        masa_seca_constante_g=490.0,
        fecha_hora_inmersion="2026/06/24 10:00",
        fecha_hora_salida_inmersion="2026/06/24 12:00",
        temp_picnometro_contenido_c=20.0,
        temp_durante_calibracion_c=22.0,
        valor_s_g=500.0,
        valor_c_g=650.0,
        valor_b_g=950.0,
        valor_d_g="-",
        valor_e_g=2.63,
        valor_f_g=2.68,
        valor_g_g=2.70,
        valor_a_g=490.0,
        densidad_relativa_od=2.63,
        densidad_relativa_ssd=2.68,
        densidad_relativa_aparente=2.70,
        absorcion_pct=2.04,
        seco_horno_110_si_no="SI"
    )
    (out_dir / "test_ge_fino.xlsx").write_bytes(generate_ge_fino_excel(fino_req))

    # 2. Gran Agregado
    print("Generando Gran Agregado...")
    gran_req = GranAgregadoRequest(
        muestra="147-AG-26",
        numero_ot="OT-GRAN-26",
        fecha_ensayo="2026/06/24",
        realizado_por="ANDRES SANCHEZ",
        revisado_por="FABIAN LA ROSA",
        revisado_fecha="2026/06/24",
        aprobado_por="IRMA COAQUIRA",
        aprobado_fecha="2026/06/24",
        tipo_muestra="AGREGADO GRUESO Y FINO",
        tamano_maximo_particula_visual_in="1\"",
        forma_particula="ANGULAR",
        masa_muestra_humeda_inicial_total_global_g=2500.0,
        masa_muestra_seca_global_g=2450.0,
        masa_muestra_seca_constante_global_g=2450.0,
        masa_muestra_seca_lavada_global_g=2400.0,
        masa_retenida_tamiz_g=[0.0, 50.0, 100.0, 200.0, 300.0, 400.0, 500.0, 300.0, 200.0, 150.0, 100.0, 50.0, 30.0, 20.0, 10.0, 5.0, 3.0, 2.0],
        masa_antes_tamizado_g=2400.0,
        masa_despues_tamizado_g=2395.0,
        error_tamizado_pct=0.21,
        balanza_01g_codigo="BAL-01",
        horno_codigo="HOR-110",
        observaciones="Granulometría limpia."
    )
    (out_dir / "test_gran_agregado.xlsx").write_bytes(generate_gran_agregado_excel(gran_req))

    # 3. Cont Humedad
    print("Generando Cont Humedad Agregados...")
    ch_req = ContHumedadRequest(
        muestra="147-AG-26",
        numero_ot="OT-CH-26",
        fecha_ensayo="2026/06/24",
        realizado_por="ANDRES SANCHEZ",
        revisado_por="FABIAN LA ROSA",
        revisado_fecha="2026/06/24",
        aprobado_por="IRMA COAQUIRA",
        aprobado_fecha="2026/06/24",
        condicion_masa_menor="SI",
        condicion_capas="NO",
        condicion_temperatura="NO",
        condicion_excluido="NO",
        tipo_muestra="AGREGADO",
        condicion_muestra="NATURAL",
        tamano_maximo_muestra_visual_in="3/4\"",
        forma_particula="SUBANGULAR",
        metodo_prueba="A",
        masa_recipiente_muestra_humedo_g=1200.0,
        masa_recipiente_muestra_seco_g=1150.0,
        masa_recipiente_muestra_seco_constante_g=1150.0,
        masa_agua_g=50.0,
        masa_recipiente_g=150.0,
        masa_muestra_seco_g=1000.0,
        contenido_humedad_pct=5.0,
        numero_ensayo=1,
        recipiente_numero="R-01",
        balanza_01g_codigo="BAL-01",
        balanza_001g_codigo="BAL-001",
        horno_110c_codigo="HOR-110"
    )
    (out_dir / "test_cont_humedad.xlsx").write_bytes(generate_cont_humedad_excel(ch_req))

    # 4. Peso Unitario
    print("Generando Peso Unitario...")
    pu_req = PesoUnitarioRequest(
        muestra="147-AG-26",
        numero_ot="OT-PU-26",
        fecha_ensayo="2026/06/24",
        realizado_por="ANDRES SANCHEZ",
        revisado_por="FABIAN LA ROSA",
        revisado_fecha="2026/06/24",
        aprobado_por="IRMA COAQUIRA",
        aprobado_fecha="2026/06/24",
        recipiente_molde_numero="M-01",
        recipiente_masa_medida_kg=3.5,
        recipiente_volumen_m3=0.00944,
        metodo_compactacion="A",
        tipo_muestra="AGREGADO GRUESO",
        tamano_maximo_nominal_visual_in="3/4\"",
        masa_agregado_g=15000.0,
        masa_agregado_seco_g=14800.0,
        masa_agregado_seco_constante_g=14800.0,
        prueba_d_masa_agregado_mas_medida_kg=[18.5, 18.6, 18.55],
        prueba_e_masa_agregado_kg=[15.0, 15.1, 15.05],
        prueba_f_densidad_aparente_kg_m3=[1588.9, 1599.5, 1594.2],
        densidad_aparente_promedio_kg_m3=1594.2,
        vacios_i_gravedad_especifica_base_seca=[2.68, 2.68, 2.68],
        vacios_j_densidad_agua_kg_m3=[998.0, 998.0, 998.0],
        vacios_k_porcentaje=[40.5, 40.1, 40.3],
        vacios_promedio_pct=40.3
    )
    (out_dir / "test_peso_unitario.xlsx").write_bytes(generate_peso_unitario_excel(pu_req))

    # 5. Tamiz (ASTM C117)
    print("Generando Tamiz...")
    tamiz_req = TamizRequest(
        muestra="147-AG-26",
        numero_ot="OT-TAMIZ-26",
        fecha_ensayo="2026/06/24",
        realizado_por="ANDRES SANCHEZ",
        revisado_por="FABIAN LA ROSA",
        revisado_fecha="2026/06/24",
        aprobado_por="IRMA COAQUIRA",
        aprobado_fecha="2026/06/24",
        procedimiento="A",
        tamano_maximo_nominal_visual_in="3/4\"",
        a_masa_recipiente_g=120.0,
        b_masa_recipiente_muestra_seca_g=1120.0,
        c_masa_recipiente_muestra_seca_constante_g=1120.0,
        d_masa_seca_original_muestra_g=1000.0,
        e_masa_recipiente_muestra_seca_despues_lavado_g=1090.0,
        f_masa_recipiente_muestra_seca_despues_lavado_constante_g=1090.0,
        g_masa_seca_muestra_despues_lavado_g=970.0,
        h_porcentaje_material_fino_pct=3.0,
        balanza_01g_codigo="BAL-01",
        horno_110c_codigo="HOR-110",
        tamiz_no_200_codigo="INS-200",
        tamiz_no_16_codigo="INS-16"
    )
    (out_dir / "test_tamiz.xlsx").write_bytes(generate_tamiz_excel(tamiz_req))

    # 6. Abrass (C131)
    print("Generando Abrass (C131)...")
    abrass_req = AbrassRequest(
        muestra="147-AG-26",
        numero_ot="OT-ABRASS-26",
        fecha_ensayo="2026/06/24",
        realizado_por="ANDRES SANCHEZ",
        revisado_por="FABIAN LA ROSA",
        revisado_fecha="2026/06/24",
        aprobado_por="IRMA COAQUIRA",
        aprobado_fecha="2026/06/24",
        masa_muestra_inicial_g=5000.0,
        masa_muestra_inicial_seca_despues_lavado_g=4980.0,
        masa_muestra_inicial_seca_constante_despues_lavado_g=4980.0,
        requiere_lavado="SI",
        numero_revoluciones=500.0,
        gradacion_a_tamiz_g=[1250, 1250, 1250, 1250, 0, 0, 0],
        gradacion_b_tamiz_g=[0]*7,
        gradacion_c_tamiz_g=[0]*7,
        gradacion_d_tamiz_g=[0]*7,
        item_3_masa_esferas_conjunto_g=[5000.0, 0, 0, 0],
        item_a_masa_original_g=[5000.0, 0, 0, 0],
        item_b_masa_final_g=[3850.0, 0, 0, 0],
        item_c_masa_final_lavada_seca_g=[3800.0, 0, 0, 0],
        item_d_masa_final_lavada_seca_constante_g=[3800.0, 0, 0, 0],
        item_e_perdida_abrasion_pct=[24.0, 0, 0, 0],
        item_f_perdida_lavado_pct=[1.0, 0, 0, 0]
    )
    (out_dir / "test_abrass.xlsx").write_bytes(generate_abrass_excel(abrass_req))

    # 7. Ge Grueso (C127)
    print("Generando Ge Grueso...")
    grueso_req = GeGruesoRequest(
        muestra="147-AG-26",
        numero_ot="OT-GRUESO-26",
        fecha_ensayo="2026/06/24",
        realizado_por="ANDRES SANCHEZ",
        revisado_por="FABIAN LA ROSA",
        revisado_fecha="2026/06/24",
        aprobado_por="IRMA COAQUIRA",
        aprobado_fecha="2026/06/24",
        tamano_maximo_nominal="1\"",
        agregado_grupo_ligero_si_no="NO",
        retenido_malla_no4_si_no="SI",
        retenido_malla_1_1_2_si_no="NO",
        fecha_hora_inmersion_inicial="2026/06/24 08:00",
        fecha_hora_inmersion_final="2026/06/24 12:00",
        equipo_balanza_1g_codigo="BAL-1G",
        equipo_horno_110_codigo="HOR-110",
        equipo_termometro_01c_codigo="TERM-01",
        equipo_canastilla_codigo="CAN-01",
        equipo_tamiz_codigo="TAM-01",
        equipo_gravedad_especifica_codigo="GE-01",
        seco_horno_110_si_no="SI",
        ensayada_en_fracciones_si_no="NO",
        malla_fraccion="-",
        masa_retenida_malla_1_1_2_pct=0.0,
        masa_muestra_inicial_total_kg=5.0,
        masa_fraccion_01_kg=5.0,
        masa_fraccion_02_kg=0.0,
        fr1_a_g=3000.0,
        fr1_b_g=3050.0,
        fr1_c_g=1880.0,
        fr1_d_g=1170.0,
        fr1_masa_total_g=3000.0,
        fr2_a_g=0.0,
        fr2_b_g=0.0,
        fr2_c_g=0.0,
        fr2_d_g=0.0,
        fr2_masa_total_g=0.0
    )
    (out_dir / "test_ge_grueso.xlsx").write_bytes(generate_ge_grueso_excel(grueso_req))

    # 8. Planas (D4791)
    print("Generando Planas...")
    planas_req = PlanasRequest(
        muestra="147-AG-26",
        numero_ot="OT-PLANAS-26",
        fecha_ensayo="2026/06/24",
        realizado_por="ANDRES SANCHEZ",
        revisado_por="FABIAN LA ROSA",
        revisado_fecha="2026/06/24",
        aprobado_por="IRMA COAQUIRA",
        aprobado_fecha="2026/06/24",
        relacion_dimensional="1:3",
        metodo_ensayo="A",
        tamiz_requerido="3/8 in.",
        masa_inicial_g=2500.0,
        masa_seca_g=2480.0,
        masa_seca_constante_g=2480.0,
        gradacion_rows=[
            PlanasGradacionRow(pasa_tamiz="2 in.", retenido_tamiz="1 1/2 in.", masa_retenido_original_g=100.0, porcentaje_retenido=4.0, criterio_acepta=False, numero_particulas_aprox_100=0, masa_retenido_g=0.0),
            PlanasGradacionRow(pasa_tamiz="1 1/2 in.", retenido_tamiz="1 in.", masa_retenido_original_g=500.0, porcentaje_retenido=20.0, criterio_acepta=True, numero_particulas_aprox_100=100, masa_retenido_g=490.0)
        ],
        metodo_rows=[
            PlanasMetodoRow(retenido_tamiz="1 1/2 in.", grupo1_numero_particulas=10, grupo1_masa_g=50.0, grupo2_numero_particulas=5, grupo2_masa_g=25.0, grupo3_numero_particulas=2, grupo3_masa_g=10.0, grupo4_numero_particulas=83, grupo4_masa_g=405.0)
        ],
        dispositivo_calibre_codigo="EQP-0044",
        balanza_01g_codigo="EQP-0046",
        horno_codigo="EQP-0150",
        nota="Prueba local"
    )
    (out_dir / "test_planas.xlsx").write_bytes(generate_planas_excel(planas_req))

    # 9. Caras (D5821)
    print("Generando Caras...")
    caras_req = CarasRequest(
        muestra="147-AG-26",
        numero_ot="OT-CARAS-26",
        fecha_ensayo="2026/06/24",
        realizado_por="ANDRES SANCHEZ",
        revisado_por="FABIAN LA ROSA",
        revisado_fecha="2026/06/24",
        aprobado_por="IRMA COAQUIRA",
        aprobado_fecha="2026/06/24",
        metodo_determinacion="MASA",
        tamano_maximo_nominal_in="3/4 in",
        tamiz_especificado_in="No. 4",
        fraccionada=False,
        masa_muestra_retenida_g=1000.0,
        masa_particula_mas_grande_g=50.0,
        porcentaje_particula_mas_grande_pct=5.0,
        masa_muestra_seca_lavada_g=950.0,
        masa_muestra_seca_lavada_constante_g=950.0,
        masa_muestra_mayor_3_8_g=600.0,
        masa_muestra_menor_3_8_g=350.0,
        global_una_f_masa_fracturadas_g=500.0,
        global_una_n_masa_no_cumple_g=100.0,
        global_una_p_porcentaje_pct=83.33,
        global_dos_f_masa_fracturadas_g=450.0,
        global_dos_n_masa_no_cumple_g=150.0,
        global_dos_p_porcentaje_pct=75.0,
        promedio_ponderado_una_pct=83.33,
        promedio_ponderado_dos_pct=75.0,
        horno_codigo="EQP-HORNO",
        balanza_01g_codigo="EQP-BALANZA",
        tamiz_especificado_codigo="EQP-TAMIZ",
        nota="Prueba local de caras"
    )
    (out_dir / "test_caras.xlsx").write_bytes(generate_caras_excel(caras_req))

    # 10. Abra (C535)
    print("Generando Abra (C535)...")
    abra_req = AbraRequest(
        muestra="147-AG-26",
        numero_ot="OT-ABRA-26",
        fecha_ensayo="2026/06/24",
        realizado_por="ANDRES SANCHEZ",
        revisado_por="FABIAN LA ROSA",
        revisado_fecha="2026/06/24",
        aprobado_por="IRMA COAQUIRA",
        aprobado_fecha="2026/06/24",
        masa_muestra_inicial_g=5000.0,
        masa_muestra_inicial_seca_g=4980.0,
        masa_muestra_inicial_seca_constante_g=4980.0,
        requiere_lavado="SI",
        tmn='3/4"',
        masa_12_esferas_g=5000.0,
        gradacion_1_tamiz_g=[1250, 1250, 1250, 1250, 0, 0],
        gradacion_2_tamiz_g=[0]*6,
        gradacion_3_tamiz_g=[0]*6,
        item_a_masa_original_g=[5000.0, 0, 0],
        item_b_masa_retenida_tamiz_12_g=[4000.0, 0, 0],
        item_c_masa_lavada_seca_retenida_g=[3950.0, 0, 0],
        item_d_masa_lavada_seca_constante_g=[3950.0, 0, 0],
        item_e_diferencia_masa_g=[1050.0, 0, 0],
        item_f_desgaste_pct=[21.0, 0, 0],
        item_perdida_lavado_pct=[1.0, 0, 0],
        horno_codigo="EQP-0150",
        maquina_los_angeles_codigo="EQP-0043",
        balanza_1g_codigo="EQP-0054",
        malla_no_12_codigo="INS-0144",
        malla_no_4_codigo="INS-0053",
        observaciones="Prueba local de abrasión"
    )
    (out_dir / "test_abra.xlsx").write_bytes(generate_abra_excel(abra_req))

    print("[SUCCESS] Se generaron los 10 archivos de prueba exitosamente.")

if __name__ == "__main__":
    main()
