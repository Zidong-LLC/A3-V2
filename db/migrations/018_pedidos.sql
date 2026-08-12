-- Ejecutar en el SQL Editor de Supabase
-- Jerarquia PEDIDO -> ORDENES -> ANALISIS (decision 011).
--
-- El PEDIDO es lo que se factura: agrupa varias ordenes (una por paciente) cargadas en la
-- misma sesion, lleva UNA forma de pago y genera UNA factura al final. Hasta ahora cada
-- orden se facturaba por separado, asi que un cliente con tres pacientes recibia tres
-- facturas y le preguntaban el pago tres veces.
--
-- NO modifica ninguna tabla existente salvo agregar una columna NULLABLE a requests
-- (alineado con la decision 006). Mismo patron que 009, 013 y 014.
-- Es retrocompatible: con pedido_id NULL, una orden se comporta exactamente como hoy.

-- Contador anual propio: P-2026-001, P-2026-002, ... y en enero vuelve a P-2027-001.
-- No se reusa order_number_counters porque su PK es (year) y ya la ocupan las ordenes.
CREATE TABLE IF NOT EXISTS pedido_number_counters (
    year     int PRIMARY KEY,
    last_seq int NOT NULL DEFAULT 0
);

CREATE OR REPLACE FUNCTION next_pedido_number() RETURNS text AS $$
DECLARE
    y   int := EXTRACT(YEAR FROM (now() AT TIME ZONE 'America/Bogota'))::int;
    seq int;
BEGIN
    INSERT INTO pedido_number_counters (year, last_seq)
        VALUES (y, 1)
        ON CONFLICT (year) DO UPDATE
            SET last_seq = pedido_number_counters.last_seq + 1
        RETURNING last_seq INTO seq;
    RETURN 'P-' || y::text || '-' || lpad(seq::text, 3, '0');
END;
$$ LANGUAGE plpgsql;

CREATE TABLE IF NOT EXISTS pedidos (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id        uuid REFERENCES clients(id),
    pedido_number    text UNIQUE DEFAULT next_pedido_number(),
    -- La forma de pago es del PEDIDO, no de cada orden: se pregunta una sola vez al cerrar.
    payment_method   text,
    -- abierto: admite mas ordenes | cerrado: ya no | facturado: con factura emitida.
    status           text NOT NULL DEFAULT 'abierto',
    entry_channel    text,
    -- Chat que abrio el pedido: permite recuperar el pedido abierto de una conversacion y
    -- alimenta el barrido por inactividad (decision 011).
    external_chat_id text,
    alegra_invoice_id text,
    created_at       timestamptz NOT NULL DEFAULT now(),
    -- Se toca con cada orden agregada; es la base del cierre por inactividad.
    updated_at       timestamptz NOT NULL DEFAULT now(),
    closed_at        timestamptz,
    CONSTRAINT pedidos_status_check CHECK (status IN ('abierto', 'cerrado', 'facturado'))
);

-- NULLABLE a proposito: las ordenes historicas y las que entran por el portal no tienen
-- pedido y deben seguir funcionando igual.
ALTER TABLE requests ADD COLUMN IF NOT EXISTS pedido_id uuid REFERENCES pedidos(id);

CREATE INDEX IF NOT EXISTS idx_requests_pedido ON requests (pedido_id);
CREATE INDEX IF NOT EXISTS idx_pedidos_client ON pedidos (client_id, created_at DESC);
-- Para el barrido de pedidos abandonados: status + antiguedad.
CREATE INDEX IF NOT EXISTS idx_pedidos_abiertos ON pedidos (status, updated_at)
    WHERE status = 'abierto';

COMMENT ON TABLE pedidos IS
    'Pedido: agrupa las ordenes de una sesion de carga. Es la unidad que se factura (decision 011).';
COMMENT ON COLUMN requests.pedido_id IS
    'Pedido al que pertenece la orden. NULL en ordenes previas a la decision 011 y en las del portal.';
