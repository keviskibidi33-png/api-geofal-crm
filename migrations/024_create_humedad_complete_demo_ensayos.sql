CREATE TABLE IF NOT EXISTS public.humedad_complete_demo_ensayos (
    id SERIAL PRIMARY KEY,
    numero_ensayo VARCHAR(100) NOT NULL,
    ot_n VARCHAR(100) NOT NULL,
    cliente VARCHAR(255),
    codigo_muestra VARCHAR(255),
    fecha_documento VARCHAR(20),
    estado VARCHAR(30) NOT NULL DEFAULT 'EN PROCESO',
    contenido_humedad DOUBLE PRECISION,
    bucket VARCHAR(100),
    object_key VARCHAR(500),
    payload_json JSON,
    fecha_creacion TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    fecha_actualizacion TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_humedad_complete_demo_ensayos_numero_ensayo
    ON public.humedad_complete_demo_ensayos (numero_ensayo);

CREATE INDEX IF NOT EXISTS ix_humedad_complete_demo_ensayos_ot_n
    ON public.humedad_complete_demo_ensayos (ot_n);

CREATE INDEX IF NOT EXISTS ix_humedad_complete_demo_ensayos_codigo_muestra
    ON public.humedad_complete_demo_ensayos (codigo_muestra);

CREATE INDEX IF NOT EXISTS ix_humedad_complete_demo_ensayos_fecha_creacion
    ON public.humedad_complete_demo_ensayos (fecha_creacion DESC);

INSERT INTO storage.buckets (id, name, public)
VALUES ('humedad-complete-demo', 'humedad-complete-demo', true)
ON CONFLICT (id) DO UPDATE
SET public = true;

DROP POLICY IF EXISTS "Public Access Humedad Complete Demo" ON storage.objects;
CREATE POLICY "Public Access Humedad Complete Demo"
ON storage.objects FOR ALL
TO public
USING (bucket_id = 'humedad-complete-demo')
WITH CHECK (bucket_id = 'humedad-complete-demo');
