-- Ejecutar en el SQL Editor de Supabase
-- Vista de "informes" sobre el espejo Anarvet (decisión 013): un informe = un paciente
-- (codigo) en una fecha de solicitud, con el resumen de sus exámenes/analitos.
-- Existe para que el dashboard liste y pagine por informe del lado servidor
-- (misma idea que 007_service_order_view): agrupar 27k analitos/semana en Python
-- obligaría a traer todo el rango en cada carga de página.

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
    max(fec_val)                                                AS ultima_validacion
FROM anarvet_results
GROUP BY
    codigo, fecha_solicitud, cod_cliente, nombre_cliente,
    nombre_propietario, mascota, especie, raza, genero;
