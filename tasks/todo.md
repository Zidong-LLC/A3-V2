# Tareas — A3 Laboratorio Veterinario V2

---

## Módulo "Facturación" (Alegra) — Completado (falta aplicar migración 014)

**Objetivo:** centro de consulta de facturas de Alegra dentro del dashboard (Fase 4 de la
decisión 009, read-only), adaptado a Colombia/DIAN. Plan en
`C:\Users\Artel\.claude\plans\hidden-leaping-eclipse.md`.

**Decisiones del usuario:** sin roles (login admin actual) · arquitectura híbrida (tabla
cache + lectura directa para el detalle) · consulta + acciones con bloqueo de envío/emisión
en pruebas.

**Cambios realizados:**
- [x] `app/services/alegra.py`: `list_invoices`, `get_invoice`, `get_invoice_pdf_url` (solo lectura).
- [x] `app/billing.py`: `invoice_to_row()` (mapeo puro Alegra→fila) + tests en `tests/test_alegra_billing.py`.
- [x] Migración `db/migrations/014_invoices_cache.sql` (tabla `invoices_cache`, no toca esquema existente).
- [x] `app/services/db.py`: `upsert_invoices_cache`, `list_cached_invoices`, `list_all_cached_invoices`, `get_cached_invoice`.
- [x] `app/config.py` + `.env.example`: flag `ALEGRA_PRODUCTION` (false=pruebas → acciones de envío bloqueadas).
- [x] `app/dashboard.py`: ruta `/facturacion`, contexto (KPIs/métricas/paginación/filtros), endpoints
      `GET /api/dashboard/invoices`, `GET .../invoices/<id>` (read-through), `POST .../invoices/sync`,
      `GET .../invoices/export` (CSV/Excel).
- [x] UI: ítem en sidebar, pestaña con KPIs, filtros, buscador, orden por columna, paginación,
      tabla con **columnas configurables** (reusa `columns-config.js`), modal de detalle.
- [x] `app/static/invoices.js` (sync, export, orden, paginación, copiar, detalle) + estilos en `app.css`.

**Pendiente:**
- [ ] Aplicar `014_invoices_cache.sql` en Supabase. Sin esto, el módulo carga vacío con gracia
      ("No hay facturas en cache") — nada se rompe.
- [ ] Validar `alegra.list_invoices/get_invoice` contra la cuenta de pruebas con un smoke (solo lectura).

**Verificación hecha:** `pytest` (147 pasan) · render `/facturacion` 200 con test client (estado
vacío correcto) · rutas registradas · `node --check` y parseo Jinja OK.

**Guardrails respetados:** solo lectura; ninguna emisión/envío; IDs Alegra↔orden vía evento
`alegra_invoiced` en `request_events`; acciones de reenvío/XML deshabilitadas en pruebas.

---

## Personalización de columnas en tablas del CRM — Completado (falta aplicar migración)

**Objetivo:** que cada usuario elija qué columnas ver/ocultar y su orden, en todas las tablas
del dashboard, de forma reutilizable y persistente entre sesiones y dispositivos.

**Estado de partida:** la funcionalidad ya existía casi completa (sin commitear) en
`app/static/columns-config.js`, con atributos `data-column`/`data-mandatory` en los `<th>` y
botones "Columnas" en 6 tablas. Persistía solo en `localStorage` (por navegador).

**Decisión del usuario:** persistencia **híbrida** (localStorage instantáneo + servidor para
sincronizar entre dispositivos).

**Cambios realizados:**
- [x] Fix bug HTML: fragmento basura en el `<thead>` de la tabla de clientes
      (`app/templates/dashboard.html`) que rompía el encabezado.
- [x] Migración `db/migrations/013_dashboard_column_prefs.sql` (tabla `dashboard_column_prefs`,
      PK `user_key,table_id`, `prefs jsonb`).
- [x] `db.list_column_prefs()` y `db.upsert_column_prefs()` en `app/services/db.py`.
- [x] Endpoints GET/POST `/api/dashboard/column-prefs` en `app/dashboard.py` (mismo patrón
      JSON que el resto; exentos de CSRF por no usar `request.form`).
- [x] `columns-config.js`: sincronización híbrida (debounce POST al guardar, GET al cargar que
      sobrescribe lo local) + arreglo del cierre del panel al hacer clic afuera. Cache `?v=3`.

**Pendiente para que funcione el lado servidor:**
- [ ] Aplicar la migración `013` en el SQL Editor de Supabase (sin esto, el GET/POST devuelven
      error y el sistema cae con gracia a solo-localStorage; nada se rompe).

**Verificación:** levantar el dashboard, abrir cada tabla → botón "Columnas" abre panel lateral;
marcar/desmarcar actualiza al instante; buscador filtra; mostrar/ocultar/restablecer funcionan;
drag & drop reordena; recargar conserva la config. Tras aplicar la migración, cambiar de equipo
debe traer la misma configuración.

---

## Bug: agregar otro análisis/perfil se traba (chat 4 real) — En curso

Reportado por el usuario y reproducido en el historial real (`external_chat_id=4`):
1. **Intención compuesta ignorada:** "quiero el perfil 152 al cual le quiero agregar un
   analisis extra" → el bot captura el perfil y salta al pago, descartando el "agregar".
2. **Pregunta de catálogo durante el ajuste se traba:** estando en personalización/confirmación,
   "que analisis de orina tienen" → el bot repite el resumen sin listar opciones de orina.
   El usuario quedó sin respuesta.

Causa raíz: durante el ajuste de un perfil, el código solo resuelve nombre/código EXACTO de
análisis; una pregunta abierta por área no llega a `find_tests_by_area` y cae al resumen.

Plan (mínimo, avisado y aprobado por el usuario):
- [x] Helper `_area_options_for_profile_addition`: ante pregunta por área durante el ajuste,
      muestra el menú de esa área marcado para AGREGAR al perfil base (`_test_menu_adds_to_profile`).
- [x] `_enforce_profile_customization_changes`: si llega una pregunta por área, mostrar el menú.
- [x] `_confirmation_analysis_adjustment`: si no resuelve test exacto, intentar opciones por área.
- [x] Selección de menú en `process_turn`: si `_test_menu_adds_to_profile`, AGREGAR al
      perfil en vez de reemplazar (`_capture_menu_addition_to_profile`).
- [x] Fix intención compuesta: en `_enforce_catalog_profile_code_selection`, si el mismo mensaje
      pide agregar, tras fijar el perfil preguntar qué análisis agregar.
- [x] Tests de regresión (`tests/test_add_analysis_during_adjustment.py`, 5 casos).
- [x] Registrar en `errores-soluciones.md` (RESUELTO-014) y actualizar el contrato (B9/B11).

**Resultado:** suite 126/126 verde. Verificado contra base real (`find_tests_by_area` →
7 análisis de Uroanálisis; perfil 152 = $24.000). Pendiente: que el usuario reinicie el Flask
local y re-pruebe la conversación (el historial del chat 4 era de código anterior).

---

## Integración de Alegra (facturación electrónica DIAN) — Por fases — En curso

Decisión [009](../docs/decisions/009-alegra-integracion-por-fases.md) (supersede la 008).
Plan completo en el archivo de plan aprobado. Cubre las 4 capacidades (facturación DIAN,
link de pago en chat, consulta de facturas/saldo, sync de clientes), por fases. Se prueba
PRIMERO con una cuenta nueva detrás de `ALEGRA_ENABLED`; migrar a la del cliente = cambiar
solo `.env`.

### Fase 0 — Credenciales y feature flag ✅ COMPLETA
- [x] `config.py`: `ALEGRA_ENABLED` (default false), `ALEGRA_EMAIL`, `ALEGRA_API_TOKEN`, `ALEGRA_BASE_URL`.
- [x] `.env.example`: bloque Alegra documentado.
- [x] `docs/decisions/009-alegra-integracion-por-fases.md` (supersede 008).
- [x] `scripts/alegra_smoke.py`: ping de conectividad + get_or_create de contacto demo.

### Fase 1 — Cliente API + sync de contactos (backend) — Base validada
- [x] `app/services/alegra.py`: cliente Basic auth aislado, `ping`, `find_contact_by_nit`,
      `get_or_create_contact`. urllib (igual que chatwoot.py), errores re-lanzados como `AlegraError`.
- [x] Validado contra API real (cuenta Colombia, `applicationVersion="colombia"`):
      conectividad, lectura y **alta de contacto con NIT** OK. El NIT se guarda y la búsqueda
      lo encuentra → idempotencia confirmada (ver RESUELTO-009). Formato: `identificationObject`
      (NIT) + `regime` + `kindOfPerson`.
- [ ] Hook de sync: al identificar cliente, `get_or_create_contact` por NIT y guardar
      `alegra_contact_id` en `request_events.event_payload` (bajo `ALEGRA_ENABLED`).
      → Toca `agent.py`/`db.py`; siguiente paso.

### Fase 2 — Facturación (backend) — Base API validada
- [x] `app/services/alegra.py`: `find_item_by_reference`, `get_or_create_item` (idempotente
      por código), `create_invoice` (borrador por defecto). Validado contra cuenta Colombia:
      ítem idempotente, factura con total correcto (2×35000=70000), status `draft`.
- [x] Confirmado: la cuenta de pruebas tiene numeración de factura de venta `id=1`
      `electronic=false` → se factura en borrador/no-electrónico ahora; la emisión DIAN real
      (timbrado) se valida con la cuenta del cliente que sí tiene facturación electrónica.
- [x] Mapeo catálogo → ítems Alegra: `app/billing.py` (`build_invoice_lines` puro +
      `invoice_order`). El total cuadra con `price_adjustment.total` del event_payload
      (base ajustado por removidas + agregadas como líneas). `create_request` ahora devuelve
      `event_payload` (cambio aditivo) para no reconstruir la lógica de catálogo.
- [x] Hook al cerrar orden `route_scheduling`: `agent._try_invoice_in_alegra` tras
      `db.create_request`, bajo `ALEGRA_ENABLED`. Sync de contacto + factura borrador; guarda
      IDs como evento `alegra_invoiced` (sin tocar esquema Supabase). try/except: si Alegra
      falla, loggea y NO rompe el cierre ni la recogida.
- [x] Tests: `tests/test_alegra_billing.py` (7) — build_invoice_lines + hook (éxito, fallo
      no rompe, orden sin perfil no factura). Suite 84/84.
- [x] Validado end-to-end contra cuenta Colombia real: hook → factura con total correcto
      (95000) → evento guardado. Decisión del usuario: facturar TODA orden, automático.
- [ ] PENDIENTE emisión DIAN real (cuenta del cliente): IVA de análisis, régimen por cliente,
      numeración electrónica. Hoy se factura en borrador/no-electrónico.

### Fases 3–4 — Pendientes
- [ ] Fase 3: link de pago en chat para `pago_linea` (requiere activar pagos electrónicos / Mercado Pago).
- [ ] Fase 4: consulta de facturas/saldo (read-only) dentro del intent `accounting`.

---

## Bucle de especie/typos + fallback robótico (caso Luciano) ✅ COMPLETA

Bug reportado: pidiendo la especie, el cliente responde "Kanino"/"Kany"; el modelo
no lo captura, repregunta idéntico, y el anti-bucle lo reemplaza por la frase
robótica "Para avanzar, dime el dato que tengas a mano o escribe 'hablar con
alguien'…". Causa: `_rephrased_repeated_question` no tenía branch para especie
(ni sexo ni pago) → caía al genérico feo; y "Kanino" no se recuperaba de raíz.

Arreglo (preciso, sin tocar el umbral del anti-bucle):
- [x] `agent.py` `_rephrased_repeated_question`: branches cálidos para especie, sexo
      y pago; genérico final sin "hablar con alguien" seco.
- [x] `agent.py` `_recover_enumerated_answer` + `_RECOVERABLE_SPECIES`/`_RECOVERABLE_SEX`:
      recupera variantes/typos de los campos enumerados ANTES del anti-bucle.
      `_avoid_redundant_route_field_question` corrige el reply al siguiente campo.
- [x] `prompt.py`: PASO 3 especie (capturar variante / confirmar ambiguo) + R5b
      (nunca repetir pregunta idéntica; confirmar u ofrecer opciones).
- [x] Capa de coherencia afinada: detector `_looks_off_topic_smalltalk` ahora cubre
      conectores ("y", "ah", "pero"…) y frases sociales ("cómo vas", "qué más"), y se
      quitó la optimización que saltaba el verificador (hacía que el off-topic saliera
      con tono seco en vez de cálido). Off-topic → SIEMPRE reencauce cálido.
- [x] Tests: typo de especie se recupera y avanza a raza; typo de sexo → Macho;
      repregunta de especie/pago da opciones cálidas; off-topic con conectores → cálido.
- [x] Verificado: py_compile OK; suite 206 passed.

### Resultados (validado contra el modelo REAL, gpt-5.4-mini)
Script `tools/scripts/validate_coherence.py` (db mockeada, `ai.generate_turn` real):
- "Kanino" → "registro canino. ¿Cuál es la raza?" (Canino). Sin bucle.
- "es un gatito" → Felino.
- "Kany" (ambiguo) → "¿Te refieres a canino?" (el modelo confirma).
- "jaja, ¿y cómo vas?" (off-topic) → "Jajaja, bien por acá, gracias. ¿Me compartes
  el nombre del médico solicitante?" (cálido, no captura basura).
- "masho" → Macho, avanza.
El bug original (frase robótica "hablar con alguien" / bucle) quedó cerrado. Ver L20.

---

## Capa de coherencia en el flujo de datos del paciente ✅ COMPLETA

Problema: cuando el cliente no sigue los pasos (pido el médico/edad y responde
"hola, ¿cómo estás?" u otra cosa), la coherencia estaba 100% delegada al prompt
del LLM (sección "Coherencia antes de capturar" + R22/R23). El LLM a veces igual
capturaba basura. El flujo de cliente nuevo ya tenía una red de seguridad real
(`interpret_nc_step`), pero el flujo principal de datos del paciente no.

Decisión de diseño (confirmada con el usuario):
- Híbrido, replicando el patrón ya existente: chequeo barato determinista primero,
  verificador-LLM corto SOLO cuando la respuesta huele a off-topic. No agrega una
  segunda llamada en cada turno.
- Tono de reencauce: humano y cálido, breve (colombiano), no robótico.

Pasos:
- [x] `ai.py`: `interpret_route_field(question, user_message)` — gemelo de
      `interpret_nc_step`, devuelve `{action: save|clarify, value, reply}`.
- [x] `agent.py`: `_enforce_field_coherence(...)` + `_looks_off_topic_smalltalk`
      (normaliza acentos) + `_COHERENCE_GUARDED_FIELDS`. Solo actúa en
      route_scheduling con cliente identificado, fuera de fases terminales y del
      armado de perfil. Si el modelo ya manejó bien el off-topic (no capturó nada
      nuevo y su reply repregunta el mismo dato), no gasta la llamada extra.
- [x] Insertado tras `_clarify_captured_field`, antes de confirmación/cierre (frena
      antes de crear cualquier request).
- [x] Tests: off-topic se reencauza y NO captura; respuesta válida no gasta llamada
      extra; modelo que ya repreguntó no gasta llamada extra.
- [x] Verificado: py_compile OK; `test_agent_flows` 112 passed; suite 202 passed.

### Resultados
- Campos cubiertos: requesting_doctor, patient_name, species, breed, sex,
  patient_age, owner_name. Quedan fuera exam_type (lo gobierna catálogo/perfil) y
  cliente/dirección/pago/observaciones (tienen manejo dedicado).
- La red de seguridad solo se activa ante señales claras de off-topic (saludo,
  small talk, pregunta social), así no encarece el caso común.

---

## Forma de pago dentro de ruta activa ✅ COMPLETA

Bug detectado durante `validate_flows.py`: si el bot estaba pidiendo la forma de
pago, el modelo podía clasificar "pago en línea" como `accounting` y crear una
solicitud incompleta, o si el usuario decía "pago en línea" antes del turno de
pago podía descarrilar el campo faltante.

Arreglo:
- [x] `agent.py`: `_payment_method_from_text` normaliza `contraentrega` y
      `pago_linea` desde texto del usuario.
- [x] Si la ruta activa está esperando `payment_method`, se fuerza
      `intent=route_scheduling` y se muestra confirmación editable antes de crear
      la orden.
- [x] Si todavía falta otro campo, una forma de pago fuera de turno no cierra ni
      escala: se vuelve a preguntar el campo faltante.
- [x] Tests: pago clasificado erróneamente como contabilidad dentro de ruta y pago
      dicho antes del turno de pago.

### Resultados
- `pytest tests/test_agent_flows.py tests/test_db_identification.py` → 134 passed.
- `python tools/scripts/validate_flows.py` → 6/6 flujos OK con modelo real.

---

## Memoria del cliente + manejo de off-topic ✅ COMPLETA

Objetivo: que el agente recuerde datos estables del cliente a lo largo de la
conversación y los reofrezca con confirmación ("el mismo de siempre"), y que
responda con naturalidad a mensajes fuera de alcance sin abandonar el flujo.

Decisiones de diseño:
- Solo se recuerdan datos ESTABLES del cliente: `pickup_address`,
  `requesting_doctor`, `payment_method`. Los datos del paciente NO se recuerdan
  entre órdenes (riesgo de arrastre). Teléfono fuera (R11).
- Se persiste en `captured_fields._client_memory` (JSON existente, sin tocar
  Supabase). Sobrevive solo porque empieza con `_` (agent.py:2043-2046).
- La confirmación conversacional y el off-topic los maneja el LLM con reglas de
  prompt + memoria inyectada al contexto. NO se construye máquina de estados nueva.

Pasos:
- [x] `agent.py`: constante `_CLIENT_MEMORY_FIELDS`.
- [x] `agent.py` (`_persist_turn`): `_remember_client_fields` vuelca los campos estables a `_client_memory`.
- [x] `agent.py` (`process_turn`): arma `session["_client_memory_hint"]` antes de llamar al modelo.
- [x] `ai.py`: inyecta el hint de memoria en `state_parts`.
- [x] `prompt.py`: R21 (reofrecer dato estable recordado + confirmar) y R22 (off-topic: declinar breve + retomar flujo).
- [x] Verificar: `py_compile` OK; suite `tests/` 199 passed (2 fallos preexistentes y ajenos: cargan un Excel de otra máquina).
- [x] Prueba local con modelo real: `validate_flows.py` reofrece "el de siempre" como médico solicitante y continúa al paciente.

### Resultados
- Memoria persistente sin tocar Supabase ni el JSON schema (vive en `captured_fields._client_memory`).
- El LLM maneja la confirmación conversacional y el off-topic vía R21/R22 — sin máquina de estados nueva.
- El atajo determinista del otro dev (`_resolve_same_as_previous`, misma sesión) sigue intacto y no colisiona: corto plazo = atajo; largo plazo = LLM con memoria inyectada.
- Verificación final: tests determinísticos de memoria + `validate_flows.py` 6/6 OK con modelo real.

---

## Desplegar análisis por área/muestra (ej. "orina") ✅ COMPLETA

Bug: al pedir "análisis de orina" el bot no despliega opciones y cae en "Para
avanzar necesito el análisis o perfil exacto". Causa: "orina" no es perfil ni
etiqueta diagnóstica; es la categoría "Uroanálisis" / sample "Orina Fresca" de
los análisis individuales (`catalog_tests`), que el bot no consulta al elegir
examen. Las 3 búsquedas (find_catalog_profiles/profile/diagnostic_label) dan vacío.

Solución (elegida: completa, generaliza a todas las áreas):
- [x] `db.find_tests_by_area(query, species)`: matchea la query contra categoría
      o sample de `catalog_tests` y devuelve (área, tests). Resuelve orina vía sample.
      Defensiva (try/except → None,[] si la BD no responde).
- [x] `agent._test_area_suggestion_reply` + `_enforce_test_category_help`: réplica
      de `_enforce_diagnostic_label_help`. Despliega los análisis del área y arranca
      selección (selected_tests=[]), reusando el flujo de perfil personalizado.
      Usa el término del usuario en el mensaje (no la categoría interna).
- [x] Insertado en el pipeline después de `_enforce_catalog_profile_help`.
- [x] Guard "exam_type nuevo" (compara con prev_captured): solo evalúa el área en
      el turno donde se menciona el examen → evita I/O y re-disparos en pasos posteriores.
- [x] Verificado: py_compile + suite 199 passed + simulación end-to-end con "orina".
- [x] Tests agregados: enforcement de área en `agent.py` y matching por `sample` en `db.find_tests_by_area`.

### Resultados
- "quiero un análisis de orina" ahora despliega las 7 opciones de Uroanálisis con precio.
- Regresión detectada y corregida: sin el guard de "exam_type nuevo", el enforcement
  hacía I/O en cada turno y rompía 30 tests (ConnectError). Ver L17.

---

## Perfiles por necesidad diagnóstica (etiquetas) ✅ COMPLETA
Integra el sheet de etiquetas: cuando el cliente pide un perfil por motivo clínico, el sistema sugiere las pruebas y arma un perfil personalizado (con descuento por volumen).
- [x] Datos: `tools/data/diagnostic_labels.json` (31 etiquetas, 66 pruebas; códigos cruzan 100% con `catalog_tests`).
- [x] Migración `012_diagnostic_labels.sql`: tabla `diagnostic_label_tests (label, test_code)`.
- [x] Script `tools/scripts/import_diagnostic_labels.py` (idempotente, lee el JSON).
- [x] `db.py`: `list_diagnostic_labels`, `find_diagnostic_label`, `get_tests_for_label` (defensivas si la tabla no existe aún).
- [x] `agent.py`: `_enforce_diagnostic_label_help` sugiere pruebas y arranca perfil personalizado (`selected_tests=[]`); prioridad a perfiles de catálogo con precio fijo. Etiquetas inyectadas al contexto. Prompt con regla.
- [x] Tests: matching normalizado de etiqueta + sugerencia en el flujo. Suite verde (186).
- ⚠️ Pasos manuales en Supabase: aplicar migración `012` y luego `python tools/scripts/import_diagnostic_labels.py`.

---

## Alineación con spec v4.3 — Plan por fases (pendiente de aprobación)

### Alcance acordado
HACER: #2 (parcial), #3, #6, #8, #9, #10, #12, #13, #14, #15, #16, #17.
OMITIR por ahora: #1 (WhatsApp), #4 (consulta resultados), #5 (notificaciones), #7 (correo), #11 (foto/OCR).

### Decisiones tomadas
- Descuentos (#15): estructura de tramos parametrizable en `config.py`, valores vacíos → sigue 0.
- N° de orden (#16): reinicia por año → `A3-2026-001`.
- Pago en línea (#6): registra la orden + deriva a contabilidad ("te contactan en X min").
- Cliente final (#2): se detecta y se BLOQUEA la sesión; el agente deja de responder.

---

### FASE 1 — Ajustes de captura (bajo riesgo) ✅ COMPLETA
Archivos: `prompt.py`, `agent.py`, `schema.py`, `db.py`
- [x] #8 Quitar teléfono: eliminado `clinic_phone` del schema, de las tuplas de campos, del prompt, de los fallbacks y del resumen. El teléfono de la orden impresa se toma del cliente (`_client_phone` desde BD) vía `_service_order_event_payload`.
- [x] #9 Exámenes al final: orden ahora Médico → Paciente → Especie → Raza → Sexo → Edad → Propietario → Observaciones → **Exámenes** (en `prompt.py` y `_ROUTE_ORDER_FIELDS_BEFORE_PAYMENT`).
- [x] #10 Regla de edad: prompt con ejemplos; `_age_has_unit` + `_missing_route_field` tratan la edad sin unidad como faltante para repreguntar.
- [x] #17 Ortografía forzada: `_normalize_name_fields()`/`_titlecase_value()` aplican Mayúscula inicial a clinic_name, patient_name, species, breed, owner_name, requesting_doctor. No toca exam_type ni observations.
- Resultado: `tests/` verde (86 en test_agent_flows).

### FASE 2 — Menú y confirmación de cierre ✅ COMPLETA
Archivos: `prompt.py`, `agent.py`
- [x] #3 Menú numerado (Etapa 3): el `WELCOME_MESSAGE` ahora ofrece `1 Programar · 2 Resultados · 3 Pagos · 4 Otro` y el prompt mapea la respuesta numérica al intent (1→route, 2→results, 3→accounting, 4→unknown/derivar).
- [x] #12 Confirmación editable: nueva `_enforce_confirmation_step` intercepta el cierre y muestra el resumen "Antes de registrar… ¿Confirmas? (Sí / Corregir)" en `fase_4_confirmacion` sin registrar. Al confirmar, el pipeline cierra (fase_6/fase_7) y crea la request. "Corregir <campo>" se resuelve con short-circuit determinista (`_detect_correction_field`/`_clear_field_for_correction`) que limpia el campo y lo repregunta. Refactor: `_order_summary_lines` (compartido cierre/confirmación), `_finalize_request` y `_persist_turn`.
- Resultado: suite verde (176 pasan). Se reescribieron los tests de cierre al flujo de 2 turnos y se añadieron tests del mecanismo de corrección.

### FASE 3 — Pago en línea ✅ COMPLETA
Archivos: `schema.py`, `prompt.py`, `agent.py`, `dashboard.py`
- [x] #6 `payment_method` enum ahora `["contraentrega", "pago_linea"]` (reemplaza "contado"). `pago_linea` → registra la orden con su N°, `requires_handoff=true`, `handoff_area=contabilidad`, y reply `PAYMENT_ONLINE_HANDOFF_MESSAGE` ("contabilidad te contactará en breve para enviarte el link… la recogida sigue programada"). Ajustados `_enforce_payment_step`, `_apply_handoff_guardrails`, `PAYMENT_METHOD_QUESTION`, prompt PASO 4 y reglas de negocio. Etiquetas legibles (`PAYMENT_METHOD_LABELS`) en el dashboard/print.
- Resultado: suite verde (176 pasan). Nuevo `test_route_with_pago_linea_sets_accounting_handoff_and_creates_request`; tests de pago y dashboard actualizados.

### FASE 4 — Identificación ✅ COMPLETA
Archivos: `agent.py`, `db.py`, `main.py`, `prompt.py`
- [x] #2 Bloqueo de cliente final: al detectar `_is_final_user_text` se marca `captured_fields._blocked` y se persiste. `process_turn` retorna `None` si la sesión está bloqueada; `main.py` (telegram y chatwoot) no envía nada cuando el reply es `None`.
- [x] #13 Sucursales: nuevo `db.find_clients_by_tax_id` devuelve todas las sedes con ese NIT. Si hay >1 → se listan con `_client_match_options` y `_client_match_options_reply` detecta sedes del mismo cliente ("¿Desde cuál sede solicitas?"). Selección por número. Corregido el descarte de opciones para no perder las sedes cuando el NIT viene preservado.
- [x] #14 Cliente nuevo: regla vigente del chatbot = escalar inmediatamente a operaciones/recepción sin capturar datos en chat. El alta y la revisión pendiente se gestionan desde la plataforma/dashboard, no desde Telegram. Las sesiones legacy que ya estaban en Flujo B se siguen atendiendo para no dejarlas colgadas.
- Resultado: suite verde (181 pasan en ese momento). Tests de identificación migrados a `find_clients_by_tax_id`; el comportamiento vigente queda documentado en `tasks/errores-soluciones.md`.

### FASE 5 — Negocio / datos ✅ COMPLETA
Archivos: `config.py`, `rules.py`, `prompt.py`, nueva migración `011`
- [x] #15 Descuentos parametrizables: `DISCOUNT_TIERS: list[tuple[int, float]] = []` en `config.py`; `calculate_discount` aplica el porcentaje del mayor tramo alcanzado. Vacío → 0 (sin cambios de comportamiento hasta tener la tabla real).
- [x] #16 N° orden anual: migración `011_order_number_yearly.sql` con `order_number_counters` + función `next_order_number()` que genera `A3-<año>-<seq 3 díg>` reiniciando por año (zona America/Bogota) y cambia el DEFAULT de la columna. `create_request` ya lee el valor generado (sin cambio de código, defensivo). R17 del prompt actualizada al formato `A3-2026-001`.
- ⚠️ La migración `011` debe aplicarse manualmente en el SQL Editor de Supabase.
- Resultado: suite verde (183 pasan). Nuevos tests de `calculate_discount` (tramos vacíos y configurados).

### Verificación
- Correr `tests/` tras cada fase y actualizar los tests afectados (test_agent_flows, test_db_identification).
- Demostrar cada fase con un flujo de ejemplo antes de marcar completa.

---

## Número de orden legible (A3-00042) — Plan, pendiente de aprobación

### Objetivo
Al cerrar una orden de servicio, generar un número legible y secuencial
(`A3-00042`), guardarlo asociado al pedido en `requests`, mostrarlo al cliente
en el cierre y poder dárselo si lo pide por chat. El AI NUNCA inventa el número.

### Decisiones
- Formato: `A3-00042` (prefijo + secuencial continuo, 5 dígitos, sin año).
- Consulta por chat: devuelve la ÚLTIMA orden del cliente identificado.
- Migración DDL: la aplica el usuario en el SQL Editor de Supabase (no hay
  `SUPABASE_ACCESS_TOKEN` en `.env`).

### Diseño
1. **`db/migrations/010_order_number.sql`** (aplicar en Supabase):
   - `CREATE SEQUENCE request_order_seq`
   - `ALTER TABLE requests ADD COLUMN order_number text UNIQUE DEFAULT
     ('A3-' || lpad(nextval(...),5,'0'))` → cada INSERT genera el número solo.
2. **`app/services/db.py`**:
   - `create_request` devuelve `{request_id, order_number}` (lee el campo que la
     BD generó por DEFAULT). Defensivo: si la columna no existe → `order_number=None`.
   - `get_last_order_for_client(client_id)` → última request con su número.
3. **`app/agent.py`**:
   - Crear la request ANTES de armar el reply de cierre, capturar `order_number`
     y añadir "Número de orden: A3-00042" al mensaje (defensivo si es None).
   - Heurística `_is_order_number_query()` + short-circuit: si el cliente
     identificado pregunta su número, responder con el real de la BD (sin AI).
4. **`app/prompt.py`**: regla R17 — nunca inventar números de orden.
5. **Tests**: cierre incluye el número; consulta devuelve el número; la heurística
   no se dispara con "crear otra orden".

### Compatibilidad
- El cierre de órdenes es defensivo: si la migración aún no se aplicó, el insert
  no cambia y simplemente no se muestra número (no rompe producción).

### Items
- [x] Migración `010_order_number.sql`
- [x] `db.py`: create_request devuelve número + get_last_order_for_client + list_requests trae order_number (select defensivo `*`)
- [x] `agent.py`: número en cierre + consulta por chat (`_is_order_number_query` short-circuit)
- [x] `prompt.py`: R17
- [x] `dashboard.py`: order_number en service_order_rows, sample lanes y operation center
- [x] templates: dashboard.html (ficha) + service_order_print.html (título y cuerpo)
- [x] Tests + verificación: 176 passed (5 nuevos)

### Resultado (2026-06-01)
Número de orden `A3-00042` implementado punta a punta. El cliente lo recibe al
cerrar la orden y puede pedirlo por chat ("¿cuál es el número de mi orden?"); el
dashboard lo muestra en la ficha, la vista de impresión y el seguimiento de
muestras. Defensivo: si la migración no está aplicada, no rompe (no muestra número).
Sin fallos del agente en esa verificación.

**PENDIENTE DEL USUARIO:** aplicar `db/migrations/010_order_number.sql` en el SQL
Editor de Supabase (no hay SUPABASE_ACCESS_TOKEN para aplicarla por script).

---

## Mensaje "déjame revisar los registros" antes del lookup de cliente — En curso

### Objetivo
Cuando el usuario da NIT o nombre de veterinaria y el bot va a buscarlo en la BD,
mandar primero un mensaje intermedio ("Permíteme un momentico mientras reviso
nuestros registros 🔍") con indicador de "escribiendo…" y pausa de ~1.5s, antes de
decir si está registrado o no.

### Diseño
- `process_turn` recibe callback opcional `on_progress(msg)` (default None) → no
  rompe firma ni tests existentes.
- El agente llama `on_progress(...)` UNA sola vez, justo antes de tocar la BD para
  la primera búsqueda de cliente por NIT/nombre.
- El webhook (main.py) implementa `on_progress`: manda el mensaje, activa "escribiendo…"
  y espera ~1.5s. Respeta separación de capas (agent no importa telegram/chatwoot).
- El mensaje de progreso es efímero: NO se persiste en conversation_messages.

### Items
- [x] `app/services/telegram.py`: `send_typing(chat_id)` → sendChatAction typing
- [x] `app/services/chatwoot.py`: `send_typing(conversation_id)` → toggle_typing_status on
- [x] `app/agent.py`: constante + param `on_progress` + llamada antes del lookup
- [x] `app/main.py`: `on_progress` en ambos webhooks
- [x] Verificar: 171 passed (2 tests nuevos del callback) + Flask reiniciado y /health OK

### Resultado (2026-06-01)
Implementado con callback `on_progress`. El agente avisa "Permíteme un momentico
mientras reviso nuestros registros 🔍", activa "escribiendo…" y espera 1.5s antes
de confirmar si el cliente está registrado. Tests: 171 passed.

---

## Agente Conversacional — Completado

### Core (Bloques 1–4)
- [x] `schema.py` → 10 campos, intents en inglés, 8 fases nombradas, message_mode, pending_intents, confidence
- [x] `prompt.py` → system prompt limpio, sin JSON embebido
- [x] `rules.py` → INTENT_TO_SERVICE_AREA + TERMINAL_PHASES
- [x] `db.py` → get_or_create_session, update_session, create_request alineados con modelo real
- [x] `agent.py` → pending_intents entre turnos, transición a fase terminal
- [x] `ai.py` → recibe pending_intents, filtra campos internos

### Tests obligatorios — 11/11 ✓
- [x] Test 1: cliente con motorizado asignado → solicitud `assigned`
- [x] Test 2: cliente sin motorizado → `error_pending_assignment` + evento en `request_events`
- [x] Test 3: cliente nuevo → `fase_7_escalado` inmediato, sin recolectar datos
- [x] Test 4: solicitud post-17:30 → `scheduled_pickup_date` = siguiente día hábil
- [x] Test 5: múltiples intenciones en un mensaje → ambas procesadas en orden correcto
- [x] Test 6: usuario repite sin dar dato → agente ofrece opciones en vez de preguntar de nuevo
- [x] Test 7: usuario cancela solicitud en curso → cancelación confirmada, flujo limpio
- [x] Test 8: conversación interrumpida y retomada → sin saludo, continúa donde estaba
- [x] Test 9: gestión de pagos → derivación inmediata a contabilidad
- [x] Test 10: alta de cliente nuevo → derivación inmediata a operaciones
- [x] Test 11: toda solicitud de ruta → priority siempre "normal" en BD

### Modificaciones V2.1 (llamadas con cliente)
- [x] Preguntas conversacionales, una por turno (no formulario)
- [x] Búsqueda progresiva de cliente: NIT → nombre → escalada
- [x] Forma de pago: contado vs contraentrega (PASO 4 del flujo)
- [x] Recolección conversacional: exam_type → patient_name → species (patient_age/owner_name opcionales)
- [x] "Crear tu perfil": selected_tests, catálogo individual, cálculo de subtotal/total
- [x] Chat permanece abierto: solo cierra con despedida explícita del usuario
- [x] Notificación del motorizado al cerrar orden (`agent.py` → append a reply)
- [x] Múltiples órdenes en misma sesión: reset de campos de orden al retomar desde fase terminal

---

## Agente Conversacional — Pendiente

### Tests nuevos (V2.1)
- [x] Múltiples órdenes en misma sesión: segunda orden con cliente ya identificado
- [x] "Crear tu perfil": seleccionar análisis individuales, ver subtotal calculado
- [x] Notificación de motorizado: mensaje incluido en cierre de orden

---

## Plataforma Interna — Pendiente (NO es el agente conversacional)

Estas funciones se implementarán en la plataforma de gestión, no en el chatbot.

- [ ] **Descuentos por cantidad**: `calculate_discount()` en `rules.py` es placeholder (retorna 0). Las reglas de descuento las define el cliente y se configuran desde la plataforma. La BD las persiste; el agente solo las lee.
- [ ] **Asignación por zonas geográficas**: hoy el agente asigna por `client_courier_assignment` (tabla por cliente). La asignación por zona requiere la tabla de zonas que define el cliente; se gestiona desde la plataforma.
- [ ] **Integración ANARVET**: consulta de estado de análisis. La plataforma expone el estado; el agente lo consumirá vía endpoint interno cuando esté disponible.
- [ ] **Gestión de zonas y motoristas**: calendario de repartidores, asignación manual de override, edición de zonas.
- [ ] **Dashboard y reportes**: órdenes por día, por motorista, por zona, perfiles más solicitados.
- [ ] **Gestión de clientes**: alta manual, edición de datos, vinculación a zona.
- [ ] **Gestión de portafolio**: cargar nuevo catálogo, editar precios, definir perfiles predefinidos.

### Información pendiente del cliente (bloquea algunas de las anteriores)
- [ ] Números de teléfono para escalar contabilidad/pagos y PQRs
- [ ] Definición de zonas geográficas (número, descripción, motorista asignado)
- [ ] Tabla de descuentos por cantidad de parámetros
- [ ] Estructura de perfiles predefinidos en el catálogo
- [ ] API ANARVET: endpoint, autenticación, datos expuestos

---

## Resultados

**2026-04-27** — Bloques 1-4 completados.
**2026-04-30** — Tests obligatorios validados: 11/11 completados.
**2026-05-01** — Flujo de búsqueda progresiva + forma de pago cerrados para V2.1.
**2026-05-03** — Separación plataforma vs. agente documentada. Notificación de motorizado y múltiples órdenes en sesión implementadas en `agent.py`.
**2026-05-11** — Tests V2.1 pendientes cubiertos y suite validada: 64/64.
**2026-05-11** — Alta manual de clientes en dashboard afinada: validación de formulario, motorizado sugerido y contexto de motorizados cubiertos por tests. Suite validada: 68/68.
**2026-05-15** — Zonas territoriales A3 estructuradas: `data/barrios_zonas_a3.csv`, `app/territory.py`, migración `006_territorial_zones.sql` y scripts de carga. Supabase actual: 8 motorizados verificados y 282 asignaciones cliente→motorizado cargadas. Pendiente aplicar migración con credencial admin SQL para subir 1649 barrios.
**2026-05-15** — Alta manual de cliente ahora sugiere motorizado automaticamente por barrio/localidad/zona, con override manual del operador. Endpoint `GET /api/dashboard/courier-suggestion` y guardado de `courier_suggestion` en revisión. Suite validada: 83/83.
**2026-05-15** — Autocompletado de barrios agregado en alta manual: `GET /api/dashboard/neighborhood-search`, autollenado de localidad/zona y sugerencia de motorizado. Suite validada: 84/84.
**2026-06-13** — Allegra queda fuera de alcance por ahora: eliminados scripts/tests activos que dependían de Excel externo. `pytest` completo queda verde (214 passed). Auditoría Supabase read-only: core/catálogo/órdenes/etiquetas OK; tablas territoriales de migración `006` aún no están en Supabase (warning no bloqueante para el bot principal).
**2026-05-15** — Flujo de migracion territorial cerrado: script `apply_supabase_migration.py` para aplicar DDL con `SUPABASE_ACCESS_TOKEN`, seed territorial idempotente y runbook actualizado. Service role key no permite crear tablas.
**2026-05-15** — Proyecto autosuficiente con `.env` local protegido por `.gitignore`; seeds corren sin rutas antiguas. Operacion territorial funcional con fallback interno hasta que existan tablas territoriales en Supabase.
**2026-05-15** — Centro Operativo Diario agregado en `/operacion`: KPIs de rutas, aprobaciones, muestras abiertas, alertas, rutas por gestionar y clientes nuevos. Suite validada: 85/85.
**2026-05-15** — Agenda por motorizado agregada dentro de `/operacion`, agrupando rutas activas por mensajero y columna `Sin asignar`. Suite validada: 86/86.
**2026-05-24** — Orden de servicio conversacional alineada al PDF oficial: datos completos antes de pago/cierre, persistencia en `request_events.event_payload.service_order`, vista Supabase `service_orders` preparada y PDF guardado en `docs/forms/orden-de-servicio-2025.pdf`. Suite validada: 131/131.
**2026-05-24** — Plataforma muestra ordenes de servicio del agente en `/operacion` y `/muestras`, con ficha visual tipo formulario y tarjetas derivadas en proceso de muestras. Suite validada: 133/133.
**2026-05-24** — Agregada vista imprimible de orden de servicio en `/ordenes-servicio/<request_id>/imprimir`, accesible desde las fichas como `Imprimir PDF` para imprimir o guardar desde el navegador. Suite validada: 134/134.
**2026-05-24** — Flujo multiorden ajustado: al cerrar una orden el agente pregunta si necesita otra para otro paciente/animal; respuesta afirmativa inicia nueva orden sin reidentificar cliente y respuesta negativa cierra la conversacion. Suite validada: 137/137.

**2026-06-13** — Memoria entre órdenes mejorada + captura de varios análisis sin bucle. (1) Al crear una orden de seguimiento el agente reusa los datos estables (médico, dirección, pago) de la orden anterior y los confirma en bloque (`_carry_over_stable_fields` + flag `_stable_confirm_pending`), en vez de repreguntarlos en blanco; el reconocimiento de "el mismo" se amplió y ahora cae a `_client_memory` aunque no haya snapshot (resolución determinística sin AI). (2) Nuevo guardrail `_enforce_multiple_tests_capture`: si el cliente pide varios análisis en un mensaje y cada ítem mapea 1:1 al catálogo, los registra como perfil personalizado sin repreguntar el tipo (evita bucle); si hay ambigüedad, deja el flujo normal. Prompt R24 agregada. Suite validada: 221/221 + 6/6 flujos con modelo real.

**2026-06-13** — Tres mejoras de robustez del agente (ordenado y sin loops): (#1) backstop determinístico `_enforce_custom_profile_close`: el perfil personalizado armado desde cero se cierra y fija `exam_type` cuando el cliente lo pide, sin depender del modelo (evita el bucle "¿agregás otro o cerramos?"). (#6) Eliminado el "Flujo B" muerto de cliente nuevo (`_start_new_client_capture`, `_handle_new_client_capture`, `_save_new_client_pending`, constantes `_nc_*`/`NEW_CLIENT_*`, `ai.interpret_nc_step`): nunca se invocaba y contradecía la regla "el bot nunca registra cliente nuevo"; sesiones viejas con `_nc_capturing` se auto-sanan y escalan por el flujo normal. (#3) Resume determinístico de intenciones: "resultados + recogida" en un mensaje ya no pierde la ruta — entrega el mensaje fijo de resultados y retoma la recogida en el mismo turno (`_enforce_results_message`). Suite: 222/222 + 6/6 flujos con modelo real.
