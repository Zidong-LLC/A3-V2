-- 029: Cartera — saldo pendiente y pagado por factura.
-- Ejecutar con tools/scripts/apply_supabase_migration.py o el SQL Editor de Supabase.
--
-- Por qué: `invoices_cache` ya guarda estado y total, pero no cuánto queda por cobrar.
-- Alegra expone `balance` (saldo) y `totalPaid` (abonado) en cada factura; sin eso la
-- cartera solo podría decir «pagada / sin pagar», no cuánto se debe ni desde cuándo.
--
-- En la cuenta real de A3 hay 660 facturas: 126 `open` y 534 `closed`.

ALTER TABLE invoices_cache
    ADD COLUMN IF NOT EXISTS balance bigint NOT NULL DEFAULT 0;

ALTER TABLE invoices_cache
    ADD COLUMN IF NOT EXISTS total_paid bigint NOT NULL DEFAULT 0;

COMMENT ON COLUMN invoices_cache.balance IS 'Saldo pendiente de cobro (Alegra: balance).';
COMMENT ON COLUMN invoices_cache.total_paid IS 'Monto ya abonado (Alegra: totalPaid).';

-- La cartera se consulta por «lo que falta cobrar»: índice sobre las que tienen saldo.
CREATE INDEX IF NOT EXISTS idx_invoices_cache_balance
    ON invoices_cache (client_nit, due_date) WHERE balance > 0;
