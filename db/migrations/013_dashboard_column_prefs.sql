-- Ejecutar en el SQL Editor de Supabase
-- Preferencias de columnas del dashboard por usuario y por tabla.
-- Habilita la sincronizacion "entre dispositivos" del selector de columnas.

CREATE TABLE IF NOT EXISTS dashboard_column_prefs (
    user_key text NOT NULL,
    table_id text NOT NULL,
    prefs jsonb NOT NULL DEFAULT '{}'::jsonb,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_key, table_id)
);

ALTER TABLE dashboard_column_prefs ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Dashboard can manage column prefs" ON dashboard_column_prefs
    FOR ALL USING (true) WITH CHECK (true);
