-- =============================================================================
-- GEOFAL CRM - TABLAS SUPABASE PARA CONTROL AMBIENTAL
-- Formatos F-LEM-IN-01.02 V03 (Balanzas) y F-LEM-P-05.01 (Temperatura/Humedad)
-- =============================================================================

-- 1. Tabla Encabezado Formato de Verificación Diaria de Balanzas (F-LEM-IN-01.02 V03)
CREATE TABLE IF NOT EXISTS public.control_verificacion_balanzas (
    id BIGSERIAL PRIMARY KEY,
    codigo_balanza VARCHAR(50) NOT NULL,
    nombre_balanza VARCHAR(150),
    mes_anio VARCHAR(50) NOT NULL,
    ubicacion VARCHAR(100) NOT NULL,
    codigos_pesas_patron VARCHAR(150) DEFAULT 'PP-01, PP-02, PP-05',
    capacidad_g NUMERIC(10,2),
    masa_patron_g NUMERIC(10,2),
    error_max_permitido_g NUMERIC(10,3),
    limpieza_nivelacion BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 2. Tabla Filas Diarias de Verificación Diaria de Balanzas
CREATE TABLE IF NOT EXISTS public.control_verificacion_balanzas_filas (
    id BIGSERIAL PRIMARY KEY,
    header_id BIGINT REFERENCES public.control_verificacion_balanzas(id) ON DELETE CASCADE,
    fecha DATE NOT NULL DEFAULT CURRENT_DATE,
    hora TIME NOT NULL DEFAULT '08:00',
    temp_c NUMERIC(4,1),
    humedad_pct NUMERIC(4,1),
    pesadas JSONB DEFAULT '[]'::jsonb, -- 15 slots con lectura_balanza_g, masa_patron_g, estado (OK/NO/-)
    verificado_por VARCHAR(100) NOT NULL DEFAULT 'BEATRIZ',
    revisado_por VARCHAR(100) NOT NULL DEFAULT 'ING. FABIAN',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 3. Tabla Encabezado Formatos de Control de Temperatura y Humedad (F-LEM-P-05.01)
CREATE TABLE IF NOT EXISTS public.control_temperatura_humedad (
    id BIGSERIAL PRIMARY KEY,
    registro_codigo VARCHAR(50) DEFAULT 'F-LEM-P-05.01',
    mes_anio VARCHAR(50) NOT NULL,
    area_ambiente VARCHAR(100) NOT NULL,
    aprobado_por VARCHAR(100) DEFAULT 'JEFE DE LABORATORIO',
    fecha_aprobacion DATE DEFAULT CURRENT_DATE,
    cumple_global BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 4. Tabla Filas Diarias de Control de Temperatura y Humedad
CREATE TABLE IF NOT EXISTS public.control_temperatura_humedad_filas (
    id BIGSERIAL PRIMARY KEY,
    header_id BIGINT REFERENCES public.control_temperatura_humedad(id) ON DELETE CASCADE,
    fecha_registro DATE NOT NULL,
    hora_toma TIME NOT NULL,
    fecha_lectura DATE,
    temp_min NUMERIC(4,1),
    temp_max NUMERIC(4,1),
    hum_min NUMERIC(4,1),
    hum_max NUMERIC(4,1),
    temperatura_c NUMERIC(4,1) NOT NULL,
    humedad_relativa_pct NUMERIC(4,1) NOT NULL,
    cumple BOOLEAN DEFAULT TRUE,
    responsable_registro VARCHAR(100) NOT NULL,
    responsable_revision VARCHAR(100),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Habilitar RLS e índices para rendimiento
ALTER TABLE public.control_temperatura_humedad ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.control_temperatura_humedad_filas ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.control_verificacion_balanzas ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.control_verificacion_balanzas_filas ENABLE ROW LEVEL SECURITY;

-- Políticas permisivas para usuarios autenticados
CREATE POLICY "Permitir lectura y escritura a control_temperatura_humedad" ON public.control_temperatura_humedad FOR ALL USING (true);
CREATE POLICY "Permitir lectura y escritura a control_temperatura_humedad_filas" ON public.control_temperatura_humedad_filas FOR ALL USING (true);
CREATE POLICY "Permitir lectura y escritura a control_verificacion_balanzas" ON public.control_verificacion_balanzas FOR ALL USING (true);
CREATE POLICY "Permitir lectura y escritura a control_verificacion_balanzas_filas" ON public.control_verificacion_balanzas_filas FOR ALL USING (true);

-- Notificar a PostgREST para recargar esquema
NOTIFY pgrst, 'reload schema';
