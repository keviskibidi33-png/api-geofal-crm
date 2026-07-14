from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field, field_validator, model_validator
from app.modules.common.schema_helpers import LabRequestBase, coerce_float, normalize_text, round_value


class DensidadHuantarPunto(BaseModel):
    punto_numero: int = Field(..., description="Número de punto (1 al 4)")
    ubicacion: Optional[str] = Field(None, description="Ubicación de la prueba")
    progresiva: Optional[str] = Field(None, description="Progresiva / Cota / Lado")
    tipo_muestra: Optional[str] = Field(None, description="Tipo de muestra")
    espesor_capa: Optional[float] = Field(None, description="Espesor de la capa en cm")
    tamano_maximo: Optional[str] = Field(None, description="Tamaño máximo de grava identificado")
    tamiz_sobretamano: Optional[str] = Field(None, description="Tamiz del sobretamaño")
    descripcion_visual: Optional[str] = Field(None, description="Descripción visual del suelo")
    condiciones_entorno: Optional[str] = Field(None, description="Condiciones de entorno")

    # Mediciones de campo/laboratorio
    masa_inicial_cono: Optional[float] = Field(None, description="Masa inicial del cono más arena (g)")
    masa_residual_cono: Optional[float] = Field(None, description="Masa residual del cono más arena (g)")
    masa_humeda_orificio: Optional[float] = Field(None, description="Masa húmeda de material del orificio (g)")
    masa_sobretamano: Optional[float] = Field(None, description="Masa de sobretamaño (g)")
    criterio_aceptacion: Optional[float] = Field(None, description="Criterio de aceptación (%)")
    humedad_speedy: Optional[float] = Field(None, description="Contenido de agua SPEEDY (%)")
    humedad_astm: Optional[float] = Field(None, description="Contenido de agua ASTM D2216 (%)")

    # Resultados calculados (devolución del API)
    masa_arena_utilizada: Optional[float] = None
    volumen_orificio: Optional[float] = None
    porcentaje_sobretamano: Optional[float] = None
    humedad_usada: Optional[float] = None
    masa_seca_material: Optional[float] = None
    densidad_humeda: Optional[float] = None
    densidad_seca: Optional[float] = None
    peso_unitario_seco: Optional[float] = None
    peso_unitario_corregido: Optional[float] = None
    porcentaje_compactacion: Optional[float] = None
    criterio_volumen_minimo: Optional[float] = None
    cumple_volumen: Optional[str] = None

    @field_validator("ubicacion", "progresiva", "tipo_muestra", "tamano_maximo", "tamiz_sobretamano", "descripcion_visual", "condiciones_entorno", mode="before")
    @classmethod
    def normalize_text_fields(cls, value):
        return normalize_text(value)

    @field_validator("espesor_capa", "masa_inicial_cono", "masa_residual_cono", "masa_humeda_orificio", "masa_sobretamano", "criterio_aceptacion", "humedad_speedy", "humedad_astm", mode="before")
    @classmethod
    def normalize_numeric_fields(cls, value):
        return coerce_float(value)


class DensidadHuantarRequest(LabRequestBase):
    cono_codigo: Optional[str] = Field(None, description="Identificación del Cono N°")
    masa_arena_embudo: Optional[float] = Field(None, description="Masa de arena embudo y placa")
    densidad_arena: Optional[float] = Field(None, description="Densidad de la arena (g/cm3)")
    volumen_cono: Optional[float] = Field(None, description="Volumen calibrado cono (cm3)")
    proctor_norma: Optional[str] = Field("-", description="Norma ensayo de Proctor")
    proctor_metodo: Optional[str] = Field("-", description="Método de ensayo de Proctor")
    peso_unitario_seco_lab: Optional[float] = Field(None, description="Peso unitario seco de laboratorio en kN/m3")
    humedad_optima: Optional[float] = Field(None, description="Humedad Óptima (%)")
    gravedad_especifica: Optional[float] = Field(None, description="Gravedad específica (P)")

    # Condiciones ambientales
    temperatura_inicial: Optional[str] = Field("-", description="Temperatura Inicial (°C)")
    temperatura_final: Optional[str] = Field("-", description="Temperatura Final (°C)")
    humedad_relativa_inicial: Optional[str] = Field("-", description="Humedad relativa Inicial (%H.R.)")
    humedad_relativa_final: Optional[str] = Field("-", description="Humedad relativa Final (%H.R.)")

    # Códigos de equipos utilizados
    eq_balanza_30kg: Optional[str] = Field("-", description="Balanza 30 kg")
    eq_pesa_patron_5kg: Optional[str] = Field("-", description="Pesa patrón 5 kg")
    eq_cono_equipo: Optional[str] = Field("-", description="Cono (código de equipo)")
    eq_tamiz_3_4: Optional[str] = Field("-", description="Tamiz 3/4 in")
    eq_termohigrometro: Optional[str] = Field("-", description="Termohigrómetro")
    eq_tamiz_4: Optional[str] = Field("-", description="Tamiz 4 in")
    eq_pesa_patron_200g: Optional[str] = Field("-", description="Pesa patrón 200 g")
    eq_tamiz_3_8: Optional[str] = Field("-", description="Tamiz 3/8 in")
    eq_balanza_500g: Optional[str] = Field("-", description="Balanza 500 g")

    puntos: List[DensidadHuantarPunto] = Field(default_factory=list, description="Lista de puntos de ensayo (hasta 4)")

    @field_validator(
        "cono_codigo", "proctor_norma", "proctor_metodo",
        "temperatura_inicial", "temperatura_final",
        "humedad_relativa_inicial", "humedad_relativa_final",
        "eq_balanza_30kg", "eq_pesa_patron_5kg", "eq_cono_equipo",
        "eq_tamiz_3_4", "eq_termohigrometro", "eq_tamiz_4",
        "eq_pesa_patron_200g", "eq_tamiz_3_8", "eq_balanza_500g",
        mode="before"
    )
    @classmethod
    def normalize_text_fields(cls, value):
        return normalize_text(value)

    @field_validator("masa_arena_embudo", "densidad_arena", "volumen_cono", "peso_unitario_seco_lab", "humedad_optima", "gravedad_especifica", mode="before")
    @classmethod
    def normalize_numeric_fields(cls, value):
        return coerce_float(value)

    @model_validator(mode="after")
    def compute_results(self):
        # Asegurar que haya exactamente 4 puntos en el payload para consistencia con el Excel
        puntos_actuales = self.puntos or []
        puntos_map = {p.punto_numero: p for p in puntos_actuales if p.punto_numero in (1, 2, 3, 4)}
        
        nuevos_puntos = []
        for i in range(1, 5):
            punto = puntos_map.get(i)
            if not punto:
                punto = DensidadHuantarPunto(punto_numero=i)
            
            # Realizar cálculos del punto si existen las mediciones necesarias
            if (punto.masa_inicial_cono is not None and 
                punto.masa_residual_cono is not None and 
                self.masa_arena_embudo is not None and 
                self.densidad_arena is not None and 
                self.densidad_arena > 0):
                
                # 1. Masa arena utilizada
                punto.masa_arena_utilizada = round_value(punto.masa_inicial_cono - punto.masa_residual_cono, 3)
                
                # 2. Volumen orificio = (Masa utilizada - embudo) / densidad arena
                if punto.masa_arena_utilizada > self.masa_arena_embudo:
                    punto.volumen_orificio = round_value((punto.masa_arena_utilizada - self.masa_arena_embudo) / self.densidad_arena, 3)
                else:
                    punto.volumen_orificio = 0.0
                
                # 3. Criterio de volumen mínimo según tamaño máximo
                # E17 en Datos: "2 in", "1 1/2 in" -> 2830; "1 in", "3/4 in" -> 2120; "1/2 in", "3/8 in" -> 1420; default -> 1420
                t_max = (punto.tamano_maximo or "").strip().lower()
                if t_max in {"2 in", "2\"", "1 1/2 in", "1 1/2\"", "1.5 in", "1.5\""}:
                    punto.criterio_volumen_minimo = 2830.0
                elif t_max in {"1 in", "1\"", "3/4 in", "3/4\"", "0.75 in", "0.75\""}:
                    punto.criterio_volumen_minimo = 2120.0
                else:
                    punto.criterio_volumen_minimo = 1420.0
                
                # 4. Cumple volumen
                if punto.volumen_orificio is not None:
                    punto.cumple_volumen = "Cumple" if punto.volumen_orificio >= punto.criterio_volumen_minimo else "Justificar"
                
                # 5. Humedad usada (prioridad: speedy, si no astm)
                if punto.humedad_speedy is not None:
                    punto.humedad_usada = punto.humedad_speedy
                elif punto.humedad_astm is not None:
                    punto.humedad_usada = punto.humedad_astm
                else:
                    punto.humedad_usada = 0.0
                
                # 6. Masa húmeda y seca
                if punto.masa_humeda_orificio is not None:
                    # Masa seca = 100 * Masa húmeda / (100 + w)
                    punto.masa_seca_material = round_value(100.0 * punto.masa_humeda_orificio / (100.0 + punto.humedad_usada), 3)
                    
                    # Densidad húmeda = Masa húmeda / Volumen orificio
                    if punto.volumen_orificio and punto.volumen_orificio > 0:
                        punto.densidad_humeda = round_value(punto.masa_humeda_orificio / punto.volumen_orificio, 3)
                        punto.densidad_seca = round_value(punto.masa_seca_material / punto.volumen_orificio, 3)
                        
                        # Peso unitario seco = Densidad seca * 9.802
                        punto.peso_unitario_seco = round_value(punto.densidad_seca * 9.802, 3)
                
                # 7. Porcentaje de sobretamaño = Masa sobretamaño * 100 / Masa húmeda
                if punto.masa_sobretamano is not None and punto.masa_humeda_orificio:
                    punto.porcentaje_sobretamano = round_value(punto.masa_sobretamano * 100.0 / punto.masa_humeda_orificio, 3)
                else:
                    punto.porcentaje_sobretamano = 0.0

                # 8. Peso unitario corregido (ASTM D4718)
                # E28: =IF($J$1="",E24,IF($J$1="-",E24,E24*$J$1*9.802*(100-E21)/(100*$J$1*9.802-E24*E21)))
                # Donde $J$1 es gravedad especifica (Gs) de Proctor, E24 es peso_unitario_seco, E21 es porcentaje_sobretamaño
                if punto.peso_unitario_seco is not None:
                    gs = self.gravedad_especifica
                    if gs is None or gs == 0:
                        punto.peso_unitario_corregido = punto.peso_unitario_seco
                    else:
                        num = punto.peso_unitario_seco * gs * 9.802 * (100.0 - punto.porcentaje_sobretamano)
                        den = (100.0 * gs * 9.802) - (punto.peso_unitario_seco * punto.porcentaje_sobretamano)
                        if den != 0:
                            punto.peso_unitario_corregido = round_value(num / den, 3)
                        else:
                            punto.peso_unitario_corregido = punto.peso_unitario_seco
                
                # 9. Porcentaje de compactación = peso unitario corregido / peso unitario lab * 100
                if punto.peso_unitario_corregido is not None and self.peso_unitario_seco_lab:
                    punto.porcentaje_compactacion = round_value(punto.peso_unitario_corregido * 100.0 / self.peso_unitario_seco_lab, 1)

            nuevos_puntos.append(punto)
            
        self.puntos = nuevos_puntos
        return self
