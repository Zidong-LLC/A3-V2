-- 039 — La clave anónima de Supabase deja de poder leer y escribir la base (ERR-187)
--
-- ⚠ PREPARADA, NO APLICADA: espera el OK del usuario (cambia permisos de producción).
--
-- Hallazgo del 2026-10-28: 24 tablas de `public` sin RLS (clients, requests, pedidos,
-- telegram_sessions, conversation_stage_events, liveconnect_messages, lab_samples…) y 7
-- políticas `USING (true)` para TODOS los roles. Supabase le da a `anon` y `authenticated`
-- todos los permisos sobre lo que se crea en `public`, así que con la clave anónima del
-- proyecto cualquiera podía leer y modificar la base entera. Hoy lo mitiga que esa clave no
-- se usa en ningún lado del proyecto ni llega a ningún navegador — pero es «pública» por
-- diseño de Supabase y no hay que depender de que nunca circule.
--
-- La plataforma usa SOLO `service_role` (dashboard, portal, bot, crons): no se rompe nada.
-- Storage (los PDF) vive en su propio esquema y no se toca. Revertir = volver a dar GRANT.

REVOKE ALL ON ALL TABLES IN SCHEMA public FROM anon, authenticated;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM anon, authenticated;
REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM anon, authenticated;

-- Y para lo que se cree de acá en adelante (las migraciones corren como `postgres`).
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public REVOKE ALL ON TABLES FROM anon, authenticated;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public REVOKE ALL ON SEQUENCES FROM anon, authenticated;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public REVOKE EXECUTE ON FUNCTIONS FROM anon, authenticated;

-- Verificación (todo false):
--   SELECT has_table_privilege('anon', 'clients', 'SELECT'),
--          has_table_privilege('anon', 'requests', 'INSERT'),
--          has_table_privilege('authenticated', 'telegram_sessions', 'UPDATE');
