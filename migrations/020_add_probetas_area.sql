-- Add PROBETAS area to control_ensayos_catalogo
INSERT INTO control_ensayos_catalogo (codigo, nombre, area, orden, activo, created_at) VALUES
('pb-res-prob', 'COMPRESION DE PROBETAS', 'PROBETAS', 1, true, NOW())
ON CONFLICT (codigo) DO UPDATE SET
    nombre = EXCLUDED.nombre,
    area = EXCLUDED.area,
    orden = EXCLUDED.orden,
    activo = EXCLUDED.activo;
