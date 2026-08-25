-- 027 — La vista anarvet_informes expone cuántos analitos están VALIDADOS
--
-- Anarvet no entrega un campo de estado, pero `fec_val` lo deja derivar: un informe con
-- todos sus analitos validados está listo; con algunos sin validar, está en proceso.
-- Medido sobre datos reales (2026-08-25): de 531 informes, 473 completos, 36 parciales y
-- 22 sin validar — o sea, el estado existe y vale la pena mostrarlo.
--
-- La vista ya traía `ultima_validacion` (el max), que solo dice "algo se validó". Falta el
-- CONTEO para distinguir "parcial" de "listo". No se toca ninguna tabla.
--
-- La columna nueva va AL FINAL a propósito: CREATE OR REPLACE VIEW solo admite agregar
-- columnas al final; intercalarla obligaría a un DROP, que rompería cualquier vista o
-- permiso que dependa de esta.

CREATE OR REPLACE VIEW anarvet_informes AS
SELECT
    codigo,
    fecha_solicitud,
    cod_cliente,
    nombre_cliente,
    nombre_propietario,
    mascota,
    especie,
    raza,
    genero,
    count(*)                                                    AS analitos,
    count(DISTINCT examen_cod)                                  AS examenes,
    string_agg(DISTINCT examen_cod, ', ' ORDER BY examen_cod)   AS examen_codigos,
    max(fec_val)                                                AS ultima_validacion,
    count(*) FILTER (WHERE fec_val IS NOT NULL)                 AS analitos_validados
FROM anarvet_results
GROUP BY
    codigo, fecha_solicitud, cod_cliente, nombre_cliente,
    nombre_propietario, mascota, especie, raza, genero;

COMMENT ON VIEW anarvet_informes IS
    'Un informe = un paciente en una fecha. analitos_validados permite derivar el estado.';

-- Verificación:
--   SELECT codigo, analitos, analitos_validados FROM anarvet_informes LIMIT 5;
