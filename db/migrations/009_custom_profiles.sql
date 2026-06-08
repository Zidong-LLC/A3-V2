-- Ejecutar en el SQL Editor de Supabase
-- Tabla de perfiles personalizados por cliente

CREATE TABLE IF NOT EXISTS client_custom_profiles (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id uuid REFERENCES clients(id) ON DELETE CASCADE,
    name text NOT NULL,
    items_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    created_at timestamptz DEFAULT now(),
    created_by text
);

CREATE INDEX IF NOT EXISTS idx_custom_profiles_client ON client_custom_profiles (client_id);

ALTER TABLE client_custom_profiles ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Dashboard can manage custom profiles" ON client_custom_profiles
    FOR ALL USING (true) WITH CHECK (true);