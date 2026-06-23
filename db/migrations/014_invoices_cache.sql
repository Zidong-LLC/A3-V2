-- Ejecutar en el SQL Editor de Supabase
-- Cache local de facturas de Alegra para el modulo "Facturacion" del dashboard.
-- NO modifica tablas existentes (alineado con decisiones 006 y 009): es una tabla nueva,
-- igual que client_custom_profiles y dashboard_column_prefs. La fuente de verdad sigue
-- siendo Alegra; esta tabla es solo cache para listados, filtros y metricas rapidas.

CREATE TABLE IF NOT EXISTS invoices_cache (
    alegra_invoice_id text PRIMARY KEY,
    number text,
    client_nit text,
    client_name text,
    document_type text,
    number_template text,
    status text,
    subtotal bigint NOT NULL DEFAULT 0,
    tax bigint NOT NULL DEFAULT 0,
    total bigint NOT NULL DEFAULT 0,
    is_stamped boolean NOT NULL DEFAULT false,
    invoice_date date,
    due_date date,
    request_id text,
    origin text,
    raw jsonb NOT NULL DEFAULT '{}'::jsonb,
    synced_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_invoices_cache_date ON invoices_cache (invoice_date DESC);
CREATE INDEX IF NOT EXISTS idx_invoices_cache_status ON invoices_cache (status);
CREATE INDEX IF NOT EXISTS idx_invoices_cache_nit ON invoices_cache (client_nit);

ALTER TABLE invoices_cache ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Dashboard can manage invoices cache" ON invoices_cache
    FOR ALL USING (true) WITH CHECK (true);
