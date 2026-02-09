-- Migration: Create compression test tables
-- Run this against your database to enable the compression module

-- Main table for compression tests
CREATE TABLE IF NOT EXISTS ensayo_compresion (
    id SERIAL PRIMARY KEY,
    numero_ot VARCHAR(50) NOT NULL,
    numero_recepcion VARCHAR(50) NOT NULL,
    recepcion_id INTEGER,
    codigo_equipo VARCHAR(100),
    otros TEXT,
    nota TEXT,
    estado VARCHAR(20) NOT NULL DEFAULT 'PENDIENTE',
    bucket VARCHAR(100),
    object_key VARCHAR(500),
    realizado_por VARCHAR(100),
    revisado_por VARCHAR(100),
    aprobado_por VARCHAR(100),
    fecha_creacion TIMESTAMP NOT NULL DEFAULT NOW(),
    fecha_actualizacion TIMESTAMP
);

-- Items table for compression test samples
CREATE TABLE IF NOT EXISTS items_compresion (
    id SERIAL PRIMARY KEY,
    ensayo_id INTEGER NOT NULL REFERENCES ensayo_compresion(id) ON DELETE CASCADE,
    item INTEGER NOT NULL,
    codigo_lem VARCHAR(50) NOT NULL,
    fecha_ensayo TIMESTAMP,
    hora_ensayo VARCHAR(10),
    carga_maxima FLOAT,
    tipo_fractura VARCHAR(50),
    defectos TEXT,
    realizado VARCHAR(100),
    revisado VARCHAR(100),
    fecha_revisado TIMESTAMP,
    aprobado VARCHAR(100),
    fecha_aprobado TIMESTAMP,
    fecha_creacion TIMESTAMP NOT NULL DEFAULT NOW(),
    fecha_actualizacion TIMESTAMP
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_ensayo_compresion_numero_ot ON ensayo_compresion(numero_ot);
CREATE INDEX IF NOT EXISTS idx_ensayo_compresion_numero_recepcion ON ensayo_compresion(numero_recepcion);
CREATE INDEX IF NOT EXISTS idx_items_compresion_ensayo_id ON items_compresion(ensayo_id);
