-- 032: Aviso al motorizado por Chatwoot (decision del usuario 2026-08-31; pedido de A3 en
-- las llamadas 1, 2 y 4 y acordado en la 9: "cuentas del personal y motorizados en el chat").
-- Cada motorizado puede tener vinculada SU conversacion de Chatwoot; al asignarle o
-- reasignarle una recogida, ahi le llega el aviso. Sin vinculo, no se avisa (como hoy).

ALTER TABLE couriers ADD COLUMN IF NOT EXISTS chatwoot_conversation_id text;

COMMENT ON COLUMN couriers.chatwoot_conversation_id IS
    'Conversacion de Chatwoot del motorizado para avisos de asignacion; vacio = sin avisos';
