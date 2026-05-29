-- Migration: Create publicidad_geofal table
-- Description: Creates the publicidad_geofal table with RLS and indexes.

BEGIN;

-- Create role policy helper functions if they do not exist
CREATE OR REPLACE FUNCTION public.normalize_role_policy(role_name text)
RETURNS text AS $$
  SELECT replace(lower(coalesce(role_name, '')), ' ', '_');
$$ LANGUAGE sql IMMUTABLE;

CREATE OR REPLACE FUNCTION public.get_my_role()
RETURNS text AS $$
  SELECT role FROM public.perfiles WHERE id = auth.uid() LIMIT 1;
$$ LANGUAGE sql SECURITY DEFINER;

CREATE TABLE IF NOT EXISTS public.publicidad_geofal (
    id SERIAL PRIMARY KEY,
    id_cliente INTEGER,
    contacto VARCHAR(255),
    telefono VARCHAR(100),
    telefono_2 VARCHAR(100),
    correo_referencial VARCHAR(255),
    razon_social_referencial VARCHAR(255),
    
    -- Mensualidades (Auxiliar / Asistente y Asesor)
    junio_asistente TEXT,
    junio_asesor TEXT,
    julio_asistente TEXT,
    julio_asesor TEXT,
    agosto_asistente TEXT,
    agosto_asesor TEXT,
    setiembre_asistente TEXT,
    setiembre_asesor TEXT,
    octubre_asistente TEXT,
    octubre_asesor TEXT,
    noviembre_asistente TEXT,
    noviembre_asesor TEXT,
    diciembre_asistente TEXT,
    diciembre_asesor TEXT,
    
    -- Columnas de observaciones adicionales (col 21 y 22)
    observacion_1 TEXT,
    observacion_2 TEXT,
    
    creado_por VARCHAR(100),
    fecha_creacion TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    fecha_actualizacion TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS ix_publicidad_geofal_id_cliente ON public.publicidad_geofal (id_cliente);
CREATE INDEX IF NOT EXISTS ix_publicidad_geofal_contacto ON public.publicidad_geofal (contacto);
CREATE INDEX IF NOT EXISTS ix_publicidad_geofal_razon_social ON public.publicidad_geofal (razon_social_referencial);

-- Enable Row Level Security
ALTER TABLE public.publicidad_geofal ENABLE ROW LEVEL SECURITY;

-- Drop existing policies if any
DROP POLICY IF EXISTS "Permitir lectura publicidad a usuarios autorizados" ON public.publicidad_geofal;
DROP POLICY IF EXISTS "Permitir escritura publicidad a roles comerciales" ON public.publicidad_geofal;

-- Create select policy
CREATE POLICY "Permitir lectura publicidad a usuarios autorizados"
ON public.publicidad_geofal
FOR SELECT
TO authenticated
USING (
  public.normalize_role_policy(public.get_my_role()) IN (
    'admin',
    'admin_general',
    'administrativo',
    'auxiliar_comercial',
    'comercial'
  )
);

-- Create write/update/delete policy
CREATE POLICY "Permitir escritura publicidad a roles comerciales"
ON public.publicidad_geofal
FOR ALL
TO authenticated
USING (
  public.normalize_role_policy(public.get_my_role()) IN (
    'admin',
    'admin_general',
    'administrativo',
    'auxiliar_comercial',
    'comercial'
  )
)
WITH CHECK (
  public.normalize_role_policy(public.get_my_role()) IN (
    'admin',
    'admin_general',
    'administrativo',
    'auxiliar_comercial',
    'comercial'
  )
);

COMMIT;

-- Trigger to sync new clients from seguimiento_cliente_comercial to publicidad_geofal
BEGIN;

-- Add publicity link column to customer tracking table
ALTER TABLE public.seguimiento_cliente_comercial 
ADD COLUMN IF NOT EXISTS publicidad_id INTEGER;

CREATE OR REPLACE FUNCTION public.sync_seguimiento_to_publicidad()
RETURNS TRIGGER AS $$
DECLARE
    next_id_cliente INTEGER;
    matched_publicidad_id INTEGER;
BEGIN
    -- Prevent trigger recursion recursion
    IF pg_trigger_depth() > 1 THEN
        RETURN NEW;
    END IF;

    -- Check if record exists (matching by razon_social or persona_contacto)
    SELECT id INTO matched_publicidad_id FROM public.publicidad_geofal 
    WHERE (razon_social_referencial = NEW.razon_social AND NEW.razon_social IS NOT NULL AND NEW.razon_social <> '')
       OR (contacto = NEW.persona_contacto AND NEW.persona_contacto IS NOT NULL AND NEW.persona_contacto <> '')
    LIMIT 1;

    IF matched_publicidad_id IS NOT NULL THEN
        -- Update existing record with the matching details
        UPDATE public.publicidad_geofal
        SET 
            telefono = COALESCE(NEW.numero_celular, telefono),
            correo_referencial = COALESCE(NEW.email, correo_referencial),
            razon_social_referencial = COALESCE(NEW.razon_social, razon_social_referencial),
            contacto = COALESCE(NEW.persona_contacto, contacto)
        WHERE id = matched_publicidad_id;
        
        NEW.publicidad_id := matched_publicidad_id;
    ELSE
        -- Calculate next id_cliente
        SELECT COALESCE(MAX(id_cliente), 0) + 1 INTO next_id_cliente FROM public.publicidad_geofal;

        -- Insert new record
        INSERT INTO public.publicidad_geofal (
            id_cliente, contacto, telefono, correo_referencial, razon_social_referencial, creado_por
        ) VALUES (
            next_id_cliente,
            NEW.persona_contacto,
            NEW.numero_celular,
            NEW.email,
            NEW.razon_social,
            NEW.creado_por
        ) RETURNING id INTO matched_publicidad_id;
        
        NEW.publicidad_id := matched_publicidad_id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_sync_seguimiento_to_publicidad ON public.seguimiento_cliente_comercial;

CREATE TRIGGER trigger_sync_seguimiento_to_publicidad
BEFORE INSERT OR UPDATE ON public.seguimiento_cliente_comercial
FOR EACH ROW
EXECUTE FUNCTION public.sync_seguimiento_to_publicidad();

COMMIT;


