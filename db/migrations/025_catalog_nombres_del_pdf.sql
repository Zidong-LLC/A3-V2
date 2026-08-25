-- 025 — Restaura en los nombres los SINÓNIMOS que trae el PDF del portafolio
--
-- Auditoría del catálogo (2026-08-25, ERR-147): los códigos y los precios de la base
-- coinciden 100% con el PDF "A3 - Catálogo 2025", pero dos nombres se cargaron recortados
-- y perdieron la palabra con que el cliente pide la prueba.
--
-- Caso real: un cliente escribe "moquillo" —como se dice en Colombia— y el único análisis
-- con esa palabra en el nombre es el 2306 del Convenio LMV ($124.000). El Distemper propio
-- de A3 (2004, $45.000) quedaba invisible porque su nombre perdió el "o Moquillo Canino"
-- que el PDF sí trae (pág. 6). Con el nombre completo, el agente ofrece los dos y el
-- cliente elige — que es la regla de dinero del proyecto.
--
-- Sin efecto sobre precios, códigos ni facturación: solo texto del nombre.
-- REQUIERE OK EXPLÍCITO DEL USUARIO ANTES DE EJECUTARSE (toca la base real).

UPDATE catalog_tests
   SET name = 'Distemper Canino o Moquillo Canino (Antígeno)'
 WHERE code = '2004' AND name = 'Distemper Canino (Antígeno)';

UPDATE catalog_tests
   SET name = 'Distemper Canino o Moquillo Canino + Adenovirus (Antígeno)'
 WHERE code = '2017' AND name = 'Distemper Canino + Adenovirus (Antígeno)';

-- Verificación:
--   SELECT code, name FROM catalog_tests WHERE code IN ('2004','2017','2306') ORDER BY code;
