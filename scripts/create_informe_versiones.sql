-- ============================================================
-- TABLA: informe_versiones
-- Registra cada descarga/generación del informe como versión
-- para auditoría y control de cambios.
-- ============================================================

CREATE TABLE IF NOT EXISTS informe_versiones (
    id SERIAL PRIMARY KEY,
    trazabilidad_id INTEGER NOT NULL REFERENCES trazabilidad(id) ON DELETE CASCADE,
    numero_recepcion VARCHAR NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    
    -- Snapshot de estados al momento de generar
    estado_recepcion VARCHAR,
    estado_verificacion VARCHAR,
    estado_compresion VARCHAR,
    
    -- Resumen de datos incluidos
    total_muestras INTEGER DEFAULT 0,
    muestras_con_verificacion INTEGER DEFAULT 0,
    muestras_con_compresion INTEGER DEFAULT 0,
    
    -- Nota/comentario opcional
    notas TEXT,
    
    -- Metadata
    generado_por VARCHAR,
    fecha_generacion TIMESTAMPTZ DEFAULT NOW(),
    data_snapshot JSONB
);

-- Índices
CREATE INDEX IF NOT EXISTS idx_informe_versiones_recepcion ON informe_versiones(numero_recepcion);
CREATE INDEX IF NOT EXISTS idx_informe_versiones_trazabilidad ON informe_versiones(trazabilidad_id);
CREATE INDEX IF NOT EXISTS idx_informe_versiones_version ON informe_versiones(trazabilidad_id, version DESC);
