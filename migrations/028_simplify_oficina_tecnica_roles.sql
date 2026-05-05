-- Simplify Oficina Técnica role catalog by collapsing legacy variants into the base role.
-- Existing user_permission_overrides preserve the extra access for the affected users.
BEGIN;

UPDATE perfiles
SET role = 'oficina_tecnica'
WHERE role IN (
    'oficina_tecnica_humedad',
    'oficina_tecnica_humedad_tipificador',
    'oficina_tecnica_sup'
);

DELETE FROM role_definitions
WHERE role_id IN (
    'oficina_tecnica_humedad',
    'oficina_tecnica_humedad_tipificador',
    'oficina_tecnica_sup'
);

COMMIT;
