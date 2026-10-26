-- 035: Panel de sistema para el responsable técnico (decisión del usuario, 2026-10-26).
-- `system_events` guarda lo que hasta hoy solo salía por el Telegram de avisos o por el log:
-- errores por componente, cada llamada al modelo (tokens y duración) y cada turno del bot.
-- `system_costs` guarda el costo mensual fijo de los servicios que no exponen API de
-- facturación (Render, VPS de Chatwoot, Alegra…), cargado a mano desde el panel.
-- Solo agrega tablas: no modifica ninguna existente.

CREATE TABLE IF NOT EXISTS system_events (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at timestamptz NOT NULL DEFAULT now(),
    kind       text NOT NULL CHECK (kind IN ('error', 'llm', 'turn')),
    component  text NOT NULL,
    level      text NOT NULL DEFAULT 'info' CHECK (level IN ('info', 'warning', 'error')),
    message    text NOT NULL DEFAULT '',
    context    text NOT NULL DEFAULT '',
    details    jsonb NOT NULL DEFAULT '{}'::jsonb,
    chat_id    text
);
CREATE INDEX IF NOT EXISTS system_events_created_idx ON system_events (created_at DESC);
CREATE INDEX IF NOT EXISTS system_events_kind_created_idx ON system_events (kind, created_at DESC);

CREATE TABLE IF NOT EXISTS system_costs (
    service     text PRIMARY KEY,
    label       text NOT NULL,
    monthly_usd numeric(10, 2) NOT NULL DEFAULT 0,
    note        text NOT NULL DEFAULT '',
    updated_at  timestamptz NOT NULL DEFAULT now()
);
INSERT INTO system_costs (service, label, note) VALUES
    ('render',   'Render (servidor)',          'Plan Standard'),
    ('supabase', 'Supabase (base y PDFs)',     'Plan del proyecto'),
    ('chatwoot', 'Chatwoot (VPS / EasyPanel)', 'Servidor propio'),
    ('whatsapp', 'WhatsApp Business (Meta)',   'Conversaciones iniciadas por A3'),
    ('alegra',   'Alegra',                     'Suscripción de A3'),
    ('dominio',  'Dominio y otros',            '')
ON CONFLICT (service) DO NOTHING;
