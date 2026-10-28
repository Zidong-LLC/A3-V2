-- 037 — Los informes de Anarvet precalculados: las pantallas del espejo volvían a andar (ERR-187)
--
-- El problema (medido el 2026-10-28): la vista `anarvet_informes` reagrupa TODA la tabla
-- `anarvet_results` en cada consulta. El espejo arrancó en agosto y crece ~100.000 analitos
-- por mes (271.453 hoy, 207 MB por el JSON crudo de cada fila). Postgres recorre la tabla
-- entera en orden de paciente para poder agrupar —aunque se filtre por fecha— y el rol de
-- la API corta a los 8 s (statement_timeout del authenticator):
--   - Resultados → Anarvet: hasta la página 1 se corta por statement timeout.
--   - Resultados → Anarvet → Clientes: el conteo por cliente se corta desde la página 10.
--   Y cada mes que pasa, peor.
--
-- La solución: una vista MATERIALIZADA con los 7.802 informes ya agrupados e indexados,
-- que el sync de Anarvet refresca al terminar (cada hora en horario laboral). Leer pasa de
-- ">8 s / error" a ~1 s (medido). No se toca ninguna tabla ni ningún dato: la vista original
-- queda igual y el código cae a ella si esta todavía no existe.
--
-- Seguridad: una vista materializada NO tiene RLS. Se le quitan los permisos a anon y
-- authenticated (Supabase se los da por defecto a todo lo nuevo de `public`): solo la lee la
-- plataforma con la service role, igual que hoy.

CREATE MATERIALIZED VIEW IF NOT EXISTS anarvet_informes_mat AS
    SELECT * FROM anarvet_informes;

-- Única: la exige REFRESH ... CONCURRENTLY (así refrescar no bloquea a quien está leyendo).
CREATE UNIQUE INDEX IF NOT EXISTS idx_anarvet_informes_mat_clave ON anarvet_informes_mat
    (codigo, fecha_solicitud, cod_cliente, nombre_cliente, nombre_propietario, mascota, especie, raza, genero);
CREATE INDEX IF NOT EXISTS idx_anarvet_informes_mat_fecha ON anarvet_informes_mat (fecha_solicitud DESC, codigo);
CREATE INDEX IF NOT EXISTS idx_anarvet_informes_mat_cliente ON anarvet_informes_mat (cod_cliente);

REVOKE ALL ON anarvet_informes_mat FROM anon, authenticated;
GRANT SELECT ON anarvet_informes_mat TO service_role;

-- La llama el sync al terminar. Con su propio tope de tiempo: el de la API (8 s) no alcanza
-- para reagrupar la tabla entera, que es justamente lo que se evita hacer en cada lectura.
CREATE OR REPLACE FUNCTION refrescar_anarvet_informes()
RETURNS void
LANGUAGE sql
SECURITY DEFINER
SET search_path = public
SET statement_timeout = '120s'
AS $$
    REFRESH MATERIALIZED VIEW CONCURRENTLY anarvet_informes_mat;
$$;

REVOKE ALL ON FUNCTION refrescar_anarvet_informes() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION refrescar_anarvet_informes() TO service_role;

-- Informes por código de cliente, agrupado en la base (PostgREST no expone GROUP BY y
-- Supabase tiene los agregados apagados). Misma semántica que antes: una fila = un informe.
CREATE OR REPLACE FUNCTION anarvet_informes_por_cliente()
RETURNS TABLE (cod_cliente text, informes bigint)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
    SELECT cod_cliente::text, count(*) FROM anarvet_informes_mat GROUP BY cod_cliente;
$$;

REVOKE ALL ON FUNCTION anarvet_informes_por_cliente() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION anarvet_informes_por_cliente() TO service_role;

-- Verificación:
--   SELECT count(*) FROM anarvet_informes_mat;                        -- 7.802 al aplicarla
--   SELECT * FROM anarvet_informes_por_cliente() ORDER BY informes DESC LIMIT 5;
--   SELECT refrescar_anarvet_informes();
