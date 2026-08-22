-- 049_create_datos_clientes.sql
-- Tabla para directorio maestro de Datos de Clientes e Informes de Laboratorio

CREATE TABLE IF NOT EXISTS datos_clientes (
    id SERIAL PRIMARY KEY,
    -- DATOS CLIENTE
    cliente VARCHAR(255) NOT NULL,
    ruc VARCHAR(20) NOT NULL,
    domicilio_legal TEXT NOT NULL,
    persona_contacto VARCHAR(255),
    email VARCHAR(255),
    telefono VARCHAR(50),
    
    -- DATOS DEL INFORME
    solicitante VARCHAR(255) NOT NULL,
    domicilio_solicitante TEXT NOT NULL,
    proyecto VARCHAR(500) NOT NULL,
    ubicacion TEXT NOT NULL,
    
    -- METADATOS Y CONTROL
    estado VARCHAR(20) DEFAULT 'INCOMPLETO',
    activo BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Índices para búsqueda y rendimiento
CREATE INDEX IF NOT EXISTS idx_datos_clientes_cliente ON datos_clientes(cliente);
CREATE INDEX IF NOT EXISTS idx_datos_clientes_ruc ON datos_clientes(ruc);
CREATE INDEX IF NOT EXISTS idx_datos_clientes_proyecto ON datos_clientes(proyecto);
CREATE INDEX IF NOT EXISTS idx_datos_clientes_estado ON datos_clientes(estado);
