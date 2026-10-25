# Capacitación de la plataforma A3

Todo lo necesario para la reunión de puesta en marcha y la capacitación de 2 horas del
equipo de A3 (octubre de 2026).

| Archivo | Para quién | Qué es |
|---|---|---|
| `Guia_Uso_Plataforma_A3.pdf` | Equipo de A3 | Guía de uso paso a paso (15 páginas, capturas reales, una página por sección y «Qué hacer si…»). Se entrega al terminar la capacitación. |
| `Guion_Capacitacion_A3.pdf` | Quien dicta | Reunión de puesta en marcha (≈ 45 min), agenda cronometrada de 2 h, qué mostrar y decir en cada bloque, práctica por perfil, plan B y checklist antes/después. Documento interno. |
| `ejemplos/clientes_demo_carga_masiva.csv` | Demo | 3 veterinarias ficticias (Bogotá, Soacha, Chía) con su motorizado. Es el caso «Veterinaria Demo Patitas» que recorre toda la sesión. |
| `ejemplos/precios_demo_actualizacion.csv` | Demo | 5 productos reales del catálogo con precio nuevo (4 cambian, 1 igual). **Si se aplica, los precios cambian de verdad.** |
| `ejemplos/precios_demo_restaurar.csv` | Demo | Devuelve esos 5 precios a su valor original. |
| `video/Recorrido_Plataforma_A3_2026-10-09.mp4` | Plan B | Recorrido grabado de la plataforma (3:45 min) por si falla la conexión en vivo. |
| `fuentes/` | Mantenimiento | HTML de la guía y del guion, y las 32 capturas (`fuentes/img/`). |

## Regenerar

```bash
# Capturas nuevas (app en solo lectura: lee datos reales, no escribe nada)
python tools/scripts/capturas_guia_a3.py

# PDFs
python tools/scripts/html_a_pdf.py capacitacion/fuentes/guia-uso-plataforma-a3.html capacitacion/Guia_Uso_Plataforma_A3.pdf "Guía de uso · Plataforma A3 Laboratorio Veterinario · Octubre de 2026"
python tools/scripts/html_a_pdf.py capacitacion/fuentes/guion-capacitacion-a3.html capacitacion/Guion_Capacitacion_A3.pdf "Guion de la capacitación · Plataforma A3 · Documento interno"

# Video (sale en output/video/; copiarlo acá)
python tools/scripts/video_plataforma_a3.py
```

Si la captura de Facturación muestra «Alegra está deshabilitado», correr las capturas con
`ALEGRA_ENABLED=true` (solo afecta a ese proceso).
