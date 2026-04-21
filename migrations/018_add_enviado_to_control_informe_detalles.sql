-- Add 'enviado' column to control_informe_detalles
ALTER TABLE control_informe_detalles ADD COLUMN IF NOT EXISTS enviado BOOLEAN DEFAULT FALSE;
CREATE INDEX IF NOT EXISTS idx_control_informe_detalles_enviado ON control_informe_detalles(enviado);
