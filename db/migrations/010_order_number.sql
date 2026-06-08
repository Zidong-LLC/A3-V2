-- Ejecutar en el SQL Editor de Supabase
-- Numero de orden legible y secuencial para las solicitudes (requests).
-- Cada INSERT genera A3-00001, A3-00002, ... de forma automatica y atomica.

CREATE SEQUENCE IF NOT EXISTS request_order_seq START 1;

ALTER TABLE requests
    ADD COLUMN IF NOT EXISTS order_number text UNIQUE
    DEFAULT ('A3-' || lpad(nextval('request_order_seq')::text, 5, '0'));

COMMENT ON COLUMN requests.order_number IS
    'Numero de orden legible (A3-00042) generado por la secuencia request_order_seq.';
