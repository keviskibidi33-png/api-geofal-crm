-- Migration: Add control_probetas permissions to admin roles
UPDATE role_definitions
SET permissions = jsonb_set(permissions, '{control_probetas}', '{"read": true, "write": true, "delete": true}'::jsonb, true)
WHERE role_id IN ('admin', 'admin_general');
