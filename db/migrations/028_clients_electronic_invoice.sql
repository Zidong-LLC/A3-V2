-- 028: Facturación electrónica por cliente (bloqueante para facturar en la cuenta real).
-- Ejecutar con tools/scripts/apply_supabase_migration.py o el SQL Editor de Supabase.
--
-- Por qué: hasta ahora TODO se facturaba igual y en la cuenta real de A3 varias facturas
-- salían a «Consumidor Final» (contacto id=1, identificación 222222222222) con el nombre de
-- la veterinaria escrito a mano en las notas. Este campo decide, por cliente, si la factura
-- se emite a su NIT y razón social o al Consumidor Final con la nota.
--
-- OJO: `billing_type` NO sirve para esto — es contado/crédito, otra cosa.
--
-- Default `true`: la mayoría de los clientes sí lleva factura electrónica. Los que no,
-- se marcan con tools/scripts/import_factura_electronica.py a partir del Excel
-- «Alegra - Terceros v2 Actualizado.xlsx», columna «Factura electrónica» = NO.

ALTER TABLE clients
    ADD COLUMN IF NOT EXISTS electronic_invoice boolean NOT NULL DEFAULT true;

-- Texto que va al campo `anotation` de la factura de Alegra cuando el cliente NO lleva
-- factura electrónica. Si queda vacío se usa el nombre de la veterinaria.
ALTER TABLE clients
    ADD COLUMN IF NOT EXISTS invoice_note text;

COMMENT ON COLUMN clients.electronic_invoice IS
    'true: se factura al NIT del cliente. false: va a Consumidor Final con invoice_note en las notas.';
COMMENT ON COLUMN clients.invoice_note IS
    'Nota para la factura cuando electronic_invoice es false (médico o veterinaria). Si es NULL se usa clinic_name.';

CREATE INDEX IF NOT EXISTS idx_clients_electronic_invoice
    ON clients (electronic_invoice) WHERE electronic_invoice = false;
