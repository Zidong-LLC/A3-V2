-- Ejecutar en el SQL Editor de Supabase
-- Numero de orden legible que REINICIA por año: A3-2026-001, A3-2026-002, ...
-- y en enero del año siguiente vuelve a A3-2027-001.
-- Reemplaza el DEFAULT global (secuencia) de la migracion 010.

-- Contador por año (atomico via UPSERT con RETURNING).
CREATE TABLE IF NOT EXISTS order_number_counters (
    year     int PRIMARY KEY,
    last_seq int NOT NULL DEFAULT 0
);

CREATE OR REPLACE FUNCTION next_order_number() RETURNS text AS $$
DECLARE
    y   int := EXTRACT(YEAR FROM (now() AT TIME ZONE 'America/Bogota'))::int;
    seq int;
BEGIN
    INSERT INTO order_number_counters (year, last_seq)
        VALUES (y, 1)
        ON CONFLICT (year) DO UPDATE
            SET last_seq = order_number_counters.last_seq + 1
        RETURNING last_seq INTO seq;
    RETURN 'A3-' || y::text || '-' || lpad(seq::text, 3, '0');
END;
$$ LANGUAGE plpgsql;

-- Nuevas ordenes usan el formato anual. Las existentes conservan su numero.
ALTER TABLE requests ALTER COLUMN order_number SET DEFAULT next_order_number();

COMMENT ON FUNCTION next_order_number() IS
    'Genera A3-<año>-<secuencial 3 dígitos> reiniciando el contador cada año (zona America/Bogota).';
