-- Migration: Create seguimiento_cliente_comercial table
-- Description: Creates the customer tracking table with RLS and indexes.

BEGIN;

CREATE TABLE IF NOT EXISTS public.seguimiento_cliente_comercial (
    id SERIAL PRIMARY KEY,
    no INTEGER,
    fecha_contacto DATE,
    persona_contacto VARCHAR(255),
    numero_celular VARCHAR(100),
    email VARCHAR(255),
    razon_social VARCHAR(255),
    ruc VARCHAR(20),
    asesor VARCHAR(100),
    contacto VARCHAR(100),
    rubro VARCHAR(100),
    estado_cliente VARCHAR(100),
    servicio_solicitado TEXT,
    fecha_ultimo_contacto DATE,
    observaciones TEXT,
    numero_cotizacion VARCHAR(100),
    estado_seguimiento TEXT,
    creado_por VARCHAR(100),
    fecha_creacion TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    fecha_actualizacion TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for performance on query filters
CREATE INDEX IF NOT EXISTS ix_seguimiento_cliente_comercial_no ON public.seguimiento_cliente_comercial (no);
CREATE INDEX IF NOT EXISTS ix_seguimiento_cliente_comercial_fecha_contacto ON public.seguimiento_cliente_comercial (fecha_contacto);
CREATE INDEX IF NOT EXISTS ix_seguimiento_cliente_comercial_ruc ON public.seguimiento_cliente_comercial (ruc);
CREATE INDEX IF NOT EXISTS ix_seguimiento_cliente_comercial_asesor ON public.seguimiento_cliente_comercial (asesor);
CREATE INDEX IF NOT EXISTS ix_seguimiento_cliente_comercial_estado_cliente ON public.seguimiento_cliente_comercial (estado_cliente);
CREATE INDEX IF NOT EXISTS ix_seguimiento_cliente_comercial_numero_cotizacion ON public.seguimiento_cliente_comercial (numero_cotizacion);

-- Enable Row Level Security
ALTER TABLE public.seguimiento_cliente_comercial ENABLE ROW LEVEL SECURITY;

-- Drop existing policies if any
DROP POLICY IF EXISTS "Permitir lectura a usuarios autorizados" ON public.seguimiento_cliente_comercial;
DROP POLICY IF EXISTS "Permitir escritura a roles comerciales" ON public.seguimiento_cliente_comercial;

-- Create select policy
CREATE POLICY "Permitir lectura a usuarios autorizados"
ON public.seguimiento_cliente_comercial
FOR SELECT
TO authenticated
USING (
  public.normalize_role_policy(get_my_role()) IN (
    'admin',
    'admin_general',
    'administrativo',
    'auxiliar_comercial',
    'comercial'
  )
);

-- Create write/update/delete policy
CREATE POLICY "Permitir escritura a roles comerciales"
ON public.seguimiento_cliente_comercial
FOR ALL
TO authenticated
USING (
  public.normalize_role_policy(get_my_role()) IN (
    'admin',
    'admin_general',
    'administrativo',
    'auxiliar_comercial',
    'comercial'
  )
)
WITH CHECK (
  public.normalize_role_policy(get_my_role()) IN (
    'admin',
    'admin_general',
    'administrativo',
    'auxiliar_comercial',
    'comercial'
  )
);

COMMIT;
