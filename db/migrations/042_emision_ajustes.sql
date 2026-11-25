-- 042: Modo de emisión a la DIAN elegido por A3 desde Facturación (decisión 017, 2026-11-25).
-- Una sola fila: 'manual' (solo el botón de cada pedido), 'clientes' (automática solo para los
-- clientes elegidos, para probar) o 'todos'. Solo agrega una tabla. Nace en 'manual'.

CREATE TABLE IF NOT EXISTS emision_ajustes (
    id          smallint PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    modo        text NOT NULL DEFAULT 'manual' CHECK (modo IN ('manual', 'clientes', 'todos')),
    client_ids  uuid[] NOT NULL DEFAULT '{}',
    updated_at  timestamptz NOT NULL DEFAULT now(),
    updated_by  text
);
INSERT INTO emision_ajustes (id) VALUES (1) ON CONFLICT (id) DO NOTHING;

ALTER TABLE emision_ajustes ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON emision_ajustes FROM anon, authenticated;
