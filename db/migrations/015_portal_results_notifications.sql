-- 015: Portal Web — resultados en PDF y notificaciones.
-- Solo tablas NUEVAS (patrón de 013/014): no modifica tablas núcleo.
-- Aplicar con tools/scripts/apply_supabase_migration.py o el SQL Editor de Supabase.

CREATE TABLE IF NOT EXISTS lab_results (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id uuid NOT NULL REFERENCES clients(id),
    request_id uuid REFERENCES requests(id),
    order_number text,
    patient_name text,
    owner_name text,
    exam_name text,
    pdf_path text NOT NULL,
    published boolean NOT NULL DEFAULT false,
    published_at timestamptz,
    uploaded_by text,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_lab_results_client
    ON lab_results (client_id, published, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_lab_results_order
    ON lab_results (order_number);

CREATE TABLE IF NOT EXISTS portal_notifications (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id uuid NOT NULL REFERENCES clients(id),
    type text NOT NULL,              -- 'request_created' | 'result_published'
    title text NOT NULL,
    body text,
    request_id uuid,
    result_id uuid,
    read_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_portal_notifications_client
    ON portal_notifications (client_id, read_at, created_at DESC);

-- RLS habilitado SIN políticas permisivas: el backend usa service role (la bypasa);
-- anon/authenticated no ven nada. Defensa en profundidad.
ALTER TABLE lab_results ENABLE ROW LEVEL SECURITY;
ALTER TABLE portal_notifications ENABLE ROW LEVEL SECURITY;

-- Bucket privado de Storage para los PDFs de resultados.
INSERT INTO storage.buckets (id, name, public)
VALUES ('lab-results', 'lab-results', false)
ON CONFLICT (id) DO NOTHING;
