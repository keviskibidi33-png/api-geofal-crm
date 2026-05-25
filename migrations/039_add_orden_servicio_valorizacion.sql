-- Migration 039: Add orden_servicio and numero_valorizacion to programacion_administracion

-- 1. Add columns to programacion_administracion
ALTER TABLE public.programacion_administracion 
ADD COLUMN IF NOT EXISTS orden_servicio TEXT,
ADD COLUMN IF NOT EXISTS numero_valorizacion TEXT;

-- 2. Recreate the cuadro_control view to include the new columns
CREATE OR REPLACE VIEW public.cuadro_control AS
SELECT
    l.id,
    l.item_numero,
    l.recep_numero,
    l.ot,
    l.codigo_muestra,
    l.fecha_recepcion,
    l.fecha_inicio,
    l.fecha_entrega_estimada,
    l.cliente_nombre,
    l.descripcion_servicio,
    l.proyecto,
    l.entrega_real,
    l.estado_trabajo,
    l.cotizacion_lab,
    l.autorizacion_lab,
    l.nota_lab,
    l.dias_atraso_lab,
    l.motivo_dias_atraso_lab,
    l.evidencia_envio_recepcion,
    l.envio_informes,
    l.created_by,
    l.created_at,
    l.updated_at,
    l.updated_by,
    l.activo,
    c.fecha_solicitud_com,
    c.fecha_entrega_com,
    c.evidencia_solicitud_envio,
    c.dias_atraso_envio_coti,
    c.motivo_dias_atraso_com,
    a.numero_factura,
    a.estado_pago,
    a.estado_autorizar,
    a.nota_admin,
    c.costo_servicio,
    a.orden_servicio,        -- Added
    a.numero_valorizacion    -- Added
FROM public.programacion_lab l
LEFT JOIN public.programacion_comercial c ON l.id = c.programacion_id
LEFT JOIN public.programacion_administracion a ON l.id = a.programacion_id;

-- 3. Set security invoker and permissions
ALTER VIEW public.cuadro_control SET (security_invoker = true);
GRANT SELECT ON public.cuadro_control TO anon, authenticated, service_role, postgres;

-- 4. Notify PostgREST to reload schema
NOTIFY pgrst, 'reload schema';
