-- 041: Pagos en línea con Wompi, uno por pedido (propuesta del 2026-09-28).
-- El link de Wompi no admite referencia propia: el pago se cruza por `payment_link_id`,
-- que llega en cada evento. Solo agrega una tabla.

CREATE TABLE IF NOT EXISTS pedido_payments (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    pedido_id       uuid NOT NULL REFERENCES pedidos(id),
    payment_link_id text NOT NULL UNIQUE,
    url             text NOT NULL,
    amount_in_cents bigint NOT NULL CHECK (amount_in_cents > 0),
    status          text NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'approved', 'declined', 'voided', 'error', 'mismatch')),
    transaction_id  text,
    raw             jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS pedido_payments_pedido_idx ON pedido_payments (pedido_id);

ALTER TABLE pedido_payments ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON pedido_payments FROM anon, authenticated;
