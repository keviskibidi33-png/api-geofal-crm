ALTER TABLE public.programacion_comercial
ADD COLUMN IF NOT EXISTS costo_servicio NUMERIC(12,2);

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
    c.costo_servicio
FROM public.programacion_lab l
LEFT JOIN public.programacion_comercial c ON l.id = c.programacion_id
LEFT JOIN public.programacion_administracion a ON l.id = a.programacion_id;
