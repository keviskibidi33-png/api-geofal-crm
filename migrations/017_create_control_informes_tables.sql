CREATE TABLE IF NOT EXISTS public.control_ensayos_catalogo (
    id SERIAL PRIMARY KEY,
    codigo VARCHAR(60) NOT NULL UNIQUE,
    nombre VARCHAR(140) NOT NULL,
    area VARCHAR(80),
    orden INTEGER NOT NULL DEFAULT 0,
    activo BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.control_ensayo_counters (
    id SERIAL PRIMARY KEY,
    ensayo_codigo VARCHAR(60) NOT NULL UNIQUE,
    ultimo_numero INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_control_ensayo_counters_catalogo
        FOREIGN KEY (ensayo_codigo)
        REFERENCES public.control_ensayos_catalogo(codigo)
        ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS public.control_informes (
    id SERIAL PRIMARY KEY,
    fecha DATE NOT NULL,
    responsable_user_id VARCHAR(80),
    responsable_nombre VARCHAR(140),
    archivo_nombre VARCHAR(255) NOT NULL,
    archivo_url TEXT,
    observaciones TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.control_informe_detalles (
    id SERIAL PRIMARY KEY,
    informe_id INTEGER NOT NULL,
    ensayo_codigo VARCHAR(60) NOT NULL,
    ensayo_nombre VARCHAR(140) NOT NULL,
    numero_asignado INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_control_informe_detalles_informe
        FOREIGN KEY (informe_id)
        REFERENCES public.control_informes(id)
        ON DELETE CASCADE,
    CONSTRAINT fk_control_informe_detalles_catalogo
        FOREIGN KEY (ensayo_codigo)
        REFERENCES public.control_ensayos_catalogo(codigo)
        ON DELETE RESTRICT,
    CONSTRAINT uq_control_informe_detalle_numero_por_ensayo UNIQUE (ensayo_codigo, numero_asignado),
    CONSTRAINT uq_control_informe_detalle_un_ensayo_por_informe UNIQUE (informe_id, ensayo_codigo)
);

CREATE INDEX IF NOT EXISTS ix_control_informes_fecha ON public.control_informes (fecha);
CREATE INDEX IF NOT EXISTS ix_control_informes_created_at ON public.control_informes (created_at DESC);
CREATE INDEX IF NOT EXISTS ix_control_informe_detalles_informe_id ON public.control_informe_detalles (informe_id);
CREATE INDEX IF NOT EXISTS ix_control_informe_detalles_ensayo_codigo ON public.control_informe_detalles (ensayo_codigo);
CREATE INDEX IF NOT EXISTS ix_control_informe_detalles_numero_asignado ON public.control_informe_detalles (numero_asignado);

INSERT INTO public.control_ensayos_catalogo (codigo, nombre, area, orden, activo) VALUES
('granul_su', 'GRANUL SU', 'PROBETAS', 10, TRUE),
('ll_lp', 'LL - LP', 'PROBETAS', 20, TRUE),
('cl_sucs_aastho', 'CL. SUCS - AASTHO', 'PROBETAS', 30, TRUE),
('proc_mod', 'PROC MOD', 'PROBETAS', 40, TRUE),
('sales_su', 'SALES SU', 'PROBETAS', 50, TRUE),
('clorur_su', 'CLORUR SU', 'PROBETAS', 60, TRUE),
('sulfa_su', 'SULFA SU', 'PROBETAS', 70, TRUE),
('ph', 'PH', 'PROBETAS', 80, TRUE),
('corte', 'CORTE', 'PROBETAS', 90, TRUE),
('cbr', 'CBR', 'PROBETAS', 100, TRUE),
('grav_solido', 'GRAV SOLIDO', 'PROBETAS', 110, TRUE),
('compresion_no_confinada', 'COMPRESION NO CONFINADA', 'PROBETAS', 120, TRUE),
('correccion_proctor', 'CORRECCION PROCTOR', 'PROBETAS', 130, TRUE),
('contenido_mat_organica', 'CONTENIDO MAT. ORGANICA', 'PROBETAS', 140, TRUE),
('dpl', 'DPL', 'PROBETAS', 150, TRUE),
('gran_macro', 'GRAN. MACRO', 'PROBETAS', 160, TRUE),
('placa_carga', 'PLACA CARGA', 'PROBETAS', 170, TRUE),
('triaxial', 'TRIAXIAL', 'PROBETAS', 180, TRUE),
('hinchamiento', 'HINCHAMIENTO', 'PROBETAS', 190, TRUE),
('colapso', 'COLAPSO', 'PROBETAS', 200, TRUE),
('permeabilidad', 'PERMEABILIDAD', 'PROBETAS', 210, TRUE),
('termica', 'TERMICA', 'PROBETAS', 220, TRUE),
('analisis_gran_hidrometro', 'ANÁLISIS GRAN.(HIDRÓMETRO)', 'PROBETAS', 230, TRUE)
ON CONFLICT (codigo) DO UPDATE
SET nombre = EXCLUDED.nombre,
    area = EXCLUDED.area,
    orden = EXCLUDED.orden,
    activo = EXCLUDED.activo;

UPDATE public.control_ensayos_catalogo
SET activo = FALSE
WHERE codigo NOT IN (
    'granul_su','ll_lp','cl_sucs_aastho','proc_mod','sales_su','clorur_su','sulfa_su','ph','corte','cbr',
    'grav_solido','compresion_no_confinada','correccion_proctor','contenido_mat_organica','dpl','gran_macro',
    'placa_carga','triaxial','hinchamiento','colapso','permeabilidad','termica','analisis_gran_hidrometro'
);
