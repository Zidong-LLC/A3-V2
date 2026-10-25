-- 033: Usuarios individuales del personal de A3, con perfil (cierre de la versión 1,
-- pedido de A3 vía Laberit, «Perfiles Plataforma.docx», 2026-10-19).
-- Hasta acá todo el personal entraba con un único usuario del .env; ese usuario sigue
-- existiendo como Administrador de respaldo, así nadie queda afuera si esta tabla falla.
-- Solo agrega tablas: no modifica ninguna existente.

CREATE TABLE IF NOT EXISTS dashboard_users (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    username      text NOT NULL UNIQUE,
    full_name     text NOT NULL DEFAULT '',
    email         text,
    role          text NOT NULL CHECK (role IN ('administrador', 'recepcion', 'digitacion',
                                                'auxiliar_administrativa', 'procesamiento')),
    password_hash text NOT NULL,
    is_active     boolean NOT NULL DEFAULT true,
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    last_login_at timestamptz
);

COMMENT ON TABLE dashboard_users IS
    'Personal de A3 con acceso a la plataforma interna; el perfil define los módulos (app/permissions.py)';

-- Historial de cambios en datos maestros: quién cambió qué y cuándo. Solo se inserta;
-- nunca se edita ni se borra.
CREATE TABLE IF NOT EXISTS audit_log (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    entity      text NOT NULL,           -- client | courier | catalog | user | import
    entity_id   text,
    action      text NOT NULL,           -- create | update | activate | deactivate | delete | import
    changes     jsonb NOT NULL DEFAULT '{}'::jsonb,
    username    text NOT NULL DEFAULT '',
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS audit_log_entity_idx ON audit_log (entity, entity_id, created_at DESC);

COMMENT ON TABLE audit_log IS
    'Historial de altas, cambios, activaciones y bajas en clientes, motorizados, precios y usuarios';

-- Acceso solo desde el servidor (service role): sin políticas públicas.
ALTER TABLE dashboard_users ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;
