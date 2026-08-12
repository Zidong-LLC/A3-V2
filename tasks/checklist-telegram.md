# Checklist de testeo por Telegram

> Para verificar **en vivo** que los cambios son reales. Cada fila dice qué escribir, qué
> tiene que pasar y qué significa si no pasa. Marcá el resultado a medida que probás.
>
> Todo lo verificado hasta ahora está hecho con el modelo real y lecturas reales de Supabase,
> pero **con las escrituras mockeadas**. Lo que ninguna simulación reemplaza es esto: una
> persona escribiendo por Telegram contra la base de verdad.

**Antes de empezar:** levantar Flask y ngrok (`docs/runbooks/sesion-local.md`), verificar
`/health` y correr `tools/scripts/verify_chatwoot_telegram_agent.py`.

Cliente real para probar: **Animal Pets** (NIT 53115419-1, DG 51A SUR 61B-03, motorizado
Jeeferson). Otro: **Dale Pets** (NIT 1026568388-6, CL 8C 78-24, motorizado Diego).

---

## Grupo 1 — Catálogo (activo, SIN flags)

| # | Qué escribir | Tiene que pasar | Si falla |
|---|---|---|---|
| 1.1 | `Perfil 653` con un paciente **felino** | Lo registra: "653 Perfil Senior Canino III ($58.000)" | Volvió el filtro por especie |
| 1.2 | `653` (solo el número) | Igual que 1.1 | El detector de código no llega |
| 1.3 | `el 1503` | "1503 T4 Total Canino" | El catálogo de análisis no le llega al modelo |
| 1.4 | `tenés el 2110?` | Lo ofrece con precio | El modelo no ve el catálogo completo |
| 1.5 | `653 y 1517` | Registra **los dos** | Se pierde uno: revisar `_attach_profiles_by_code` |
| 1.6 | `perfil 653, 1517 y 2108` | Registra **los tres** | Vuelve el borrado en cadena |
| 1.7 | `no sé qué pedir` con paciente felino | Sugiere perfiles **felinos** | La recomendación dejó de filtrar (no debe) |

## Grupo 2 — Precios y orden de preguntas (activo, SIN flags)

| # | Qué escribir | Tiene que pasar |
|---|---|---|
| 2.1 | Cualquier análisis | El precio sale como **`$14.000`**, nunca `$14,000 COP` |
| 2.2 | Flujo completo | El **análisis se pide ANTES** que las observaciones |
| 2.3 | Idem | El "Por último…" está en **observaciones**, no en el análisis |

## Grupo 3 — Los fixes de bugs (activo, SIN flags)

| # | Qué escribir | Tiene que pasar | Bug original |
|---|---|---|---|
| 3.1 | Al pedir el médico: `José Toro` | Pregunta especie y sexo **normalmente** | ERR-084: los inventaba (Bovino/Macho) |
| 3.2 | Especie `Equino`, raza `Cuarto de Milla`, propietario `Jorge Toro` | El resumen dice **Equino** | ERR-084: quedaba Bovino |
| 3.3 | `creo que no estamos registrados` y al turno siguiente `ah no, sí estamos, somos Animal Pets` | **Vuelve a responder** y sigue la orden | ERR-088: quedaba mudo para siempre |
| 3.4 | Decir que sos **dueño de una mascota** (particular) | Deja de responder — **este silencio es correcto** | Contraprueba de 3.3 |
| 3.5 | Orden completa a nombre de **Dale Pets**; en el resumen: `el cliente, soy Animal Pets` | Dirección **DG 51A SUR 61B-03** y motorizado **Jeeferson** | ERR-099: quedaban los de Dale Pets |
| 3.6 | Identificarse como `Centro Medico Veterinario`, rechazar la dirección, y responder `Centro veterinario La Uribe` | Veterinaria y dirección de **la misma sede** | ERR-081 — **nunca se probó en vivo** |
| 3.7 | Agregar un análisis, llegar al resumen y confirmar con `Si` | "Quedó registrado… Número de orden: A3-…" | ERR-080: entraba en bucle |
| 3.8 | Un escalado a contabilidad (opción 3) | Dice **"Te asignaremos un asesor…"** | Antes cada camino tenía su frase |

## Grupo 4 — Pedidos multi-orden (requiere `PEDIDOS_ENABLED=true`)

> Levantar con: `PEDIDOS_ENABLED=true python -m flask --app app.main run --port 5000 --host 0.0.0.0`
>
> **Ojo:** con pedidos, la factura de Alegra se emite **al cerrar el pedido**, no al confirmar
> cada orden. Si cargás tres pacientes, esperá **una sola** factura.

| # | Qué escribir | Tiene que pasar |
|---|---|---|
| 4.1 | Flujo de una orden hasta el final | El resumen **NO** muestra la forma de pago |
| 4.2 | Confirmar la orden | Ofrece: "¿otra orden…? Si eso es todo, seguimos con la forma de pago" |
| 4.3 | `otra orden` y cargar un segundo paciente | Mantiene cliente y dirección; permite cambiar el médico |
| 4.4 | Cargar una **tercera** orden | Igual |
| 4.5 | `eso es todo` | Pregunta **observación del pedido + forma de pago** en un mismo mensaje |
| 4.6 | `contraentrega` | **Resumen con LAS TRES órdenes**, cada una con paciente, médico, análisis y subtotal, más el TOTAL |
| 4.7 | Revisar Alegra | **UNA sola factura** con todo |
| 4.8 | Verificar en Supabase | Tres filas en `requests` con el mismo `pedido_id`, y el pedido en `facturado` |

**4.6 es el que más importa:** es lo único que no quedó demostrado en simulación — en la
corrida de prueba el cliente corrigió a mitad y quedó una sola orden.

### Cierre con tus propias palabras (no las del guion)

| # | Qué escribir en vez de "eso es todo" | Tiene que pasar |
|---|---|---|
| 4.9 | `listo, nada más por hoy` | Pregunta el pago |
| 4.10 | `ya está, cerrame eso` | Pregunta el pago |
| 4.11 | `dale, cerralo` | Pregunta el pago |
| 4.12 | `listo, ahora cargame el otro paciente` | **NO** cierra: abre otra orden |
| 4.13 | `les pagamos cuando pasen a recoger` | Cierra con **contraentrega** |
| 4.14 | `mandanos el link de pago` | Cierra con **pago en línea** |

**4.12 es la contraprueba importante:** empieza con "listo" pero NO quiere cerrar. Si cierra
ahí, el criterio quedó demasiado flojo.

---

## Qué anotar cuando algo falla

Para que el arreglo no sea a ciegas, anotá: **qué escribiste exacto**, **qué respondió el
bot** (copiado tal cual) y **en qué punto del flujo estabas**. Con eso se reproduce; sin eso
hay que adivinar.
