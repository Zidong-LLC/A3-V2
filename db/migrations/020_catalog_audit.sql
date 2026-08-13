-- Ejecutar en el SQL Editor de Supabase
-- Auditoria de cambios del CATALOGO (precios y etiqueta de especie).
--
-- Hasta ahora el catalogo era de solo lectura desde la plataforma: cambiar un precio exigia
-- SQL a mano. A3 pidio poder editarlo el 07/04 (el pendiente mas antiguo) y marcar la especie
-- exclusiva el 28/07. Editar un precio mueve plata, asi que cada cambio queda registrado con
-- el valor anterior y quien lo hizo.
--
-- No se reusa request_events porque su request_id es NOT NULL: un cambio de catalogo no
-- pertenece a ninguna orden.
--
-- Tabla NUEVA, no toca nada existente (mismo patron que 009, 013, 014, 018 y 019).

CREATE TABLE IF NOT EXISTS catalog_audit (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    -- 'catalog_tests' | 'catalog_profiles'
    source_table text NOT NULL,
    code        text NOT NULL,
    -- Valores ANTES y DESPUES, solo de los campos que cambiaron.
    before_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    after_json  jsonb NOT NULL DEFAULT '{}'::jsonb,
    changed_by  text,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_catalog_audit_item
    ON catalog_audit (source_table, code, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_catalog_audit_fecha
    ON catalog_audit (created_at DESC);

COMMENT ON TABLE catalog_audit IS
    'Historial de cambios de precio y especie del catalogo hechos desde la plataforma.';
