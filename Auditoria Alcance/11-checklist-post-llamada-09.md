# Checklist post-llamada 9 — qué se hizo y qué falta

**Fecha del documento:** 25 de agosto de 2026
**Fuente:** `reuniones/llamada-09-2026-08-21.md` + verificación contra el código (commits del 21 al 25 de agosto)

La llamada 9 cerró el frente que estaba trabado desde mayo: **A3 aprobó el pedido con pago
agrupado y una sola factura**, y la prueba de inicio a fin se completó por primera vez. Lo que
queda son tres integraciones y una lista corta de ajustes.

---

## 1 · Resuelto DESPUÉS de la llamada (21 – 25 de agosto)

Todo verificado en código. **Está en local; nada de esto se ha desplegado — ver §5.**

| # | Qué | Dónde |
|---|---|---|
| 1 | **Pago al final del pedido**, tras anexar todas las órdenes — el pedido pasó a ser la unidad que se cobra | decisión 011 + migración `018_pedidos.sql` |
| 2 | **Jerarquía pedido → órdenes → análisis** y **una factura por pedido** | `app/agent.py`, `app/services/db.py` |
| 3 | **Observaciones después del análisis** y **resumen de orden sin forma de pago** | flujo de cierre |
| 4 | **El análisis 1903 (Citología PAF) y los convenios** — el seed original nunca cargó las páginas 9 y 18-27 del listado; entraron 24 análisis, el catálogo pasó de 159 a 183 | `db/migrations/022_catalog_convenios.sql:21` (aplicada en Supabase el 21/08) |
| 5 | **Los 4 fallos del test en vivo de esa misma llamada**, reproducidos contra el código nuevo (bucle de la oferta, 952 + 1903 juntos, análisis heredado que contaminaba la orden siguiente) | ERR-139…143 |
| 6 | **3 bugs de dinero** cazados en la repro: quitar un agregado restaba del perfil base, "cambia el 653 **por** el 1903" borraba el destino, y "contraentrega" en plena confirmación descartaba la orden en curso | ERR-146 |
| 7 | **Formato de precios** `$18,000 COP` → `$18.000` | `app/text.py:27` |
| 8 | **Bug del PDF**: la columna "Valor" imprimía la forma de pago; hoy imprime el precio y el total | `app/templates/service_order_print.html:104` |
| 9 | **Anarvet Fase 1** — espejo de solo lectura: conexión, migraciones 023/024, sync manual, mapeo de clientes (84/103 automáticos) y vista de informes en el dashboard | decisión 013, `app/services/anarvet.py`, `app/anarvet_sync.py` |
| 10 | **35/35 flujos en verde con modelo real** (el récord anterior era 18-20/24). Suite: 911 tests | ERR-145 |

---

## 2 · Pedido en la llamada y TODAVÍA sin hacer

### 2.1 🔴 Ajustes directos de la llamada

| # | Qué | Detalle verificado |
|---|---|---|
| 11 | **Preguntar la fecha de toma de muestra en el chat** | El campo **no existe en la base**. El PDF tiene la etiqueta "Fecha toma de muestras" pero la rellena con `scheduled_pickup_date`, la fecha de recogida autocalculada — **dato incorrecto bajo etiqueta correcta** (`service_order_print.html:98`). Agregarlo toca el schema estricto, el prompt, `flow.py`, `state.py` y el resumen, y **modifica el bloque B4 del contrato, que está ✅ APROBADO** → requiere OK explícito antes de tocarlo |
| 12 | **Ajuste visual de la plataforma** | Enviar a Adriana las 3 capturas (versión nueva, anterior y el ajuste) para que A3 elija. Compromiso nuestro de la llamada, sin hacer |
| 11b | ~~**Catálogo completo y detección por nombre**~~ | ✅ **HECHO el 25/08** (ERR-147 y 147b). 316 códigos verificados contra el PDF sin faltantes; siglas, jerga del gremio y romanos XI/XII resueltos; 2 bugs de dinero corregidos. Quedan dos colas: la **migración 025** (nombres del 2004 y 2017, pendiente de tu OK) y **Mascolab** (60 ítems, bloqueado por el doble precio) |
| 13 | **Cargar una orden desde la plataforma** (cliente que llama o llega presencial) | **No existe la pantalla.** El dashboard solo tiene alta de *cliente* (`/clientes/nuevo`); ninguna ruta llama a `create_request`. El único formulario de creación es el del portal, que exige sesión del cliente. La pieza reutilizable ya está: `resolve_catalog_selection()` en `app/portal/client_requests.py:72` |

### 2.2 🔴 Anarvet — Fase 2 (lo que A3 espera ver)

La Fase 1 dejó el espejo funcionando, pero **ninguno de los cuatro pedidos de la llamada está cubierto**:

| # | Qué pidió A3 | Estado real |
|---|---|---|
| 14 | Ver el **estado del análisis** en la plataforma | Parcial y con tope de origen: `fn_reporte_examenes` solo devuelve analitos **ya validados**. No hay "recibido / en proceso": solo "aparece = listo". Requiere que Anarvet exponga estado |
| 15 | **Consultar el resultado desde el chat** | 0%. El chat sigue con el mensaje fijo de "resultados no disponibles" (`app/enforcers/resultados.py:19`) |
| 16 | Que el **personal descargue el resultado** y lo reenvíe por WhatsApp | No hay botón de descarga en las vistas del espejo, **Anarvet no entrega PDF** (habría que generarlo nosotros) y ni Telegram ni Chatwoot tienen envío de documentos, solo texto |
| 17 | **Publicación en el portal con aviso en tiempo real** | La mitad existe (publicar + notificar ya funciona para PDFs subidos a mano) pero **no se alimenta del espejo**, y "tiempo real" no existe: el badge se calcula al renderizar, sin WebSocket ni polling |
| 18 | — | Falta además: **sync automático** (hoy es un click manual), la **llave de cruce** entre nuestra orden y el paciente de Anarvet, y **pantalla** para los 19 mapeos de cliente pendientes (hoy solo por API/script) |

### 2.3 🔴 Inventario en Alegra

| # | Qué | Estado |
|---|---|---|
| 19 | **Control de inventario sobre Alegra** | **Cero líneas en el repo** — es trabajo nuevo completo. Johan confirmó que el descuento es automático al facturar, así que el alcance real es *leer y reflejar*, no *calcular*: mapear los campos de la cuenta de A3 y volcarlos a la plataforma |

### 2.4 🔴 WhatsApp y cierre

| # | Qué | Estado |
|---|---|---|
| 20 | **Canal WhatsApp** | La infraestructura de Chatwoot sirve tal cual (es agnóstica de canal), pero hay **3 tapones nuestros**: el CHECK de `requests.entry_channel` solo admite `telegram` y hoy reetiqueta cualquier otro canal (`db.py:1885`); el aviso de resultados llama a Telegram directo y filtra `channel = telegram`, así que un cliente de WhatsApp **no recibiría aviso** (`dashboard_results.py:78`); y el webhook de Chatwoot **no valida firma** |
| 21 | **Cuentas del personal y de los motorizados** en el chat interno | Solo hay 2 equipos (`contabilidad`, `operaciones`). **Falta el área "recepción"** —el prompt la nombra pero el enum no la tiene y cae en operaciones—, **no hay derivación a motorizados**, y el dashboard tiene **un único usuario admin por variable de entorno**: sin tabla de usuarios ni roles, el motorizado no puede loguearse a nada |
| 22 | **Semana de testeo en vivo con seguimiento** | Posterior al lanzamiento; sin arrancar |

---

## 3 · Lo que depende de A3 / Anarvet

| # | Qué | Para qué bloquea |
|---|---|---|
| 23 | **API y credenciales de Alegra de A3** (lectura) + definición de qué necesitan del inventario + video de cómo lo manejan | Ítem 19 |
| 24 | **Whitelisting de las IPs de Render en Anarvet** | El sync solo se probó desde local; en producción no corre sin esto |
| 25 | **TLS en el servidor de Anarvet** | Hoy el tráfico va en claro por internet |
| 26 | **Función o vista de ESTADO** en Anarvet, e idealmente filtro por cliente/paciente | Ítem 14 |
| 27 | **Definición del PDF de resultados**: quién lo genera y con qué formato/logo | Ítems 16 y 17 |
| 28 | **Llave de cruce** orden A3 ↔ paciente Anarvet | Ítems 14 y 17 |
| 29 | **Cuenta de WhatsApp Business / número** | Ítem 20 |
| 30 | **Credenciales reales de Alegra** + IVA por análisis + régimen por cliente | Facturar de verdad |
| 31 | **Datos faltantes de clientes** (dirección, NIT, motorizado) | Operación real |

---

## 4 · Pendientes viejos que la llamada NO tocó

Siguen abiertos y no se mencionaron el 21 de agosto. Detalle en `07-tenemos-falta-cronologia.md`:

- **Campo consumidor final vs. nombre propio** (llamada 4, 13/05) — **bloqueante para pasar Alegra a la cuenta real**: sin esto las facturas saldrían mal emitidas.
- **Guardar perfiles favoritos por clínica y reofrecerlos en el chat** (llamadas 3 y 5).
- **Asignación automática de motorizado por zona** (llamadas 1, 2, 4 y 5) — la zonificación está construida y sin usar.
- **Edición de precios y de descuentos desde la plataforma** (07/04 y llamada 6) — viven en código.
- **Cargas masivas por CSV**, **pasarela de pago** (Wompi/Bancolombia), **validación bloqueante de médico**, **PQR por link**, **rol de mensajero**, **alertas de recolección pendiente**, **nombre del paciente en la línea de factura**.
- **Bloquear el cambio de cliente maestro** (llamada 7) y **perfiles válidos para todas las especies salvo los etiquetados** (llamada 8).
- **Acta/minuta de cierre** prometida entre el 29 y 30 de julio: sin rastro. En esta llamada, coordinación volvió a comprometer el acta.

---

## 5 · Estado del despliegue (actualizado el 2026-08-28)

- **El código ya está publicado.** `master` estaba parado en el 8 de junio y hoy quedó a la
  altura del trabajo de julio y agosto: pedido con pago agrupado, catálogo de convenios, los
  fixes de dinero, Anarvet, el portal real, cartera, la consulta de resultados por chat, la
  agenda de mensajeros y las cargas por CSV. La rama de trabajo también.
- **Las migraciones 023 a 030 ya estaban aplicadas** en la base real, verificado tabla por
  tabla en solo lectura. **Hay un solo proyecto de Supabase**: el local y el que usará Render
  son el mismo, así que no queda ninguna migración por aplicar.
- **`PORTAL_DEMO_MODE` está apagado** desde el 27/08 y el portal entra con nombre y NIT reales.
- **Falta el despliegue en sí**: el servicio de Render todavía no corre este código. Pasos en
  `docs/runbooks/deploy.md`: runtime Docker, variables de entorno, primer arranque con
  `PDF_ENABLED=false`, verificar `/health` y recién ahí encender el PDF.
- Arrastrados de la auditoría, todavía abiertos: webhook de Chatwoot sin firma y
  `POST /setup-webhook` sin autenticación.

## Resumen

| | Cantidad |
|---|---|
| Resuelto tras la llamada | 10 frentes |
| Pendiente nuestro, pedido en la llamada | 12 |
| Bloqueado por A3 / Anarvet | 9 |
| Pendientes viejos que siguen abiertos | ~15 |

**El camino corto al lanzamiento** que A3 aceptó en la llamada: fecha de toma de muestra → ajuste
visual → Anarvet Fase 2 → WhatsApp → semana de testeo. De esos, **solo el primero y el segundo
dependen únicamente de nosotros**; los otros dos esperan entregas de A3 y de Anarvet.
