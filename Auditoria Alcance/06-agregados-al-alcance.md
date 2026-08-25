# Lo que se agregó al alcance en las llamadas

**Fecha:** 2 de agosto de 2026 · **Cobertura: las 10 reuniones (07/04 – 28/07/2026)**

Pedidos que **no figuran** en la Propuesta V2, el Kickoff ni el Plan de Trabajo firmado, y que
entraron por conversación durante el proyecto. No incluye correcciones de bugs.

> **Distinción importante.** No todo lo pendiente es alcance agregado. Hay pedidos antiguos que
> nunca se entregaron — están en la sección F y **no deberían usarse como argumento de
> sobrecosto**. Mezclarlos debilita el caso de los que sí lo son.

Peso: 🔴 estructural · 🟠 módulo nuevo · 🟡 refinamiento

---

## A. Cambios estructurales — rehacen algo ya construido

| # | Qué | Llamada | Estado |
|---|---|---|---|
| A1 | **Jerarquía pedido → órdenes → análisis**; el pedido es la unidad que se factura | 8 (28/07) | ❌ |
| A2 | **Una factura por pedido** con varias órdenes adentro | 8 | ❌ |
| A3 | **Resumen de orden sin forma de pago** | 8 | ❌ |
| A4 | **Observaciones después del análisis**, no antes | 8 | ❌ |
| A5 | **Bloquear el cambio de cliente maestro** | 7 (07/07) | ❌ |
| A6 | **Perfiles válidos para todas las especies** salvo los etiquetados, con etiqueta administrable | 8 | ❌ |

Son seis, no siete: **la forma de pago al cierre del pedido salió de esta lista** — se pidió el
20 de mayo, no el 28 de julio. Ver sección F.

A1 y A2 siguen siendo el mismo cambio visto desde dos ángulos, y tocan el paso de confirmación y
cierre, marcado como aprobado en `docs/contrato-flujo-conversacional.md`.

---

## B. Módulos nuevos completos

| # | Qué | Llamada | Estado |
|---|---|---|---|
| B1 | **Chatbot externo para dueños de mascotas** — otro portafolio, venta por WhatsApp, pago directo. Es un segundo desarrollo | 1, 3 | ❌ Nunca entró al alcance registrado |
| B2 | **Calendario de mensajeros** — compensatorios, permisos, vacaciones | 1 | ❌ No existe |
| B3 | **Campo consumidor final vs. nombre propio** por cliente, con datos de la veterinaria en observaciones | 4 | ❌ **Bloqueante para facturar en la cuenta real** |
| B4 | **Nombre del paciente en la descripción de cada servicio facturado** | 4 | ❌ |
| B5 | **Cargas masivas por CSV** de precios, clientes y portafolio | 4 | ❌ Solo hay exportación |
| B6 | **Adjuntar soporte de pago en el chat** + "gestión de pagos" + verlo en la plataforma | 2 | ❌ El bot no recibe archivos |
| B7 | **RUT y documentos a carpeta de Google Drive** con validación humana | **00b (08/04)**, 2 | ❌ |
| B8 | **Rol de mensajero** con vista limitada a sus rutas y pendientes generales | 2 | ❌ |
| B9 | **Alertas por recolección pendiente durante X tiempo** | 4 | ❌ |
| B10 | **Sincronización bidireccional plataforma ↔ Alegra** | 4 | ❌ |
| B11 | **Pago en línea con pasarela** (Wompi/Bancolombia) | 2, 5, 6, 8 | ❌ |
| B12 | **Edición de precios desde la plataforma** | **00a (07/04)**, 1 | ❌ Pedido desde el arranque del proyecto |
| B13 | **Descuentos editables desde la plataforma** | 6 | ❌ Los tramos funcionan, viven en código |
| B14 | **Reconocimiento del cliente por su teléfono** | 6, 7 | ❌ Planteado como futuro |
| B15 | **"Crea tu perfil"** — perfiles personalizados | **00b (08/04)**, 1, 3, 6 | ⚠️ Se arman y cobran; no se guardan ni reofrecen |
| B16 | **Etiquetas diagnósticas + sugerencia de pruebas** por perfil clínico | 6 | ✅ |
| B17 | **Descuentos por cantidad de pruebas** | 3, 6 | ✅ |
| B18 | **Zonificación territorial de Bogotá** — 8 zonas, 1.649 barrios | 1, 4 | ✅ Construida… y sin usar para asignar la orden |
| B19 | **Especies grandes** — bovino, equino, porcino, caprino, aves, roedores, silvestres | 7 | ✅ en el agente · ❌ en el catálogo de perfiles |
| B20 | **Base de razas por especie** — 323 razas | 7 | ✅ |
| B21 | **Validación de médicos** con tarjeta profesional y afiliación a su clínica | **00b (08/04)**, 6, 7 | ⚠️ Tabla y búsqueda inversa; sin validación que bloquee ni gestión de afiliación |
| B22 | **Panel de métricas personalizable** con bloques configurables | 4 | ⚠️ Preferencias de columnas, no "cubos" |
| B23 | **Estados operativos del chat** ("resuelto por llamada", "inactivo") | 2 | ⚠️ |
| B24 | **Consecutivo de orden de servicio** | 3 | ✅ |
| B25 | **Colores por etapa** | 4 | ✅ |

---

## C. Refinamientos sobre lo ya entregado

| # | Qué | Llamada | Estado |
|---|---|---|---|
| C1 | Búsqueda por palabra clave con lista de coincidencias | 5, 6 | ✅ |
| C2 | NIT con y sin dígito de verificación | 2 | ✅ |
| C3 | No repetir preguntas ya respondidas | 2, 3 | ✅ |
| C4 | Sedes múltiples con confirmación explícita | 3 | ✅ |
| C5 | Flujo dinámico ramificado, no lineal | 3 | ✅ |
| C6 | Barrios repetidos en varias localidades | 4 | ✅ |
| C7 | Cambio manual de motorizado en una solicitud | 1, 2, 4 | ✅ |
| C8 | Tono más natural y colombiano | 5, 6 | ✅ |
| C9 | Mensaje explícito de "te asignaremos un asesor" | 3 | ❓ No lo encontré en `messages.py` |
| C10 | Formato de precios "18K" → "18.000" | 7 | ⚠️ Quedó `$18,000 COP`, coma inglesa |
| C11 | PDF de la orden: donde imprime la forma de pago debe ir el valor | 8 | ❌ Confirmado en `service_order_print.html:102` |
| C12 | PQR por link | 2 | ❌ |
| C13 | Prueba guiada de inicio a fin | 7, 8 | ⚠️ Intentada dos veces, sin cerrar |

---

## D. Cambio de supuesto técnico — Anarvet

| # | Qué | Llamada | Impacto |
|---|---|---|---|
| D1 | Acceso **solo de lectura** | 4 (13/05) | Ya se sabía desde mayo |
| D2 | El mecanismo sería **SQL directo**, no API REST | 8 (28/07) | Cambia el diseño que el triage asumía |
| D3 | **El PDF del resultado lo generamos nosotros** | 8 | Trabajo nuevo no contemplado |
| D4 | Plan B: PDFs desde **OneDrive** | 7 | Vía alternativa sin registrar |

---

## E. Lo que se sacó del alcance

| Qué | Cómo quedó | Respaldo |
|---|---|---|
| Siigo (facturación) | Sustituido por Alegra | Triage |
| DelSol (sistema) | Consolidado en Alegra | Triage |
| LiveConnect (logística) | Sustituido por Chatwoot | **Acta: reunión 00a (07/04), transcripción literal** — Luciano propone Chatwoot, Clara responde *"Sí, perfecto"* |
| Tracking GPS en tiempo real | A3 lo movió a mejora futura | **Acta: llamada 7, punto 8** (y llamada 2, punto 11) |
| Foto de la orden con OCR | Retirado | **Acta: llamada 5, punto 5 — quedó como decisión abierta, nunca fue compromiso** |
| Notificaciones por email | WhatsApp y bandeja del portal | Triage |
| Manuales y capacitación | No se hacen | Triage |
| Roles y multi-usuario por clínica | No aplica | Triage · ⚠️ choca con el rol de mensajero (B8) |

---

## F. Pedidos antiguos nunca entregados — NO son alcance agregado

Los seis se pidieron entre el 7 de abril y el 20 de mayo, y siguen sin hacerse:

| Qué | Pedido el | Reaparece en |
|---|---|---|
| **Edición de precios desde la plataforma** | **07/04** (reunión 00a) — *"que lo puedan modificar ustedes el precio de cada uno de los análisis"* | Llamada 1, punto 11 |
| **Afiliación médico ↔ clínica administrable** | **08/04** (reunión 00b) — *"que la clínica afilie sus médicos veterinarios que están vinculados con ella"* | Llamadas 6 y 7 |
| **Asignación automática de motorizado por zona** | **16/04** (llamada 1, punto 6) | Llamadas 2, 4 y 5 |
| **Guardar perfiles favoritos por clínica y reofrecerlos en el chat** | **06/05** (llamada 3, punto 12) | Llamada 5, punto 14 |
| **Reiniciar / finalizar conversación** | **13/05** (llamada 4, punto 16) | Llamada 7, punto 12 · *fuera de alcance: es herramienta de prueba, no de producción* |
| **Forma de pago al final, tras anexar todas las órdenes** | **20/05** (llamada 5, punto 6) | Llamada 8, donde se discutió como si fuera nuevo |

Los dos primeros son los más expuestos: **tienen casi cuatro meses y están en transcripción
literal**, no en resumen. Si A3 los saca en la reunión de cierre, no hay margen de interpretación.

Presentarlos como alcance adicional no se sostiene contra las actas. Conviene separarlos antes
de cualquier conversación de cierre.

---

## Resumen

**48 ítems identificados en 8 llamadas.** Del total: 17 hechos, 8 parciales, 23 sin hacer.

- **Alcance genuinamente agregado y sin hacer:** los 6 del bloque A (todos de las llamadas 7 y 8)
  más los 14 módulos nuevos pendientes del bloque B.
- **Pedidos antiguos sin entregar:** los 4 del bloque F.
- **Lo bien cubierto:** GPS y OCR tienen acta propia; la búsqueda, el NIT, las sedes, las
  especies, el consecutivo y los descuentos están entregados.

El bloque F es el que hay que mirar primero: son cuatro pedidos con dos y tres meses de
antigüedad, y dos de ellos —el pago y los perfiles favoritos— son exactamente lo que A3 sigue
reclamando en las últimas dos llamadas.
