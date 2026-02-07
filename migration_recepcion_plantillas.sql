-- Create table for Reception Templates
CREATE TABLE IF NOT EXISTS public.recepcion_plantillas (
    id SERIAL PRIMARY KEY,
    nombre_plantilla VARCHAR(255) UNIQUE NOT NULL,
    
    -- Client info
    cliente VARCHAR(255) NOT NULL,
    ruc VARCHAR(20) NOT NULL,
    domicilio_legal TEXT NOT NULL,
    persona_contacto VARCHAR(255),
    email VARCHAR(255),
    telefono VARCHAR(50),
    
    -- Report/Project info
    solicitante VARCHAR(255) NOT NULL,
    domicilio_solicitante TEXT NOT NULL,
    proyecto VARCHAR(255) NOT NULL,
    ubicacion TEXT NOT NULL,
    
    -- Metadata
    fecha_creacion TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    fecha_actualizacion TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- Enable RLS if needed (adjust based on project policy)
ALTER TABLE public.recepcion_plantillas ENABLE ROW LEVEL SECURITY;

-- Create policy for all (assuming public access or similar as other tables in this project)
CREATE POLICY "Allow all access to recepcion_plantillas" ON public.recepcion_plantillas
    FOR ALL USING (true);

-- Add comment
COMMENT ON TABLE public.recepcion_plantillas IS 'Plantillas para agilizar el llenado de recepciones de muestras';
