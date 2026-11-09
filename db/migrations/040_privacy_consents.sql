-- 040: Evidencia de la autorización de datos en WhatsApp (propuesta del 2026-09-28).
-- Cada fila es un hecho y no se edita: se le preguntó, aceptó o rechazó. El último hecho de
-- un contacto decide si el bot puede atenderlo. Solo agrega una tabla.

CREATE TABLE IF NOT EXISTS privacy_consents (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at       timestamptz NOT NULL DEFAULT now(),
    contact_key      text NOT NULL,                 -- +573001234567
    channel          text NOT NULL,
    external_chat_id text NOT NULL,
    event            text NOT NULL CHECK (event IN ('asked', 'accepted', 'rejected')),
    response_text    text,                          -- lo que respondió el contacto, tal cual
    policy_version   text NOT NULL,
    policy_url       text NOT NULL
);

CREATE INDEX IF NOT EXISTS privacy_consents_contact_idx ON privacy_consents (contact_key, created_at DESC);

COMMENT ON TABLE privacy_consents IS
    'Evidencia de autorización de tratamiento de datos por WhatsApp; solo se agregan filas';

ALTER TABLE privacy_consents ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON privacy_consents FROM anon, authenticated;
