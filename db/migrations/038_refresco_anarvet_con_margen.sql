-- 038 — Más margen para refrescar los informes de Anarvet (ERR-187)
--
-- Al aplicar la 037 (2026-10-28) el refresco tardó 25,5 s con 271.453 analitos. El espejo
-- crece ~100.000 analitos por mes, así que en pocos meses pasaría el tope de 120 s que trae
-- la función y el sync dejaría de actualizar las pantallas sin que nadie lo note (el sync
-- solo deja un warning). REFRESH ... CONCURRENTLY no bloquea a quien lee: subir el tope no
-- frena ninguna pantalla.

ALTER FUNCTION refrescar_anarvet_informes() SET statement_timeout = '600s';

-- Verificación:
--   SELECT proconfig FROM pg_proc WHERE proname = 'refrescar_anarvet_informes';
