# 014 — Los códigos repetidos de Mascolab son análisis distintos y se quedan

**Fecha:** 2026-11-09 · **Decide:** el usuario, con la explicación de A3.

Mascolab es una asociación y cada análisis tiene dos técnicas con precio propio: Punto Final y Tiempo
Real. El sufijo del código las separa: `2457` es Punto Final ($157.000) y `2457-1` es Tiempo Real
($224.000). Además hay códigos con el mismo nombre y precio para especies distintas, como `2457`
(canino) y `2461` (ambos).

**Consecuencia:** no son duplicados. No se fusionan ni se borran, y una limpieza del catálogo no los
debe tocar. Si el cliente nombra el análisis sin decir la técnica, el bot ofrece las opciones con su
precio; si da el código o la técnica, va directo a esa.
