
-- Optimización de Índices para Trazabilidad y Búsquedas Cruzadas
-- Fecha: 17/02/2026
-- Autor: Sistema de Optimización Geofal

-- 1. Trazabilidad: Índices compuestos para dashboard y filtros
CREATE INDEX IF NOT EXISTS idx_trazabilidad_numero_recepcion_trgm ON public.trazabilidad USING gin (numero_recepcion gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_trazabilidad_cliente_trgm ON public.trazabilidad USING gin (cliente gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_trazabilidad_estados ON public.trazabilidad (estado_recepcion, estado_verificacion, estado_compresion, estado_informe);
CREATE INDEX IF NOT EXISTS idx_trazabilidad_fecha_creacion ON public.trazabilidad (fecha_creacion DESC);

-- 2. Recepción: Índices para búsquedas flexibles y ordenamiento
CREATE INDEX IF NOT EXISTS idx_recepcion_numero_trgm ON public.recepcion_muestras USING gin (numero_recepcion gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_recepcion_cliente_trgm ON public.recepcion_muestras USING gin (cliente gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_recepcion_fecha_creacion ON public.recepcion_muestras (fecha_creacion DESC);
CREATE INDEX IF NOT EXISTS idx_recepcion_bucket_key ON public.recepcion_muestras (bucket, object_key); -- Para validación rápida de storage

-- 3. Verificación: Índices para cruces
CREATE INDEX IF NOT EXISTS idx_verificacion_numero_trgm ON public.verificacion_muestras USING gin (numero_verificacion gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_verificacion_fecha_verificacion ON public.verificacion_muestras (fecha_verificacion DESC);

-- 4. Compresión: Índices para cruces y estados
CREATE INDEX IF NOT EXISTS idx_compresion_numero_recepcion_trgm ON public.ensayo_compresion USING gin (numero_recepcion gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_compresion_estado ON public.ensayo_compresion (estado);

-- 5. Programación: Índices para filtros de laboratorio y comercial
CREATE INDEX IF NOT EXISTS idx_prog_lab_fecha_recepcion ON public.programacion_lab (fecha_recepcion DESC);
CREATE INDEX IF NOT EXISTS idx_prog_lab_estado_muestra ON public.programacion_lab (estado_muestra);
CREATE INDEX IF NOT EXISTS idx_prog_com_estado_pago ON public.programacion_comercial (estado_pago);

-- Comentario: La extensión pg_trgm es necesaria para índices GIN de texto (búsquedas ILIKE eficientes)
CREATE EXTENSION IF NOT EXISTS pg_trgm;
