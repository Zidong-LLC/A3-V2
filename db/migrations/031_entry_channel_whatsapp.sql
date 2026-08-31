-- 031: El canal de entrada deja de mentir — se admiten chatwoot y whatsapp.
-- Ejecutar con tools/scripts/apply_supabase_migration.py o el SQL Editor de Supabase.
--
-- El CHECK original de requests.entry_channel solo admite 'telegram', así que TODA orden
-- entrada por Chatwoot quedaba reetiquetada como 'telegram' (ERR de la auditoría del canal:
-- "el CHECK de requests.entry_channel solo admite telegram"). Es el tapón #1 para conectar
-- el número de WhatsApp de A3 (llamada 9: la secuencia de cierre acordada).
--
-- 'manual' y 'portal' se agregan por los caminos administrativos existentes y futuros.
-- Idempotente: DROP IF EXISTS + ADD.

ALTER TABLE requests DROP CONSTRAINT IF EXISTS requests_entry_channel_check;
ALTER TABLE requests ADD CONSTRAINT requests_entry_channel_check
    CHECK (entry_channel IN ('telegram', 'chatwoot', 'whatsapp', 'manual', 'portal'));

COMMENT ON COLUMN requests.entry_channel IS
    'Canal por el que entró la orden: telegram | chatwoot (web) | whatsapp (vía Chatwoot) | manual | portal';
