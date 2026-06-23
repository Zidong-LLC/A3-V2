# Errores y soluciones del agente conversacional

Este documento es la bitacora viva del agente de Telegram/Chatwoot. Se actualiza con cada bug conversacional, cambio de flujo o decision que afecte lo que el cliente ve.

Regla operativa: ningun bug conversacional se cierra sin prueba de regresion o justificacion, actualizacion de este documento y validacion del flujo afectado.

---

## Estado de flujos

| Flujo | Estado actual | Riesgo principal | Referencias |
|---|---|---|---|
| Bienvenida y menu | Implementado con opciones 1-4 | Mantener menú sincronizado entre bienvenida y reconsideración | `app/agent.py`, `app/prompt.py` |
| Programar recogida | Implementado punta a punta | Archivo `agent.py` concentra demasiada logica | `app/agent.py`, `app/services/db.py` |
| Identificacion cliente | Implementado por NIT/nombre y opciones de sedes | Captura incorrecta si el mensaje no responde la pregunta | `app/agent.py`, `app/services/db.py` |
| Confirmacion direccion | Implementado con confirmacion tolerante | Faltan mas regresiones para lenguaje natural | `app/agent.py` |
| Orden de servicio | Implementado con confirmacion editable | Orden vive duplicada en prompt y guardrails | `app/prompt.py`, `app/agent.py` |
| Catalogo/perfiles | Implementado con perfiles, areas y personalizados | I/O de catalogo debe estar siempre protegido por guards | `app/agent.py`, `app/services/db.py` |
| Pagos | Implementado: contraentrega o pago en linea con contabilidad | Mantener enum y mensajes sincronizados con contabilidad | `app/agent.py`, `docs/decisions/002-payment-method-in-flow.md` |
| Resultados | Formalizado en V1 como mensaje fijo de no disponibilidad | Implementación real depende de integración futura | `app/agent.py`, `docs/architecture.md` |
| Cliente nuevo | Corregido: escala sin capturar datos en chat | Alta queda para recepción/plataforma | `app/agent.py`, `app/services/db.py` |
| Cliente particular | Implementado con bloqueo de sesion | Puede impedir recuperacion si el usuario luego da datos validos | `app/agent.py` |
| Opcion 4 / otro | Corregido: handoff deterministico a operaciones | Debe mantenerse fuera del flujo de recogida | `app/agent.py` |
| Chatwoot | Usa `process_turn(channel="chatwoot")`, persiste canal y asigna equipo si hay handoff | Riesgo de sesiones legacy creadas antes del fix | `app/main.py`, `app/services/db.py` |

---

## Errores abiertos

### RESUELTO-024 — Tras rechazar la lista de coincidencias, identificaba por match parcial en vez de tratar como cliente nuevo (2026-06-23)

- **Síntoma (reporte del usuario, 2026-06-23):** "Pet colombia" → el bot lista 2 coincidencias
  parciales (Pet Agro Colombia, Vets&Pets Colombia). El usuario responde "Ninguno de esos" y
  luego "mi veterinaria se llama Pets Colombia"; el bot igual identificaba "Vets&Pets Traiding
  Colombia SAS" por match parcial y seguía pidiendo dirección. Entraba en bucle.
- **Regla de negocio (confirmada por el usuario, flujo definitivo):**
  1. 1ª búsqueda por nombre = PARCIAL → muestra lista de coincidencias.
  2. El cliente elige una → identifica.
  3. El cliente dice que ninguna es la suya ("ninguno de esos", "no es esa") → el bot REPREGUNTA
     el nombre exacto (o el NIT). No escala todavía.
  4. Con ese nombre → búsqueda EXACTA: si existe → identifica; si no → "¿Eres cliente nuevo?".
  5. El cliente confirma que es nuevo → escala a un humano (recepción).
- **Causa raíz:** (a) una coincidencia parcial ÚNICA se auto-identificaba sin confirmar
  ("Pets Colombia" → "Vets&Pets Traiding Colombia SAS"); (b) "ninguno de esos" disparaba
  `says_new_client` y escalaba directo en vez de repreguntar; (c) el reintento usaba búsqueda
  parcial otra vez.
- **Solución (`app/agent.py` + `app/services/db.py`):**
  - Nueva `db.find_client_exact(name)`: match por nombre normalizado estricto (sin acentos/símbolos).
  - 1ª búsqueda: identifica directo SOLO si hay match exacto; si las coincidencias son parciales
    (una o varias) se muestran como lista (mensaje de 1 coincidencia ajustado).
  - Con lista pendiente, "ninguno de esos" ya NO dispara `says_new_client` (`has_pending_matches`):
    limpia la lista, marca `_awaiting_exact_name` y repregunta el nombre exacto.
  - Turno siguiente con `_awaiting_exact_name`: SOLO `find_client_exact` (nombre del LLM + palabras
    significativas del mensaje, filtrando `_EXACT_RETRY_STOPWORDS`). Si no hay exacto → no
    encontrado → "¿Eres cliente nuevo?"; al confirmar, escala a recepción.
  - Helpers `_rejects_match_options`, `_EXACT_RETRY_STOPWORDS`.
- **Verificación:** rechazo→repregunta→no exacto→"¿nuevo?"→escala; rechazo→repregunta→exacto
  ("Pet Agro Colombia")→identifica; selección por número y primer intento parcial intactos.
  Suite: 144 passed (3 fallos pre-existentes de dashboard).
- **Estado:** ✅ CORREGIDO.

### RESUELTO-023 — Paciente sin propietario (callejero/rescatado) no se podía registrar (2026-06-23)

- **Síntoma (QA de flujo, 2026-06-23):** al pedir el propietario, si el cliente respondía
  "ninguna" / "no tiene dueño" / "es callejero", el bot no lo aceptaba y repetía la pregunta.
- **Regla de negocio (confirmada por el usuario, 2026-06-23):** se PERMITE registrar sin
  propietario; se guarda como "Sin propietario" y se avanza.
- **Solución (`app/agent.py`):** helper `_says_no_owner` (frases/tokens: "sin dueño",
  "no tiene propietario", "ninguna", "callejero", "rescatado", etc.). En el pipeline, si se está
  pidiendo el propietario (`_detect_which_field_is_being_asked == "owner_name"`) y el cliente
  indica que no hay, se setea `owner_name = "Sin propietario"` y el flujo continúa. Acotado a ese
  paso para que "ninguna" sea inequívoco y no afecte otros campos.
- **Verificación:** "ninguna" / "es callejero, no tiene dueño" / "no tiene propietario" →
  `owner_name="Sin Propietario"` y avanza; "Carlos Pérez" → se captura normal. Suite: 144 passed.
- **Estado:** ✅ CORREGIDO.

### OBSERVADO — Dos puntos de baja severidad que NO requieren acción (2026-06-23)

- **Multi-análisis con término ambiguo** ("hemograma, química y orina"): el bot abre el submenú del
  área ambigua (química) primero, pero NO pierde los concretos — los mantiene pendientes
  ("También tengo pendiente el hemograma…") y los resuelve después. Funcionalmente correcto; tocar
  el orden de resolución del catálogo sería un refactor riesgoso por una preferencia de UX. **No se toca.**
- **Corrección inline durante la captura** ("el paciente se llama Max no Firulais" mientras se pide
  la raza): el dato SÍ se corrige (`patient_name` pasa a Max) y se ve corregido en el resumen final;
  solo falta una confirmación verbal en el momento. Cosmético, sin pérdida de datos. No amerita
  tocar el flujo de captura aprobado. **No se toca** (documentado por si se prioriza a futuro).

### RESUELTO-022 — Anti-bucle escalaba a humano aunque el cliente diera datos válidos en desorden (2026-06-23)

- **Síntoma (QA de flujo, 2026-06-23):** al pedir el médico solicitante, si el cliente daba datos
  del paciente en otro orden (especie, raza, análisis…), tras ~3 turnos el bot escalaba a una
  persona ("Te voy a comunicar con una persona del equipo"). Intermitente (depende de cuántos
  turnos seguidos marque el LLM como `unclear`).
- **Causa raíz:** el contador anti-bucle (`_offtrack_count`) sumaba un turno perdido siempre que
  `signal in (unclear, off_topic)` o se repetía la pregunta, SIN mirar si el turno había
  capturado un dato nuevo de la orden. Un cliente que colabora dando datos (aunque no en el orden
  pedido) acumulaba "turnos perdidos" y disparaba el escalado.
- **Solución (`app/agent.py`):** antes de incrementar `_offtrack_count`, se mide si hubo PROGRESO
  (más campos de `_ROUTE_REQUIRED_FIELDS` con valor que en el turno anterior). Si hubo progreso, se
  resetea el contador a 0; el anti-bucle solo incrementa/escala cuando NO hay avance. Así se
  preserva la protección contra bucles reales (cliente que no aporta nada) sin castigar al que sí
  colabora.
- **Verificación:** 5/5 corridas dando datos en desorden → 0 escalados indebidos (antes
  intermitente). Bucle real sin aportar datos → el bot reencauza/escala como corresponde. Suite:
  144 passed (3 fallos pre-existentes de dashboard).
- **Estado:** ✅ CORREGIDO.

### RESUELTO-021 — Multi-orden ignoraba el cambio de análisis pedido en el mismo mensaje (2026-06-23)

- **Síntoma (QA de flujo, 2026-06-23):** al pedir "otra orden con los mismos datos pero cambiale
  el análisis a glucosa", el bot mantenía el análisis de la orden anterior (hemograma) e ignoraba
  el cambio. El `exam_type` quedaba pegado al viejo.
- **Causa raíz:** el trigger de "otra orden" (`_explicitly_wants_another_order`) disparaba
  `_begin_followup_order`, que heredaba el análisis del snapshot y devolvía la respuesta fija
  ("Mantengo estos datos…") SIN leer el resto del mensaje. El cambio explícito se perdía.
  Nota de diseño: mantener datos previos es INTENCIONAL (ver [[project_multiorden_intent]]); el
  cliente puede querer "otra orden, mismos datos, cambiá solo X".
- **Solución (`app/agent.py`):** `_begin_followup_order`/`_start_followup_service_order_response`
  reciben el `user_message`. Nuevo helper `_followup_wants_new_analysis` detecta cuando el cliente
  pide cambiar el análisis en ese mensaje (nombra análisis/examen/perfil + señal de cambio). En ese
  caso NO se hereda el análisis viejo: queda vacío y se pide explícitamente, capturándolo por el
  flujo normal de catálogo (validado contra el catálogo real). **No se adivina el análisis de la
  frase**: un primer intento de extraer tokens sueltos capturaba basura ("urianálisis" → "ALT (GPT)";
  "glucosa" → "Perfil de 2 análisis"), así que se descartó por riesgo de registrar uno equivocado.
- **Verificación:** "otra orden … cambiale el análisis a glucosa" → pide análisis → "glucosa" →
  `exam_type='Glucosa'`. "otra orden para otro paciente" (sin mencionar análisis) → hereda
  "Cuadro Hemático Completo" (feature intacta). Suite: 144 passed (3 fallos pre-existentes de dashboard).
- **Estado:** ✅ CORREGIDO. La captura inline del análisis nuevo en el mismo mensaje (sin turno
  extra) queda como mejora futura, hecha de forma robusta (no por tokens sueltos).

### RESUELTO-020 — Nombres de clínica con "Colombia"/"Bogotá" no se identificaban (el código decidía por palabras sueltas, no por el mensaje completo) (2026-06-23)

- **Síntoma (reporte del usuario, 2026-06-23):** al pedir el identificador y responder con el
  nombre de una veterinaria registrada que contiene "Colombia" o "Bogotá" (ej. `Pet Agro Colombia`),
  el bot contestaba `Estoy bien, gracias. Somos A3 Laboratorio Clínico Veterinario y estamos en
  Bogotá, Colombia...` y volvía a pedir el NIT, sin buscar el cliente. Entraba en bucle.
- **Evidencia:** reproducido 5/5 con `process_turn` (flujo `Hola → 1 → Pet Agro Colombia`).
  Instrumentando se vio que en ese turno **el LLM ni se invocaba**: el reply venía de
  `_pre_identification_service_info_response`. El LLM aislado entendía `Pet Colombia` perfecto
  (`user_intent_signal=provides_client_identifier`).
- **Causa raíz:** `_pre_identification_service_info_response` decidía el sentido del mensaje por
  tokens sueltos. La rama de ubicación se disparaba con `tokens & {"colombia","bogota","bogotá"}`,
  es decir, por la MERA aparición de la palabra, aunque el mensaje completo fuera el nombre de una
  clínica. Cortaba el turno antes del LLM y nunca capturaba ni buscaba. Afectaba a toda clínica con
  "Colombia"/"Bogotá" en el nombre (`Pet Agro Colombia`, `Vets&Pets Traiding Colombia SAS`, etc.).
- **Solución (3 cambios mínimos en `app/agent.py`, principio: el LLM lee todo, el código hace cumplir reglas):**
  1. El atajo de "info de servicio" ya no corre cuando estamos esperando el identificador
     (`and not _awaiting_client_identifier(history)`): en ese momento el mensaje completo va al LLM.
  2. La rama de ubicación solo se activa ante una PREGUNTA explícita de dónde estamos
     (`donde/ubicados/ubican/...`), no por la mención de "Colombia"/"Bogotá".
  3. `_apply_identification_fallbacks` respeta la lectura del LLM: si el modelo marcó el turno como
     `side_question` (una pregunta como "¿dónde están?", "¿cuánto cuesta el hemograma?"), el fallback
     de "nombre pelado" ya NO fabrica un `clinic_name` con la pregunta.
- **Auditoría de identificación (QA dirigido, 2026-06-23):** se estresó identificación por NIT
  (con/sin guion, normalización, inexistente, incompleto), por nombre (parcial "San", mal escrito sin
  tildes, profesional individual "Dr. X", inexistente, "soy de X"), off-topic y seguridad. **Único bug
  real era el de "Colombia".** Seguridad robusta: no lista la base, no obedece jailbreak, no inventa NIT.
- **Verificación:** `Pet Agro Colombia` y `Vets&Pets Colombia` ahora se identifican; `¿dónde están
  ubicados?` responde la ubicación y re-pide el NIT (no lo busca como nombre); NIT/"San"/"Dr. Luis
  Sandoval"/"soy de Petland" siguen OK. Suite: `python -m pytest -q` -> 144 passed (3 fallos
  pre-existentes en `test_dashboard.py`, ajenos a este cambio).
- **Estado:** ✅ CORREGIDO. Pendiente validar en Telegram en vivo.
- **Riesgo residual:** `_awaiting_client_identifier` aún detecta por presencia de "nit" en el último
  mensaje del bot; si el LLM cambia esa redacción, el fallback se debilita. Caso menor: pregunta de
  precio pre-identificación responde "Perfecto, lo anoto..." en vez de mostrar el valor (no rompe flujo).

### RESUELTO-019 — Orden registrada no aparecía como borrador en Alegra por contacto duplicado con NIT/DV (2026-06-22)

- **Síntoma (reporte del usuario, 2026-06-22):** la conversación cerró y registró la orden de
  `Animal Pets`, pero la factura borrador no apareció reflejada en Alegra.
- **Evidencia:** Supabase sí creó la orden `7c74b1ac-2124-4117-ad69-6cb297dc497f` con evento
  `created`, perfil base `152` ($24.000), agregado `1507 Cortisol en Orina` ($33.000) y total
  $57.000. La sesión tenía `tax_id` en `captured_fields`. No existía evento `alegra_invoiced`.
  El log local mostró: `Alegra POST /contacts -> HTTP 400`, code `2006`, `Ya existe un contacto
  con la identificación 53115419`, `contactId=3`, DV `1`.
- **Causa raíz:** `find_contact_by_nit` buscaba el NIT tal como venía de Supabase
  (`53115419-1`). En Alegra el contacto existente estaba guardado como identificación
  `53115419` + `identificationObject.dv=1`. El lookup no lo encontró, `get_or_create_contact`
  intentó crear el contacto y Alegra rechazó el duplicado antes de crear la factura.
- **Solución:** `get_or_create_contact` ahora, si no encuentra el NIT original, separa número/DV
  con `_split_nit` y busca también por el número sin DV antes de hacer `POST /contacts`.
- **Tests:** `tests/test_alegra_billing.py::test_contact_lookup_retries_without_dv_before_create`.
  Suite enfocada: `python -m pytest tests/test_add_analysis_during_adjustment.py tests/test_extra_analysis_offer.py tests/test_alegra_billing.py` -> 21/21.
- **Estado:** ✅ CORREGIDO TÉCNICAMENTE. No se creó retroactivamente la factura de esa orden para
  evitar duplicados sin autorización; validar con la próxima orden real o crear ese borrador manualmente si se necesita.

### RESUELTO-018 — “Perfil 152 más un análisis extra” seleccionaba solo el perfil y descartaba el extra (2026-06-22)

- **Síntoma (reporte del usuario, 2026-06-22):** al responder en un solo mensaje algo como
  `sí quiero el perfil 152 más un análisis extra`, el bot registraba correctamente el perfil 152,
  pero no entendía la segunda parte. Contestaba la oferta genérica `¿Quieres agregar otro análisis
  o perfil...? Si ya está, seguimos con el pago`, aunque el usuario ya había dicho que quería un
  análisis extra.
- **Causa raíz:** `_wants_partial_analysis_change` detectaba ajustes parciales por verbos
  (`agregar`, `agrégale`, `sumar`, etc.) o marcadores con `el mismo`, pero no por la forma natural
  `análisis extra/adicional`. Además, cuando la selección del perfil venía desde
  `_profile_menu_options`, `_capture_profile_menu_selection` recibía solo la opción elegida y no el
  mensaje completo del usuario, por lo que no podía consumir la intención compuesta.
- **Solución:**
  1. `_wants_partial_analysis_change` ahora trata `análisis/prueba/examen + extra/adicional` como
     ajuste parcial del perfil base.
  2. Se centralizó la respuesta de “perfil seleccionado + agregar algo” en
     `_selected_profile_addition_response` y se usa tanto para selección por código como para
     selección desde menú.
  3. `process_turn` ahora pasa el `user_message` a `_capture_profile_menu_selection` para no perder
     el resto del turno.
- **Tests:** `tests/test_add_analysis_during_adjustment.py` cubre el código directo y el menú de
  perfiles con `si quiero el perfil 152 mas un analisis extra`. Suite enfocada: 21/21.
- **Estado:** ✅ CORREGIDO TÉCNICAMENTE. Pendiente re-prueba conversacional en vivo.

### RESUELTO-017 — Paso "¿agregar otro análisis/perfil?" antes del resumen final (2026-06-22)

- **Pedido del usuario (2026-06-22):** antes de pasar al resumen final, el bot debe ofrecer
  agregar otro análisis, otro perfil o personalizar, y repetir esa oferta tras cada agregado
  hasta que el cliente decida seguir. Todo con datos reales de la BD, sin inventar.
- **Riesgo:** es la zona del bucle histórico "¿agregás otro análisis?" (ver RESUELTO-013/014).
  Por eso la salida tiene que ser robusta (no quedar atrapado pidiendo "¿algo más?").
- **Solución:**
  1. `_analysis_settled_response`: punto único tras fijar/ajustar el análisis. Si la orden ya
     tiene análisis y solo falta el pago, OFRECE agregar más (`EXTRA_ANALYSIS_OFFER`, con salida
     explícita "si ya está, seguimos con el pago") y marca `_offering_extra_analysis`. Lo usan
     todas las vías de captura (perfil por código, menú de recomendación, menú de área,
     múltiples análisis).
  2. `_handle_extra_analysis_answer` (pre-modelo): interpreta la respuesta — sigue al pago
     (`_wants_to_proceed_to_payment`), agrega un análisis nombrado, abre menú de área que SUMA,
     lista perfiles, o pide "¿cuál?" ante un "sí" suelto. Tras cada agregado vuelve a ofrecer.
  3. `_enforce_extra_analysis_offer`: misma oferta cuando el análisis lo captura el modelo por
     texto libre. `_enforce_payment_step` y `_enforce_first_missing_after_progress` respetan
     `_offering_extra_analysis` (no pisan la oferta con la pregunta de pago).
- **Bug encontrado y corregido al probar:** `_wants_to_proceed_to_payment` armaba el texto
  normalizado desde un `set` (orden no determinista) → el match de frases ("asi esta bien")
  fallaba de forma intermitente según el hash seed. Se cambió a tokens ORDENADOS.
- **Verificado contra el modelo real** (`tools/scripts/repro_partb.py`): perfil 152 → oferta →
  "agregale glucosa" (suma, re-ofrece) → "qué análisis de orina tienen" (menú área) → "la 1"
  (suma Cortisol, re-ofrece) → "no, seguimos con el pago" → "contraentrega" → resumen con
  total correcto $69.000 (24+12+33). También: dar el método de pago en la propia oferta salta
  directo al resumen.
- **Tests:** `tests/test_extra_analysis_offer.py` (7 casos). Suite 142/142 (determinista x3).
- **Estado:** ✅ IMPLEMENTADO Y VERIFICADO. Pendiente: aprobación visual del usuario en vivo.

### RESUELTO-016 — Al pedir el análisis, dejó de mostrar la lista seleccionable de perfiles/análisis (2026-06-22)

- **Síntoma (reporte del usuario, 2026-06-22):** antes, cuando el bot preguntaba el análisis y
  el cliente respondía vago, por área o por síntoma ("no sé", "algo de orina", "algo para el
  dolor de panza de mi perro"), mostraba una lista de perfiles/análisis seleccionables con
  número y precio real. Dejó de hacerlo: el modelo improvisaba la lista en el texto, sin menú
  detrás (no seleccionable por número, riesgo de inventar precios).
- **Causa raíz:** asimetría en los guards. `_enforce_profile_recommendation_help` (B7) lee el
  MENSAJE del usuario, por eso "no sé" seguía funcionando. Pero `_enforce_test_category_help`
  (área) y `_enforce_diagnostic_label_help` (etiqueta) dependían de que el modelo guardara el
  término en `exam_type`. El modelo ahora suele dejar `exam_type` vacío y escribir él la lista
  → esos guards no disparaban y la lista quedaba improvisada (sin `_test_menu_options`/
  `_profile_menu_options`).
- **Solución:**
  1. Helper `_analysis_help_candidate`: usa `exam_type` si el AI lo capturó; si lo dejó vacío y
     el bot ACABA de pedir el análisis, usa el propio mensaje del usuario. Los guards de área y
     etiqueta ahora reciben `user_message` + `history` y disparan con eso.
  2. Catch-all `_enforce_analysis_help_fallback`: si la respuesta es vaga y no mapea a área ni
     etiqueta (ej. "dolor de panza" sin etiqueta directa), muestra perfiles por especie
     SELECCIONABLES (B7) en vez de dejar improvisar al modelo.
  3. Prompt (`app/prompt.py`): el modelo mapea más síntomas a etiquetas canónicas
     (panza/vómito/diarrea→PANCREÁTICO, etc.), deja `exam_type` en null si no hay etiqueta
     clara, y REGLA CRÍTICA: nunca escribe él la lista — el sistema la arma desde la BD.
- **Verificado contra el modelo real** (`tools/scripts/repro_reco.py`): "no sé" → perfiles
  caninos; "algo de orina" → 7 análisis de Uroanálisis (menú seleccionable, elegí "la 2" →
  registró 1601); "función renal" → etiqueta RENAL; "dolor de panza" → PANCREÁTICO; "hígado" →
  HEPÁTICO CANINO; "hemograma"/"perfil 152" → registran directo sin lista.
- **Tests:** `tests/test_analysis_options_restore.py` (5 casos). Suite 135/135.
- **Estado:** ✅ CORREGIDO Y VERIFICADO. Pendiente: confirmación visual del usuario en vivo.

### RESUELTO-015 — "Si la uno" (opción 1 del menú) escalaba a recepción como cliente nuevo (2026-06-22)

- **Síntoma (chat 4 real, 2026-06-22):** tras la bienvenida, el usuario eligió la opción 1 con
  "Si la uno" y el bot respondió `CLIENT_NEW_REGISTRATION_MESSAGE` (escala a recepción como
  cliente nuevo), en vez de pedir el NIT/nombre para identificarlo.
- **Causa raíz:** en el flujo de identificación (`process_turn`), `says_new_client` se activaba
  con `_confirms_new_client(user_message)` y escalaba **sin verificar si el bot había preguntado
  "¿eres cliente nuevo?"**. `_confirms_new_client` da True para cualquier afirmación pelada de
  ≤4 palabras con "sí" → "Si la uno" la disparaba. Es el patrón de L46 (clasificar por longitud
  en vez de por contexto).
- **Solución:** nuevo helper `_explicitly_says_new_client` (solo mención EXPLÍCITA de "cliente
  nuevo", no afirmación pelada). En `says_new_client`, la afirmación pelada (`_confirms_new_client`)
  solo cuenta cuando el bot ACABA de preguntarlo (`_asks_if_new_client(_last_bot_message(history))`);
  la mención explícita y `_claims_unregistered_client` cuentan siempre.
- **Tests:** `tests/test_new_client_classification.py` (4 casos). Suite 130/130.
- **Estado:** ✅ CORREGIDO TÉCNICAMENTE — pendiente re-prueba conversacional del usuario.

### RESUELTO-014 — Agregar otro análisis/perfil se trababa al preguntar por área (2026-06-22)

- **Síntoma (chat 4 real, 2026-06-22):** dos fallos al querer agregar análisis a un perfil:
  1. **Intención compuesta ignorada:** "quiero el perfil 152 al cual le quiero agregar un
     analisis extra" → el bot fijaba el perfil y saltaba directo al pago, descartando el
     "agregar un analisis extra".
  2. **Pregunta de catálogo durante el ajuste → trabazón:** ya en confirmación/personalización,
     el usuario dijo "quiero agregar otro analisis a ese perfil" (el bot pidió el nombre exacto)
     y luego "que analisis de orina tienen". El bot **repitió el resumen** sin listar ningún
     análisis de orina. El usuario quedó sin respuesta y abandonó.
- **Causa raíz:** durante el ajuste de un perfil, el código solo resolvía nombre/código EXACTO
  de un análisis (`_confirmation_analysis_adjustment`, `_enforce_profile_customization_changes`).
  Una pregunta abierta por ÁREA nunca llegaba a `db.find_tests_by_area`: los helpers que listan
  por área (`_enforce_test_category_help`, `_enforce_diagnostic_label_help`) se auto-desactivan
  cuando ya hay `selected_tests`/perfil base. Sin un test exacto que resolver, el flujo caía al
  resumen → bucle.
- **Solución:** helper `_area_options_for_profile_addition`: ante una pregunta por área durante
  el ajuste, lista las opciones de esa área marcadas para AGREGAR al perfil base
  (`_test_menu_adds_to_profile`), sin reemplazarlo. Integrado en
  `_confirmation_analysis_adjustment` (cuando no hay test exacto) y en
  `_enforce_profile_customization_changes`. La selección del menú (`process_turn`, bloque
  `_test_menu_options`) ahora suma al perfil vía `_capture_menu_addition_to_profile` cuando la
  bandera está activa, en vez de reemplazar. La lógica de sumar/quitar se factorizó en
  `_add_tests_to_order` (fuente única). Para la intención compuesta,
  `_enforce_catalog_profile_code_selection` fija el perfil y, si el mismo mensaje pide agregar,
  abre el ajuste (lista el área si la nombró, o pregunta qué agregar) en vez de saltar al pago.
- **Tests:** `tests/test_add_analysis_during_adjustment.py` (5 casos, mocks de catálogo).
  Verificado además contra la base real: `find_tests_by_area("que analisis de orina tienen",
  "Felino")` → 7 análisis de Uroanálisis. Suite completa 126/126.
- **Estado:** ✅ CORREGIDO TÉCNICAMENTE — pendiente re-prueba conversacional del usuario
  (reiniciar el Flask local: el historial del chat 4 venía de una versión anterior a los
  últimos fixes, por eso mostraba la línea "Perfil base:" ya removida en RESUELTO-012).

### RESUELTO-011 — Regresión: con perfil de catálogo + pago en línea, el bot escalaba sin mostrar el resumen (2026-06-22)

- **Síntoma:** cliente identificado, orden completa, elige un perfil por código (ej. "perfil
  152") y luego "pago en línea". El bot escalaba a Contabilidad SIN mostrar antes el resumen
  de confirmación; los datos del paciente quedaban en NULL y, al pedir el usuario "agregar
  otro análisis", el flujo multi-orden (B14) limpiaba el paciente y reiniciaba pidiendo el
  médico solicitante.
- **Causa raíz:** tres cambios encadenados introducidos en una edición previa para resolver
  "agregar análisis en la confirmación" (B11): (1) reescritura de `_order_summary_lines` con
  `analysis_line` y "Valor estimado" condicional; (2) guarda de `_wants_partial_analysis_change`
  al inicio de `_enforce_confirmation_step`; (3) Sección 7.0 `_awaiting_additional_test` en
  `process_turn`. La combinación rompió el camino del resumen para el perfil de catálogo.
- **Solución:** revertir los 3 cambios al estado del commit `9570b50` (solo esas funciones;
  Alegra y el resto se mantienen). Decisión acordada con el usuario (revert + re-implementar
  limpio después). Quedó documentado el contrato del flujo en
  `docs/contrato-flujo-conversacional.md` y la regla de no tocar el flujo sin avisar en `CLAUDE.md`.
- **Verificación:** `validate_flows.py` 20/20 OK con modelo real (incluye F: pago en línea;
  A: multi-orden) + repro dirigido perfil-por-código (401) + "pago en línea" → muestra el
  resumen en `fase_4_confirmacion`, no escala directo.
- **Pendiente derivado:** B10 fue corregido en RESUELTO-012 y B11 fue corregido en
  RESUELTO-013.
- **Estado:** RESUELTO.

### RESUELTO-012 — B10: resumen duplicaba perfil de catálogo en "Análisis" y "Perfil base" (2026-06-22)

- **Síntoma:** al llegar a `fase_4_confirmacion` con un perfil de catálogo, el resumen mostraba
  el mismo perfil dos veces: `- Análisis: X` y luego `- Perfil base: X ($Y)`. El precio quedaba
  separado de la línea principal del análisis y el usuario lo percibía como estructura partida.
- **Causa raíz:** `_order_summary_lines` agregaba siempre la línea `- Análisis: exam_type` antes
  de saber si el análisis era un perfil de catálogo; después, en la rama `_selected_profile_code`,
  agregaba otra línea `- Perfil base: profile_name (precio)` para el mismo concepto.
- **Solución:** en perfiles de catálogo, `_order_summary_lines` arma la línea principal como
  `- Análisis: Nombre del perfil — $Y COP` y deja de emitir `- Perfil base:`. Si hay agregados o
  quitados, se siguen mostrando en líneas separadas y el `Valor estimado` conserva el total.
- **Verificación:** `python -m pytest tests/test_profile_price_resolution.py` → 11/11; `python -m
  pytest` → 119/119; `python tools/scripts/validate_flows.py F M Q` → 4/4 flujos OK. El intento
  de `validate_flows.py` completo no falló por aserción, pero quedó cortado por timeout antes del
  resumen final.
- **Estado:** RESUELTO técnicamente; pendiente aprobación visual del usuario.

### RESUELTO-013 — B11: agregar análisis durante la confirmación cerraba la orden (2026-06-22)

- **Síntoma:** en `fase_4_confirmacion`, si el usuario respondía algo como `sí, pero agrégale
  glucosa`, el bot tomaba el `sí` como confirmación final y cerraba la orden antes de aplicar
  el cambio de análisis.
- **Causa raíz:** el cierre determinístico de `_enforce_confirmation_step` corría antes de
  revisar si el mismo mensaje traía un ajuste parcial del análisis (`agregar/quitar`).
  `_is_order_confirmation` veía el `sí` y marcaba `fase_6_cierre`.
- **Solución:** agregar `_confirmation_analysis_adjustment` antes del cierre determinístico.
  Si hay análisis nombrado, lo suma/quita, recalcula el resumen y mantiene
  `fase_4_confirmacion`; si el usuario solo dice `agregale otro análisis`, pregunta cuál y deja
  `_awaiting_additional_test` para el siguiente turno. El cierre normal queda intacto.
- **Verificación:** primero se reprodujo la falla con una prueba nueva (`fase_6_cierre` en vez
  de `fase_4_confirmacion`). Luego: `python -m pytest tests/test_profile_price_resolution.py`
  → 13/13; `python -m pytest` → 121/121; `python tools/scripts/validate_flows.py F M Q` → 4/4;
  `python tools/scripts/validate_flows.py A` → 1/1.
- **Estado:** RESUELTO técnicamente; pendiente aprobación visual del usuario.

### RESUELTO-010 — El bot vuelve a pedir la dirección tras confirmarla con "sisi" (caso Animal Pets) (2026-06-19)

- **Síntoma:** cliente registrado, el bot ofrece la dirección de retiro de la BD ("¿Es
  correcta?"), el usuario responde "sisi", el bot avanza al médico solicitante y, tras dar
  el médico, vuelve a preguntar "¿Cuál es la dirección de retiro?" aunque ya estaba puesta.
- **Causa raíz:** `_confirms_address("sisi")` devolvía False — "sisi" (pegado) no está en
  `_ADDRESS_CONFIRM_TOKENS` (que tiene "si"/"sí"/"sip"). El LLM sí entendió y avanzó, pero
  el guardrail determinista no bajaba `_address_confirmation_pending`. Esa bandera quedaba
  pegada en True y `_missing_route_field` reporta `pickup_address` como faltante mientras
  siga encendida, aunque el campo tenga valor. Evidencia: sesión chat 4 con
  `pickup_address` poblado pero `_address_confirmation_pending=True`. **Independiente de la
  integración de Alegra** (el hook de facturación está aislado en el cierre).
- **Solución (2 fixes, `app/agent.py`):**
  1. `_confirms_address`: reconoce confirmaciones coloquiales pegadas/alargadas con
     `re.fullmatch(r"(s[ií]+)+", w)` → "sisi", "sisisi", "siii", "sí sí".
  2. Red de seguridad anti-bandera-pegada: el bloque que baja `_address_confirmation_pending`
     cuando el flujo ya avanzó ahora evalúa los `fields` ACTUALES (no solo `prev_captured`),
     así desatasca la bandera aunque la confirmación venga en una forma no prevista.
- **Segundo camino (mismo bug, otra entrada):** cuando el cliente confirma con "el mismo"/
  "esa misma" y la sesión ya tiene `_client_memory`/`_prev_order_snapshot`, el flujo entra a
  `_resolve_same_as_previous` (process_turn ~3890), que pone `pickup_address` y hace `return`
  temprano — **saltándose** el handler que baja la bandera. La bandera quedaba pegada igual.
  Fix: en ese `return` temprano, si la resolución dejó `pickup_address` y la bandera estaba
  pendiente, bajarla (`_address_confirmation_pending=False`, `_address_confirmed=True`).
  **No es regresión de Alegra:** el `git diff` muestra `_resolve_same_as_previous` intacto
  desde el commit; el único cambio Alegra cercano (`_store_client_context` setea `tax_id`)
  no toca este flujo.
- **Verificación:** `tests/test_address_confirmation.py` (16 casos) + reproducción de la
  cadena completa (`_resolve_same_as_previous` → bandera abajo → `_missing_route_field` ya no
  pide la dirección, ni antes ni después de capturar el médico). Suite 112/112.
- **Pendiente operativo:** REINICIAR el server Flask para tomar el fix (el código no se
  recarga solo); reiniciar la conversación de prueba o seguir (se desatasca sola).

### RESUELTO-009 — Cuenta Alegra de pruebas era de Argentina, no de Colombia (2026-06-19)

- **Síntoma:** al probar `app/services/alegra.py`, el alta de contacto fallaba con `2055`
  ("condición de IVA obligatoria"), `2054` ("valor de IVA inválido") y `2039` ("tipo de
  identificación no válido"); cuando un alta "tenía éxito" el contacto quedaba con
  `identification=None` y la búsqueda por NIT no lo encontraba (duplicados, sin idempotencia).
- **Causa raíz:** `GET /company` devolvía `applicationVersion="argentina"`. La primera cuenta
  de pruebas quedó configurada como **Argentina**, no Colombia: aceptaba `ivaCondition`
  argentino y rechazaba NIT/CC y los regímenes colombianos.
- **Solución:** se usó una cuenta de pruebas de **Colombia** (`applicationVersion="colombia"`).
  El alta con el formato oficial de Colombia (`identificationObject` con NIT + `regime` +
  `kindOfPerson`) funciona: el NIT se guarda (`identification:"900123456"`) y la búsqueda por
  NIT lo encuentra (idempotencia OK, no duplica).
- **Verificación:** `python scripts/alegra_smoke.py --contact` (2 corridas → mismo id=2).
- **Lección:** validar siempre `company.applicationVersion` antes de probar flujos por país.
- **Referencias:** `app/services/alegra.py`, `scripts/alegra_smoke.py`,
  `docs/decisions/009-alegra-integracion-por-fases.md`.

### ABIERTO-005 — Confirmacion no cierra cuando falta confirmar la direccion (caso Gusmery)
- Severidad: alto
- Flujo: orden de servicio / confirmacion
- Sintoma observado: el cliente confirma una y otra vez ("Si", "Cierra la orden", "1") y el
  bot alterna resumen ↔ "¿que corregir?" sin registrar. Caso real (Chatwoot conv 10, Gusmery,
  2026-06-15): se fue con "Chao no funciona". Pista del chat: el bot pedia "responde 1) si,
  esa direccion esta bien" → la DIRECCION quedo sin confirmar y bloqueaba el cierre.
- Reproduccion: `diag_chatwoot.py H1` con DOS guiones (orden completa y direccion SIN
  confirmar explicitamente) — en ambos el agente actual CIERRA la orden con normalidad. No
  reproducible. El codigo actual auto-confirma la direccion cuando el flujo progresa
  (`agent.py` ~3093: si hay medico/paciente/especie/analisis y hay `pickup_address`, baja
  `_address_confirmation_pending`), por lo que el dato pendiente ya no bloquea el cierre.
- Causa probable del chat real: version anterior a los fixes de confirmacion del 2026-06-16
  (commit 694e518 "Robustecer agente: confirmacion..."); el chat es del 2026-06-15.
- Estado: monitoreo (no reproducible en el codigo actual; vigilar si reaparece en prod).

### ABIERTO-001 — validate_flows.py: caso "cliente caotico" no cierra (modelo real)
- Severidad: bajo
- Flujo: programar recogida (validacion con modelo real)
- Sintoma observado: el caso F de `tools/scripts/validate_flows.py` espera 1 orden creada y crea 0; ante "si, confirmo" el bot pide un dato en vez de cerrar.
- Causa raiz (probable): flujo deliberadamente caotico ejecutado contra el modelo real (no determinista); el camino feliz (caso A) si cierra y los 236 tests unitarios pasan. No reproducible en los tests con mocks.
- Estado: monitoreo (vigilar si se vuelve consistente).

### ABIERTO-003 — Refactor de comprension por IA incompleto (Etapas 2-4)
- Severidad: medio
- Flujo: interpretacion de lenguaje (transversal)
- Sintoma observado: solo las Etapas 0 (schema+prompt) y 1 (identificacion de cliente) usan `user_intent_signal` como fuente primaria. El resto del flujo todavia decide con detectores de tokens como autoridad.
- Solucion propuesta: migrar por etapas — 2 (confirmaciones/correcciones/direccion), 3 (memoria/"el mismo de siempre"/cambio de cliente), 4 (perfiles/small talk). Plan: `~/.claude/plans/glittery-marinating-newell.md`.
- Estado: en progreso.

---

## Correcciones aplicadas

### ERR-044 — Confirmar el detalle de un perfil reabría opciones de Perfil General
- Severidad: medio (respuesta confusa tras mostrar detalle de perfil)
- Flujo: catálogo / confirmación de perfil predefinido
- Síntoma observado (chat 4, 2026-06-21): tras preguntar `me dirías qué análisis contiene el perfil 151`, el bot respondió correctamente el detalle del `Perfil General` y preguntó si lo dejábamos así o se personalizaba. El usuario respondió `no asi esta bien`; el bot contestó: "Para Perfil General, estas son las combinaciones..." y listó `1339 Panel Generales de Salud` + `151 Perfil General`.
- Causa raíz: orden de guardrails. `_enforce_catalog_profile_help` corría antes de `_enforce_profile_detail_step`. Aunque `no asi esta bien` era una confirmación válida para `_is_profile_confirmation`, primero el guard de catálogo volvió a buscar `exam_type="Perfil General"`; `db.find_catalog_profiles("Perfil General")` matcheó tanto la categoría/nombre `General` como el panel `1339`, y mostró opciones. La confirmación nunca llegó limpia al handler de detalle.
- Solución aplicada: si `_profile_detail_offered` ya está activo, `_enforce_catalog_profile_help` no vuelve a buscar opciones por nombre; deja que `_enforce_profile_detail_step` procese confirmación o personalización. Esa decisión usa `user_intent_signal` como fuente primaria (`affirm`/`negate`) y deja los tokens como fallback: frases distintas como `tal cual` o `no quiero agregar nada` confirman el perfil si la intención semántica es dejarlo igual. Si el usuario vuelve a preguntar el detalle y hay `_selected_profile_code`, se responde el detalle por código.
- Tests: `test_confirming_profile_detail_does_not_reopen_catalog_options`, `test_profile_detail_confirmation_uses_intent_signal_not_exact_words`, `test_negated_customization_signal_keeps_profile_as_is` en `tests/test_profile_price_resolution.py`; suite completa `pytest` -> 118/118.
- Estado: corregido.

### ERR-043 — `perfil 151` se trataba como perfil diagnóstico GENERAL en vez de perfil cerrado
- Severidad: medio (confunde selección de catálogo y retrasa el cierre)
- Flujo: catálogo / selección de perfil
- Síntoma observado (chat 4, 2026-06-21): al pedir `perfil 151` cuando el bot preguntaba qué análisis o perfil deseaban, respondió "Para un perfil General suelo sugerir estas pruebas... ¿Cuáles quieres incluir?". El usuario tuvo que aclarar "el perfil que deseo es el 151". El estado final sí terminó con `_selected_profile_code=151`, `_selected_profile_price=32000`, pero el primer turno fue incorrecto.
- Causa raíz: el guard de perfil diagnóstico (`_enforce_diagnostic_label_help`) corría antes de resolver códigos de perfiles del catálogo desde el texto real del usuario. El modelo reinterpretó `perfil 151` como `Perfil General`; al llegar al guard diagnóstico, `find_diagnostic_label("Perfil General")` devolvió `GENERAL` y abrió el flujo de perfil personalizado, aunque el usuario había dado un código cerrado del catálogo.
- Solución aplicada: nuevo guard `_enforce_catalog_profile_code_selection` en `app/agent.py`, ejecutado antes del guard diagnóstico. Si el texto del usuario trae un código de perfil existente (`151`) y no es una pregunta de detalle, resuelve por `db.get_catalog_profiles_by_codes`, guarda código/nombre/precio con `_store_selected_profile_fields`, limpia marcas de perfil diagnóstico y avanza al siguiente dato faltante. Además, si después de elegir un perfil cerrado el usuario dice `agrégale X`/`quítale X`, el pago ya no pisa la personalización: se agrega/quita el análisis, se permite seguir ajustando y `cerramos así` cierra la personalización antes de pedir pago.
- Tests: `test_profile_code_selection_wins_over_diagnostic_label`, `test_selected_profile_can_be_customized_before_payment`, `test_customized_selected_profile_can_be_closed_then_asks_payment` en `tests/test_profile_price_resolution.py`; suite completa `pytest` -> 115/115.
- Estado: corregido.

### ERR-042 — El agente dejó de mostrar el precio de los análisis y no respondía "¿cuánto cuesta?"
- Severidad: medio (experiencia de cotización)
- Flujo: catálogo / precios / preguntas laterales
- Síntoma observado (testeo real): al mencionar un análisis ya no aparecía el precio al lado, y al preguntar "¿cuánto sale este análisis?" o "¿cuánto serían todos esos?" el agente no respondía el valor.
- Causa raíz: (1) `_operational_side_question_answer` interceptaba toda pregunta de precio con una frase genérica ("el valor depende del análisis, dime cuál") que se devolvía como respuesta y CORTABA al LLM, que sí tiene el catálogo con precios y conoce los sinónimos (hemograma = Cuadro Hemático). (2) No había una respuesta determinista para el total de los análisis ya elegidos ni para un análisis puntual; `_price_answer_for_order` solo cubría un perfil ya seleccionado. (3) La confirmación de selección de menú (`_capture_test_menu_selection`) registraba "Listo, registro X" con `_format_selected_tests`, que no incluía precio.
- Solución aplicada:
  1. `_catalog_price_answer(fields, msg)`: responde con valores REALES del catálogo — el total de los análisis ya elegidos (con subtotal/descuento por volumen/total explícitos vía `_format_tests_total`), un análisis puntual por código/nombre exacto, una selección del menú mostrado, o el perfil ya elegido. Se engancha antes de la respuesta genérica en el flujo activo y en la confirmación.
  2. Se quitó la frase genérica de deflección de precio: las preguntas que el código no resuelve con certeza pasan al LLM, que las contesta con el catálogo inyectado (incluye precios) y mapeando sinónimos.
  3. La confirmación de selección ahora usa `_format_test_items` (precio al lado de cada análisis) + "Valor estimado" si son varios. Se eliminó `_format_selected_tests` (sin uso).
  4. Prompt reforzado: precio SIEMPRE visible al nombrar/registrar un análisis; responder preguntas de precio con el catálogo y nunca inventar.
- División IA/código: el código resuelve lo seguro (total de elegidos, código/nombre exacto, menú, perfil); el LLM resuelve el vocabulario del cliente (sinónimos), porque el catálogo real usa "Cuadro Hemático Completo" / "Parcial de Orina", no "hemograma" / "uroanálisis" (el match por substring fallaba y no se quiso construir un diccionario de sinónimos).
- Archivos afectados: `app/agent.py` (`_catalog_price_answer`, `_format_tests_total`, `_named_analysis_terms`, `_capture_test_menu_selection`, `_operational_side_question_answer`), `app/prompt.py`, `tests/test_price_answers.py` (nuevo).
- Tests: `test_specific_analysis_price`, `test_total_of_selected_tests`, `test_selected_profile_price_when_no_named_analysis`, `test_non_price_question_returns_none`, `test_price_from_menu_options_selection`. Verificado además contra el catálogo real (Cuadro Hemático $14k, total de elegidos con descuento). Suite 96/96.
- Estado: corregido.

### ERR-041 — Orden con perfil del catálogo cerraba con precio $0 y no facturaba en Alegra (caso gato, orden A3-2026-062)
- Severidad: alto (afecta precio mostrado, registro y facturación electrónica)
- Flujo: catálogo / precio / persistencia / integración Alegra
- Síntoma observado (testeo real con la cuenta de pruebas Alegra): una orden de un gato con "Perfil Prequirúrgico I" cerró registrando precio $0 (el perfil real cuesta $24.000) y NO generó factura en Alegra; la única factura en la cuenta era la demo manual (canino $58k), no la del flujo conversacional.
- Causa raíz (dos bugs que se combinan):
  1. **Precio $0:** el `exam_type` quedó como "152-Perfil Prequirúrgico I" (código + nombre juntos) sin `_selected_profile_code`. El backstop `_resolve_profile_base_if_missing` resolvía por NOMBRE: `find_catalog_profile("152-Perfil Prequirúrgico I")` no matchea la cadena combinada, y por nombre suelto ("Perfil Prequirúrgico I") devolvía un perfil EQUIVOCADO ($90k, perfil X en vez del I). Quedaba sin resolver → `_profile_event_payload` persistía base price 0 y total 0. Además `billing.build_invoice_lines` descarta líneas con precio 0 → sin factura aunque hubiera NIT.
  2. **NIT no llegaba a facturación:** cuando el cliente se identifica por NOMBRE, `_store_client_context` no copiaba el `tax_id` del cliente a `fields`. `_try_invoice_in_alegra` lee `fields.get("tax_id")` → None → `billing.invoice_order` retorna None y la facturación se salta en silencio, aunque el cliente tenga NIT en la BD.
- Solución aplicada:
  1. `_resolve_profile_base_if_missing` resuelve primero por CÓDIGO (extrae el código del `exam_type` con `_profile_codes_from_text` y usa `db.get_catalog_profiles_by_codes`), que es la fuente determinística del precio; el match por nombre queda solo como fallback. Corrige las tres superficies a la vez: el resumen que ve el cliente, el evento persistido (dashboard) y la factura de Alegra.
  2. `_store_client_context` ahora copia el NIT canónico del cliente (`client.tax_id`) a `fields` para que la facturación lo tenga aunque la identificación haya sido por nombre.
- Archivos afectados: `app/agent.py` (`_resolve_profile_base_if_missing`, `_store_client_context`), `tests/test_profile_price_resolution.py` (nuevo).
- Tests: `test_combined_code_name_resolves_by_code_not_name`, `test_already_resolved_is_left_untouched`, `test_custom_profile_is_not_resolved`, `test_invoice_lines_have_price_after_resolution`. Suite completa 91/91.
- Estado: corregido (precio y facturación).
- Verificación de datos: el cliente "Animal Pets" SÍ tiene NIT en la BD (`tax_id=53115419-1`); la corrección inicial de que "no tenía NIT" era falsa (venía de cómo el join de `list_requests` traía la columna). La base está bien cargada: 492 de 500 clientes con NIT, y el catálogo tiene los precios reales. Por eso el bug #2 (NIT no llega a facturación) era la causa real, no un dato faltante. Probado en memoria (sin escribir en Alegra): con ambos fixes la orden del gato lleva NIT 53115419-1, resuelve 152 a $24.000 y arma la línea de factura.
- Relacionado con ERR-039 (misma clase: perfil base elegido por texto pierde código/precio). Deuda aparte: `find_catalog_profile` por nombre puede devolver un perfil de la misma familia con número distinto (I/II/X); por eso se resuelve por código primero.
- Recordatorio de entorno: TODO es prueba. La facturación se crea solo en BORRADOR en la cuenta de pruebas (`create_invoice` sin `status`); la emisión DIAN real no está conectada y no debe activarse en pruebas.

### ERR-040 — Elegir una opción de la lista de coincidencias con respuesta corta de confirmación se tomaba como cliente nuevo o nombre de otra veterinaria ("exacto, es la primera")
- Severidad: alto
- Flujo: identificación cliente / selección de coincidencias
- Síntoma observado (testeo real): el bot mostró varias veterinarias que coincidían y preguntó "¿cuál es?". El cliente respondió "exacto, es la primera" (= sí, la opción 1) y el bot NO lo detectó como selección: lo interpretó como el nombre de OTRA veterinaria y la re-buscó (también podía escalar a "cliente nuevo").
- Causa raíz: orden de prioridad equivocado en `process_turn`. Con la lista de coincidencias pendiente (`_client_match_options`), el mensaje se reinterpretaba ANTES de resolver la selección: (1) `_confirms_new_client("exacto, es la primera")` devolvía True por una heurística frágil de "≤4 palabras + token afirmativo" (el "exacto" la disparaba) → escalaba a cliente nuevo; y (2) `_apply_identification_fallbacks` tomaba "la primera" como un nombre nuevo (`_looks_like_bare_client_name`, también basada en longitud) y BORRABA la lista, así que el selector de ordinales (`_select_client_match`, que ya entiende "la primera" → opción 1) nunca corría. El problema no era falta de frases en un diccionario, sino que las heurísticas por longitud de mensaje ganaban a la comprensión por contexto.
- Solución aplicada: prioridad por contexto, sin depender de la cantidad de palabras. Al inicio del bloque de identificación se calcula `picks_from_match_list` = hay lista pendiente Y `_select_client_match(user_message)` resuelve una opción (número, ordinal o nombre listado). Si es una selección: `says_new_client` se fuerza a False (no escala por un "exacto" de confirmación) y se omite `_apply_identification_fallbacks` (no reinterpreta el ordinal como nombre ni borra la lista). La selección se resuelve en el bloque `_client_match_options` ya existente, con la lista intacta. La IA interpreta el significado; el código hace cumplir la selección determinísticamente.
- Archivos afectados: `app/agent.py` (`process_turn`, bloque de identificación), `tests/test_client_match_selection.py` (nuevo).
- Tests: `test_short_confirmation_with_ordinal_selects_option_one`, `test_plain_ordinal_selects_option_two`, `test_number_selection_still_works`. Verificado que fallan sin el fix (2/3) y pasan con él. Suite completa 87/87.
- Estado: corregido.
- Pendiente relacionado (no bloqueante, ver ERR-011/ABIERTO-003): las heurísticas por longitud (`_confirms_new_client`, `_looks_like_bare_client_name` con su corte de ≤4 palabras) siguen siendo frágiles fuera de este flujo; deberían gatillarse por contexto/señal del LLM, no por cantidad de palabras. Este fix las neutraliza cuando hay lista pendiente, pero conviene migrarlas a comprensión por intención en las etapas restantes.

### ERR-039 — Agregar un análisis a un perfil del catálogo perdía el precio base (total mal calculado)
- Severidad: alto
- Flujo: catálogo / personalización de perfil / confirmación / precio
- Síntoma observado (testeo real, `external_chat_id=4`, 2026-06-18): el cliente eligió el perfil 504 (Perfil Renal IV, $22k por texto, vía el LLM) y luego pidió agregarle el 1601 (Parcial de Orina, $16k). El resumen mostró "Análisis: 504-Perfil Renal IV", "Análisis incluidos: 1601 $16k" y "Valor estimado: $16,000 COP" — solo el análisis agregado, SIN el precio del perfil base. El total correcto era $22k + $16k = $38k. El cliente lo notó ("me parece que me estás dando un valor equivocado").
- Causa raíz: el perfil 504 quedó en `exam_type` como TEXTO pero `_selected_profile_code`/`_selected_profile_price` quedaron en None (lo eligió por el LLM, no por el menú determinista; y al pedir "agregar análisis" el flujo entró al menú genérico de análisis sueltos `_test_options_response`, que pone `exam_type=None`/`selected_tests=[]` y descartó la base). En `_order_summary_lines`, sin `_selected_profile_code`, cae a la rama `elif selected_tests` (perfil a medida desde cero) y solo suma los análisis agregados (`calculate_custom_profile_total`), ignorando el valor del perfil base.
- Solución aplicada: backstop `_resolve_profile_base_if_missing(fields)` llamado al inicio de `_order_summary_lines`: si `exam_type` es un perfil del catálogo (`_looks_like_catalog_profile`, excluyendo "Perfil personalizado…") y falta `_selected_profile_code`, resuelve el perfil con `db.find_catalog_profile` y fija código/nombre/precio/descripción del base. Así el resumen usa la rama de perfil base (`calculate_profile_adjusted_total`): total = precio del perfil + agregados − quitados, y muestra "Perfil base", "Agregados" y "Valor estimado" correctos. Path-independent: corrige el total sin importar cómo se llegó al estado.
- Archivos afectados: `app/agent.py` (`_resolve_profile_base_if_missing`, `_order_summary_lines`), `tools/scripts/validate_flows.py` (mock `find_catalog_profile` resuelve perfiles).
- Validación: prueba determinística reconstruyendo el estado de la sesión 4 (504 texto + 1601 agregado) → "Perfil base $22k + Agregados $16k = Valor estimado $38,000 COP" y `_selected_profile_code=504` persistido. `pytest` 77/77; `validate_flows.py` 20/20 sin regresión.
- Pendiente relacionado (no bloqueante): al agregar análisis a un perfil, el flujo debería entrar a la PERSONALIZACIÓN del perfil base (`_profile_customizing`, manteniendo `_selected_profile_code`) en vez del menú de análisis sueltos; el backstop corrige el total, pero la ruta ideal evitaría perder la base de entrada. Además, "el precio está mal" cae al prompt de corrección genérico (no recalcula/explica): mejora futura.
- Estado: corregido (total correcto en el resumen y el registro).

### ERR-038 — Recomendación de perfiles ("no sé qué pedir") improvisada por el LLM: formato amontonado, sin precio y arrastre en multiorden
- Severidad: alto
- Flujo: catálogo / selección de análisis / confirmación / multiorden
- Síntoma observado (testeo real del usuario, `external_chat_id=1`, 2026-06-18): al pedir el análisis y responder "No se", el bot listaba los perfiles TODO JUNTO en una sola línea separados por `;` (P1). Al elegir "la primera", el resumen y el registro NO mostraban el precio del perfil (P2). Al confirmar la orden preguntando a la vez el precio ("sí es correcto, pero cuánto cuesta"), el bot cerraba sin responder el precio (P3). En una segunda orden para un paciente de OTRA especie (canino), al pedir otro análisis y decir "no sé, recomiéndame", el bot no recomendaba y registraba el perfil FELINO de la orden anterior para el canino (P4).
- Causa raíz: el flujo "no sé / qué me recomiendas" lo resolvía el LLM sin guard determinista. (P1) el LLM formateaba la lista del catálogo inyectado. (P2) la selección por texto guardaba `exam_type` sin `_selected_profile_code/price`, así que `_order_summary_lines` no agregaba la línea de valor. (P3) el cierre solo anteponía `_operational_side_question_answer`, que para "precio de eso" daba respuesta genérica y además el precio no estaba guardado. (P4) al cambiar de análisis no se limpiaba el `exam_type` viejo; y "no sé... perro" disparaba el detector de corrección ("no"=corregir, "perro"=paciente), borrando el paciente en vez de recomendar.
- Solución aplicada:
  - Guard determinista `_enforce_profile_recommendation_help` + handler temprano en `process_turn`: ante recomendación/"no sé" con especie conocida, lista los perfiles de la especie (`db.list_catalog_profiles_for_species`) en formato VERTICAL con código y precio, seleccionables (`_profile_menu_options`). Corre ANTES de los detectores de corrección y de `_enforce_diagnostic_label_help`.
  - `_select_profile_from_menu` + `_capture_profile_menu_selection`: la selección guarda el perfil real con `_store_selected_profile_fields` (código, nombre, precio), por lo que el resumen muestra "Valor estimado" (P2).
  - `_price_answer_for_order`: al confirmar + preguntar precio, antepone el valor REAL del perfil elegido antes del "Quedó registrado" (P3).
  - Distinción CAMBIO TOTAL vs AJUSTE PARCIAL: `_wants_to_change_analysis` (total → limpia y reofrece) vs `_wants_partial_analysis_change` ("el mismo pero sin X / más Y" → mantiene el perfil base y activa la personalización existente `_profile_customizing`). El reofrecimiento de followup marca `_profile_detail_offered` para que el ajuste parcial funcione (P4).
  - Prompt: bullet de formato vertical de perfiles + R28 (total vs parcial; nunca registrar un perfil de especie distinta a la del paciente).
- Archivos afectados: `app/agent.py`, `app/prompt.py`, `app/services/db.py`, `tools/scripts/validate_flows.py` (mocks de perfiles), `tools/scripts/diag_perfil_recomendacion.py` (nuevo).
- Validación: `python tools/scripts/diag_perfil_recomendacion.py` (modelo real: A lista vertical con precios; B captura con precio; C precio al confirmar; D 2ª orden canina sin arrastrar el felino → OK). Caso parcial reproducido (mantiene el perfil base, no reinicia). `pytest` 77/77; `validate_flows.py` 20/20 sin regresión.
- Estado: corregido.

### ERR-037 — Cliente impaciente ("programen la recogida ya") metia bucle y no escalaba al no registrado
- Severidad: alto
- Flujo: programar recogida / preguntas operativas laterales / escalado cliente no registrado
- Sintoma observado: detectado con el simulador adversarial `tools/scripts/sim_cliente.py` (IA-cliente vs agente real). (1) Persona `apurado`: al pedirle observaciones, respondia "sin observaciones, programen la recogida ya" y el bot soltaba la frase fija "Si, recogemos muestras con motorizado asignado..." y volvia a pedir observaciones → bucle, nunca cerraba la orden. (2) Persona `no_registrado`: "necesito que me programen la recogida igual, no estamos registrados" recibia la misma frase fija en bucle en vez de escalar a recepcion. (3) Persona `preventa`: bucle de identificacion.
- Reproduccion minima: `python tools/scripts/sim_cliente.py apurado no_registrado preventa caotico`.
- Causa raiz: la rama final de `_operational_side_question_answer` (`app/agent.py`) trataba cualquier mencion de `recoger/recogida/motorizado` como pregunta operativa y devolvia la frase fija del motorizado, sin distinguir una PREGUNTA por el servicio de una ORDEN impaciente ("programen la recogida ya", "recogela hoy"). Como la respuesta lateral no avanzaba el flujo, re-preguntaba el mismo campo → bucle; y antes de la identificacion impedia llegar al escalado del no registrado.
- Solucion aplicada: dos guards. (1) `_is_service_question(text, tokens)` — la rama del motorizado de `_operational_side_question_answer` solo responde si el mensaje es una PREGUNTA real (signo `?`/`¿` o marcador interrogativo) y NO trae verbo imperativo de programar; si el cliente ordena, devuelve `None` y el flujo sigue capturando/cerrando. (2) Guard temprano en `process_turn`: si `_claims_unregistered_client(user_message)` y no hay cliente identificado, escalar a recepcion de inmediato (`_escalate_new_client_turn`) ANTES de las respuestas de preventa/servicio, aunque el mensaje mencione un nombre o pida "que me programen". Antes el escalado existia (~linea 3621) pero era inalcanzable porque `_pre_identification_service_info_response` interceptaba primero.
- Archivos afectados: `app/agent.py`, `tools/scripts/sim_cliente.py` (nuevo simulador adversarial).
- Validacion: `python tools/scripts/sim_cliente.py` bateria completa (apurado/caotico/evasivo/desordenado/no_registrado/particular → BIEN; preventa → REGULAR/BIEN segun corrida); `no_registrado` 3/3 corridas escala correctamente; `pytest` (77/77).
- Estado: corregido.

### ERR-036 — Catalogo y preguntas laterales se perdian durante la orden real
- Severidad: alto
- Flujo: catalogo / preguntas laterales / seleccion de analisis
- Sintoma observado: en Chatwoot `external_chat_id=1`, el usuario pidio `analisis de sangre`; el bot lo guardo como texto libre sin codigo ni precio, aunque no existe una prueba unica con ese nombre. Tambien pregunto `para que cantidad de animales hacen analisis?` y el bot no respondio la duda, sino que solto un fallback de analisis y siguio con paciente. Luego pregunto `que tipo de analisis hacen` y el bot volvio a `Por ultimo, que analisis...` sin mostrar opciones.
- Reproduccion minima: `python tools/scripts/diag_real_messy_flows.py` casos E/F/G.
- Causa raiz: las preguntas con palabras `analisis/hacen` se trataban como catalogo antes que como duda lateral de especies; `analisis de sangre` se aceptaba como `exam_type` cerrado aunque era generico; y cuando el guard de hematologia si preparaba opciones, `_enforce_first_missing_after_progress` las pisaba con el siguiente campo faltante.
- Solucion aplicada: responder dudas de especies/animales antes del catalogo general; mostrar opciones concretas de hematologia para `analisis de sangre`; mostrar resumen de catalogo con codigos/precios ante `que analisis hacen`; y proteger `_test_menu_options` para que los guards genericos no reemplacen la respuesta especifica.
- Archivos afectados: `app/agent.py`, `tools/scripts/diag_real_messy_flows.py`.
- Validacion: `python tools/scripts/diag_real_messy_flows.py` (7/7); `python tools/scripts/validate_flows.py` (20/20); `python tools/scripts/diag_chatwoot.py` (6/6); `pytest` (86/86).
- Estado: corregido.

### ERR-035 — Frases reales con pregunta lateral, cliente y datos mezclados se quedaban a medio camino
- Severidad: alto
- Flujo: identificacion / comprension de frase completa / post-cierre
- Sintoma observado: al convertir conversaciones imperfectas en prueba ejecutable se detectaron fallos reales: (1) pregunta lateral + cliente exacto + datos del paciente (`recogen con motorizado? soy de Animal Planet HVP...`) respondia la duda pero no identificaba el cliente; (2) `La veterinaria ... es Animal Planet, necesito analisis...` podia caer en preventa/metodologia en vez de consultar BD; (3) `analisis de sangre` en frase larga no siempre quedaba absorbido; (4) tras cerrar una orden, `hacen analisis a reptiles?` podia reactivar el resumen anterior.
- Reproduccion minima: `python tools/scripts/diag_real_messy_flows.py`.
- Causa raiz: la respuesta de preventa se ejecutaba antes del lookup aunque la frase trajera identificador; el extractor de `soy de X` solo funcionaba al final del mensaje; faltaba fallback minimo para analisis comunes cuando el LLM no los capturaba; y el post-cierre dejaba pasar preguntas generales al pipeline normal.
- Solucion aplicada: nueva bateria de conversaciones reales imperfectas; no interceptar preventa si hay identificador; extraer `soy de X y necesito...`; preservar respuesta lateral al confirmar cliente encontrado; fallback para `hemograma` / `analisis de sangre`; reofrecer opciones cuando el usuario dice `ya te dije`; y derivar preguntas generales post-cierre sin reabrir la orden.
- Archivos afectados: `app/agent.py`, `tools/scripts/diag_real_messy_flows.py`.
- Validacion: `python tools/scripts/diag_real_messy_flows.py` (4/4); `python tools/scripts/diag_chatwoot.py` (6/6); `python tools/scripts/validate_flows.py` (20/20); `pytest` (86/86); `python tools/scripts/diag_identificacion.py`.
- Estado: corregido.

### ERR-034 — Nombre de veterinaria en frase larga se detectaba pero no se mostraban opciones
- Severidad: alto
- Flujo: identificacion de cliente / recogida de datos
- Sintoma observado: en Chatwoot `external_chat_id=1`, el usuario escribio: "La veterinaria con la que trabajo es Animal Planet, ... quiero hacer un analisis...". El agente guardo datos de la orden, pero respondio de nuevo pidiendo NIT/nombre. Luego interpreto "Ya te dije el nombre de la veterinaria" como `clinic_name` y contesto "No encuentro ningun cliente registrado".
- Reproduccion minima: conversacion real con `Animal Planet` en medio de una frase larga que tambien trae analisis/especie/edad.
- Causa raiz: habia dos fallos encadenados: (1) el extractor deterministico solo leia nombres con marcador si quedaban al final del mensaje; (2) cuando el lookup si encontraba varias coincidencias (`_client_match_options`), `_enforce_first_missing_after_progress` pisaba la respuesta de opciones con la pregunta generica de NIT/nombre porque vio avance en otros campos y cliente aun faltante.
- Solucion aplicada: extraer nombres con patron `veterinaria/clinica ... es X` aunque aparezcan en medio del mensaje; no tratar frases como "ya te dije..." como identificador; y evitar que `_enforce_first_missing_after_progress` sobrescriba respuestas de lookup (`_client_match_options` / `_client_not_found`).
- Archivos afectados: `app/agent.py`, `tests/test_agent_side_questions.py`.
- Validacion: reproduccion real corregida (`Animal Planet` muestra opciones); `pytest` (86/86); `python tools/scripts/diag_identificacion.py`; `python tools/scripts/validate_flows.py` (20/20).
- Estado: corregido.

### ERR-033 — Retesteo real descubrio bucles post-cierre, multiorden y especie ambigua
- Severidad: alto
- Flujo: route_scheduling / multiorden / especie / confirmacion / perfiles
- Sintoma observado: el retesteo con conversaciones reales mostro varios fallos: (1) tras cerrar una orden, un "si" suelto o "cierra la orden" podia abrir/reconfirmar una segunda orden con datos viejos; (2) una duda operativa post-cierre (hora de ruta) sacaba el estado a escalado y luego "otra orden" reusaba mal la orden anterior; (3) "el mismo medico y el mismo propietario" solo reutilizaba un campo; (4) especie ambigua repetia literalmente la misma pregunta; (5) cliente particular se trataba como cliente nuevo; (6) correccion con valor en el mismo mensaje podia perder el valor; (7) perfil por etiqueta diagnostica podia caer en fallback repetido al agregar/quitar/cerrar.
- Reproduccion minima: `python tools/scripts/diag_comprension.py`; `python tools/scripts/diag_multiorden.py`; `python tools/scripts/diag_chatwoot.py H1 H3 H7`; `python tools/scripts/validate_flows.py`.
- Causa raiz: detectores deterministas demasiado amplios (`si`/`orden` como otra orden), algunos turnos post-cierre seguian el pipeline del LLM en vez de responder como estado cerrado, y faltaban backstops para datos compuestos (`mismo medico y propietario`), especie ambigua, correccion con valor y personalizacion por etiqueta diagnostica.
- Solucion aplicada: endurecer deteccion de otra orden; responder dudas operativas post-cierre conservando fase terminal; cambiar el prompt de cierre para pedir "otra orden" explicitamente; resolver varios campos "el mismo" en un solo turno; normalizar especies comunes y especies adicionales; aclarar especie ambigua sin repetir literal; bloquear particulares antes de tratarlos como cliente nuevo; extraer el valor de correccion del paciente; agregar backstop deterministico para agregar/quitar/cerrar perfiles por etiqueta diagnostica.
- Archivos afectados: `app/agent.py`.
- Validacion: `python tools/scripts/check_supabase_state.py`; `python tools/scripts/diag_identificacion.py`; `python tools/scripts/diag_comprension.py`; `python tools/scripts/diag_multiorden.py`; `python tools/scripts/diag_chatwoot.py`; `python tools/scripts/validate_flows.py` (20/20); `pytest` (85/85).
- Estado: corregido.

### ERR-032 — Nombre de clinica con "mia es" no matcheaba clientes existentes
- Severidad: alto
- Flujo: identificacion de cliente
- Sintoma observado: en `external_chat_id=1`, el usuario escribio "Nombre de la clinica mia es Animal Pet". La BD si tenia `Animal Pets`, y `find_client_matches('Animal Pet')` devolvia opciones, pero el agente guardo `clinic_name="Mia Es Animal Pet"` y respondio "No encuentro ningun cliente registrado".
- Reproduccion minima: `diag_identificacion.py "Nombre de la clínica mía es Animal Pet"`.
- Causa raiz: `_extract_clinic_name_candidate` tomaba todo lo posterior a "clinica" como nombre, incluyendo el puente posesivo "mia es".
- Solucion aplicada: limpiar prefijos `mia/mio/mi/nuestra/nuestro + es/se llama` y `es/se llama` antes del lookup, sin tocar memoria ni perfiles.
- Archivos afectados: `app/agent.py`, `tests/test_agent_side_questions.py`.
- Tests: `pytest tests/test_agent_side_questions.py`; `pytest`; `diag_identificacion.py "Nombre de la clínica mía es Animal Pet"`.
- Estado: corregido.

### ERR-031 — Memoria de multiorden ignoraba "otra veterinaria/otros clientes"
- Severidad: alto
- Flujo: confirmacion / multiorden / memoria de cliente
- Sintoma observado: en `external_chat_id=1` (2026-06-18), el usuario confirmo una orden pero agrego que era para otra veterinaria; el bot cerro igual. Luego pidio otros analisis para otros clientes y el bot heredo la veterinaria/medico anterior y pregunto por paciente.
- Reproduccion minima: en `fase_4_confirmacion`, mensaje con confirmacion + "otra veterinaria"; tras una orden registrada, mensaje "otros analisis para otros clientes".
- Causa raiz: el cierre deterministico de confirmacion corria antes de detectar cambio de cliente. Ademas `_wants_to_change_client` y `_explicitly_wants_another_order` no cubrian plurales (`clientes`, `otros`).
- Solucion aplicada: detectar cambio de cliente antes de cerrar confirmacion y antes de iniciar orden de seguimiento; agregar plurales al detector; si aparece otro cliente/veterinaria, limpiar cliente actual y pedir NIT/nombre del nuevo registrado.
- Archivos afectados: `app/agent.py`, `tests/test_agent_side_questions.py`.
- Tests: `pytest tests/test_agent_side_questions.py`; `pytest`; `validate_flows.py A B`; `diag_chatwoot.py H3`.
- Estado: corregido.

### ERR-030 — "No estoy registrado" se buscaba como nombre de clinica
- Severidad: alto
- Flujo: identificacion / cliente nuevo
- Sintoma observado: en la prueba real `external_chat_id=4` (2026-06-18), tras preguntas laterales de tiempos/perfil, el bot pidio NIT o nombre de veterinaria. El usuario respondio "No estoy registrado" y el agente guardo `clinic_name="No Estoy Registrado"`, hizo lookup y contesto "No encuentro ningun cliente registrado con ese dato".
- Reproduccion minima: sesion sin `client_id`, ultimo bot pidiendo NIT/nombre, IA devuelve `user_intent_signal=new_or_unregistered_client` pero tambien trae `clinic_name="No Estoy Registrado"`.
- Causa raiz: `_looks_like_bare_client_name()` aceptaba casi cualquier frase corta cuando el bot esperaba identificador. Ademas `says_new_client` solo escalaba de forma deterministica si ya veniamos de un no-encontrado previo, no cuando el usuario declaraba de entrada que no estaba registrado.
- Solucion aplicada: si el turno indica cliente nuevo/no registrado y no trae un identificador real, se limpian `clinic_name`/`tax_id`, se evita el lookup y se escala directamente a atencion al cliente con mensaje especifico. Tambien se bloqueo la extraccion de nombre para frases de no registro.
- Archivos afectados: `app/agent.py`, `tests/test_agent_side_questions.py`.
- Tests: `pytest tests/test_agent_side_questions.py`; `pytest`; `python -m py_compile app/agent.py tests/test_agent_side_questions.py`.
- Estado: corregido.

### ERR-029 — Preguntas operativas laterales se perdian por guardrails rigidos
- Severidad: alto
- Flujo: preventa / preguntas laterales / resultados / pago
- Sintoma observado: en la conversacion real `external_chat_id=4` (2026-06-17), el cliente pregunto tres veces cuanto demoraban aproximadamente los resultados. El bot no respondio esa pregunta: primero pidio NIT y luego uso el mensaje fijo de consulta de resultados no disponible. En una transcripcion previa, al decir "Online quiero pagar... a que hora llegaria el repartidor?", el bot capturo el pago y salto al resumen sin contestar la hora.
- Causa raiz: el pipeline tenia guardrails que reemplazaban la respuesta del modelo: `results` se trataba siempre como consulta de resultado existente, y el resumen deterministico de confirmacion pisaba dudas laterales mezcladas con datos validos. Ademas `_payment_method_from_text` no reconocia "quiero pagar online" porque buscaba `pago`, no `pagar`.
- Solucion aplicada: capa transversal minima `_operational_side_question_answer` para dudas operativas de A3 (tiempos de resultados/ruta y valores) que responde sin inventar y luego retoma solo si ya hay contexto de ruta; `results` ya no absorbe preguntas de tiempos; la confirmacion preserva la respuesta lateral antes del resumen; pago en linea reconoce `pagar online`.
- Archivos afectados: `app/agent.py`, `app/prompt.py`, `tests/test_agent_side_questions.py`.
- Tests: `pytest tests/test_agent_side_questions.py`; `pytest`; `python -m py_compile app/agent.py app/prompt.py tests/test_agent_side_questions.py`.
- Estado: corregido.

### ERR-028 — Preguntas laterales respondian bien pero no retomaban el flujo
- Severidad: alto
- Flujo: route_scheduling / preguntas laterales / preventa
- Sintoma observado: en la conversacion real `external_chat_id=4` (2026-06-17), el bot respondio bien preguntas random/preventa, pero cuando el usuario dijo "estoy registrado te paso mis datos para programar la recogida de meustras" volvio a responder informacion general de recogida en vez de retomar el flujo y pedir NIT/nombre. Parecia congelado porque no avanzaba hacia la orden.
- Reproduccion minima: conversacion con preguntas de metodologia/recogida/post-mortem y luego el mensaje real de programacion; antes del fix, el ultimo turno caia otra vez en `_pre_identification_service_info_response`.
- Causa raiz: el detector de preventa interceptaba cualquier mensaje con `recogida`/`retirar` antes del gate de identificacion. Solo dejaba pasar `quiero/necesito + programar/agendar/coordinar`; el mensaje real tenia `programar + recogida` pero no `quiero/necesito`, asi que quedaba tratado como duda lateral. Ademas, las respuestas `side_question` no tenian un backstop transversal que anexara el siguiente dato pendiente del flujo.
- Solucion aplicada: (1) no tratar como preventa mensajes con `programar/agendar/coordinar + ruta/recogida/retiro/muestra(s)`; (2) marcar preventa como `side_question`; (3) agregar `_resume_route_after_lateral_turn`, que conserva la respuesta natural y remata con el campo pendiente (`client`, medico, paciente, etc.) en cualquier punto de `route_scheduling`.
- Archivos afectados: `app/agent.py`, `tests/test_agent_side_questions.py`, `tools/scripts/validate_flows.py`.
- Tests: `pytest tests/test_agent_side_questions.py`; `python -m py_compile app/agent.py tools/scripts/validate_flows.py tests/test_agent_side_questions.py`.
- Estado: corregido.

### ERR-027 — Preguntas de preventa se trataban como orden y sonaban robóticas
- Severidad: alto
- Flujo: preventa / identificacion / robustez conversacional
- Sintoma observado: en el ultimo test local (Chatwoot chat 4, 2026-06-17), el usuario hizo
  preguntas normales antes de decidir si trabajar con A3: si hacen analisis para mascotas,
  como es la metodologia, si retiran muestras y un caso post-mortem. El bot respondia raro:
  saltaba a pedir NIT, derivaba una pregunta de recogida a humano, y luego capturo
  "para ver los motivos de su muerte" como `clinic_name`, busco ese "cliente" y respondio
  "No encuentro ningun cliente registrado".
- Reproduccion minima: `python tools/scripts/validate_flows.py T` con el guion exacto de
  preventa/metodologia; antes del fix creaba una solicitud de handoff y/o podia capturar la
  explicacion clinica como cliente.
- Causa raiz: el gate deterministico de identificacion pisaba respuestas `side_question` del
  LLM con la pregunta de NIT, y `_apply_identification_fallbacks` extraia nombres de cliente a
  ciegas cuando el bot esperaba identificador. Ademas, preguntas claras de servicio (retiran
  muestras, metodologia, cobertura, post-mortem) podian caer como `unknown` y disparar handoff.
- Solucion aplicada: (1) `_enforce_client_identification_gate` deja pasar `message_mode=side_question`
  sin forzar NIT; (2) `_apply_identification_fallbacks` usa `user_intent_signal` como fuente primaria
  y solo acepta nombres libres si parecen nombre corto de cliente; (3) red deterministica minima
  `_pre_identification_service_info_response` responde preventa comun antes de identificar; (4) se
  agregaron tokens clinicos/post-mortem a `_NON_IDENTIFIER_TOKENS` para no buscarlos como cliente.
- Archivos afectados: `app/agent.py`, `app/prompt.py`, `tools/scripts/validate_flows.py`.
- Verificacion: `python -m py_compile app/agent.py app/prompt.py tools/scripts/validate_flows.py`;
  `python tools/scripts/validate_flows.py T`; `python tools/scripts/validate_flows.py B T`;
  `python tools/scripts/validate_flows.py A B K T`.
- Estado: corregido.

### ERR-026 — Un escalado (cliente nuevo) marcaba `_order_registered` y disparaba "otra orden"
- Severidad: alto
- Flujo: cliente nuevo / escalado / multi-orden
- Sintoma observado: cliente nuevo que mezcla intenciones (caso real Chatwoot conv 5, Sérgio).
  Reproducido extendiendo el guion con `diag_chatwoot.py H6`: "soy cliente nuevo" → escala OK;
  luego "programar ruta" → identificacion falla; al confirmar "sí, soy nuevo" el bot respondia
  "Perfecto, creamos otra orden de servicio para otro paciente. ¿Cuál es el médico solicitante?"
  en vez de escalar a recepcion (viola regla de negocio #3).
- Causa raiz: `_finalize_request` marcaba `_order_registered=True` para CUALQUIER request creado,
  incluidos los escalados (cliente nuevo, pagos, opción 4), que NO son ordenes de recogida. Con
  ese flag activo, el bloque de "otra orden" (`process_turn`) se disparaba porque
  `_explicitly_wants_another_order("sí, soy nuevo")` da true (la palabra "nuevo" está en su set)
  → `_begin_followup_order` en vez de escalar.
- Solucion aplicada: `_order_registered=True` solo se marca cuando `intent == "route_scheduling"`
  (una orden de recogida real). Los escalados ya no lo marcan, así que un "sí, soy nuevo"
  posterior cae al camino de confirmacion de cliente nuevo (`_confirms_new_client`) y escala.
- Archivos afectados: `app/agent.py` (`_finalize_request`).
- Verificacion: `diag_chatwoot.py H6` (escala a fase_7, sin arrancar orden); suite 77/77;
  `validate_flows.py A B` (multi-orden y cliente nuevo) sin regresion.
- Nota: en el mismo análisis, **H7** (orden de campos: raza tras observaciones) ya NO se
  reproduce — el agente actual pide los campos en orden; y las "respuestas vacías" del chat 5
  ("Perfecto.") tampoco aparecen.
- Estado: corregido.

### ERR-025 — Estado de orden arrastrado tras el cierre (chats reales Chatwoot)
- Severidad: alto
- Flujo: post-cierre / clasificacion de intencion
- Sintoma observado: tras cerrar una orden, ante una consulta general el bot respondia con
  una pregunta de campo de orden. Caso real (Chatwoot conv 4, Chuuck, 2026-06-16): "¿hacen
  analisis a reptiles?" → "¿Cuál es el médico solicitante?". Reproducido IDENTICO contra el
  modelo real con `tools/scripts/diag_chatwoot.py H4`.
- Causa raiz: al salir de la fase terminal, el reset de orden dejaba `fase_1`/`unknown` y el
  modelo reclasificaba la consulta como `route_scheduling`; con el cliente aun identificado,
  `_missing_route_field` devolvia el primer campo (medico) y el enforcement lo pedia. Una
  consulta fuera de los 4 servicios se trataba como inicio de orden.
- Solucion aplicada: en `process_turn`, al limpiar la orden por venir de fase terminal se
  marca `just_closed_order`. Tras conocer la senal del modelo, si es `off_topic`/`unclear` y
  el usuario NO pidio explicitamente otra orden (`_explicitly_wants_another_order`), se deriva
  de una a una persona con `_unknown_handoff_response` (mismo handoff que el bot ya usaba bien
  en el 2º intento del chat real), en vez de reabrir el flujo de orden. Principio: la IA
  interpreta la intencion (senal), el codigo hace cumplir la regla de derivar.
- Archivos afectados: `app/agent.py`.
- Verificacion: `tools/scripts/diag_chatwoot.py H4` (deriva, no pide medico); suite 77/77;
  `validate_flows.py A` sin regresion (multi-orden "el de siempre" intacto: la nueva orden da
  senal `another_order`/datos, no `off_topic`, asi que no se intercepta).
- Estado: corregido.

### ERR-024 — El agente no entendía sinónimos, datos adelantados ni "el mismo X"
- Severidad: alto (afecta la comprensión del cliente en todas las fases)
- Flujo: recolección de datos / interpretación de lenguaje (transversal)
- Sintoma observado: el agente "no entendía" al cliente cuando usaba SINÓNIMOS ("perra" = hembra canino), ADELANTABA datos, daba VARIOS juntos, o decía "el mismo X" con frases naturales. Casos reales (chat 4): "el mismo que el anterior, solo cambiaba el paciente" (al pedir el propietario) → lo aplicaba al PACIENTE; "soy el Dr. Gastón Alcojor" dentro de una frase larga → no capturaba el médico.
- Causa raiz: short-circuits y detectores de TOKENS cortaban ANTES del LLM o reinterpretaban lo que el LLM ya entendía. `_resolve_same_as_previous` usaba el campo MENCIONADO (tokens) en vez del PREGUNTADO; el bloque "el de siempre" cortaba frases largas que traían el dato; faltaban reglas de captura semántica.
- Solucion aplicada (alcance: 3 focos; principio acordado: **el LLM interpreta QUÉ dijo el cliente; el código solo hace cumplir reglas de negocio**):
  - Etapa 1: `_resolve_same_as_previous` resuelve el campo PREGUNTADO desde el snapshot cuando el mensaje trae señal de cambio sobre OTRO campo ("el mismo, solo cambia el paciente" → propietario, no paciente). `_CHANGE_TOKENS` distingue "lo que cambia" de "el mismo". El bloque "el de siempre" solo corta en frases CORTAS (≤6 tokens); las largas que traen el dato siguen al LLM.
  - Etapa 2: prompt R26 (captura semántica: sinónimos e implícitos "perra"→Canino+Hembra; datos en frases largas/anuncios) + R27 ("el mismo X, cambia Y"). Fallback determinista `_recover_doctor_from_text` para el médico cuando el LLM se distrae con ruido. `_recover_enumerated_answer`/`_merge_existing_route_fields` solo rellenan huecos (no pisan al LLM).
- Archivos afectados: `app/agent.py`, `app/prompt.py`.
- Verificacion: `tools/scripts/diag_comprension.py` (4/4 casos con modelo real: "perra"→Canino+Hembra; varios datos juntos; médico en frase larga; "el mismo, solo cambia el paciente"→propietario). Suite 77/77, `validate_flows.py` 19/19, `diag_multiorden.py` sin regresión.
- Limitacion: el LLM no es 100% determinista; un caso aislado puede fallar en una corrida y pasar en otra (ej. especie capturada literal). Los fallbacks determinísticos cubren los más comunes. Etapa 3 (unificar `user_intent_signal` en TODOS los detectores de intención) queda como deuda estructural.
- Estado: corregido (focos principales del "no entiende").

### ERR-023 — El flujo MULTI-ORDEN fallaba en la segunda orden y siguientes
- Severidad: alto (la primera orden funcionaba; la segunda en adelante se rompía)
- Flujo: orden de seguimiento (varias órdenes en la misma conversación)
- Sintoma observado (casos reales en BD, chats 1=Luciano y 4=Chuck):
  - **Chuck:** tras cerrar la orden 1, un turno intermedio ("a qué hora pasan?"/"Okok") sacaba la sesión de la fase terminal; al pedir "otra orden" el reset NO se disparaba → arrastraba el paciente anterior ("Lolo"), confundía "el mismo propietario" con el paciente, no capturaba el paciente nuevo ("Leija") y terminaba en bucle de corrección.
  - **Luciano:** la orden de seguimiento se escalaba/registraba VACÍA porque el pago en línea heredado disparaba el handoff a contabilidad antes de pedir paciente/análisis.
- Causa raiz (cinco piezas):
  1. El reinicio de orden solo ocurría dentro de `if phase_current in TERMINAL_PHASES`; un turno intermedio lo rompía.
  2. `_apply_handoff_guardrails` escalaba a `fase_7_escalado` por `pago_linea` heredado SIN verificar completitud, y corría DESPUÉS de `_prevent_incomplete_route_closure`.
  3. El análisis no se reofrecía en la orden de seguimiento.
  4. `_is_same_as_previous` exigía ≤6 tokens → frases largas ("es el mismo propietario que el otro perro") caían al modelo; y `_SAME_AS_FIELD_KEYWORDS` tenía "perro/gato" en `patient_name`, así que "propietario … perro" resolvía al paciente.
  5. `_CORRECTION_FIELD_KEYWORDS` no reconocía "la perra/se llama" como paciente → bucle "¿qué corregir?".
- Solucion aplicada:
  1. **Reset robusto:** `_order_registered` se marca al registrar (`_finalize_request`) y un bloque nuevo en `process_turn` detecta "otra orden" en cualquier turno posterior (no solo fase terminal) con `_explicitly_wants_another_order`; centralizado en `_begin_followup_order`.
  2. **Cierre seguro:** `_prevent_incomplete_route_closure` se movió a JUSTO antes de `_finalize_request` (tras handoff y confirmación) → ninguna orden incompleta se finaliza/escala.
  3. **Reofrecer análisis:** `_begin_followup_order` guarda el análisis en el snapshot y `_start_followup_service_order_response` lo reofrece en bloque ("¿confirmas o cambias … o análisis?"); decisión del usuario: paciente siempre de cero, análisis reofrecido.
  4. **"El mismo X" robusto:** `_is_same_as_previous` resuelve frases largas si hay campo explícito; `_SAME_AS_FIELD_KEYWORDS` prioriza `owner_name` y quita "perro/gato" de `patient_name`.
  5. **Corrección del paciente:** `_CORRECTION_FIELD_KEYWORDS` mapea "perro/perra/gato/gata/animal/mascota" → `patient_name`.
- Archivos afectados: `app/agent.py`.
- Verificacion: `tools/scripts/diag_multiorden.py` (Chuck reproducido contra BD+modelo real: reset disparó tras turno intermedio, no arrastró Lolo, capturó Leija, resolvió "el mismo médico/propietario"); Luciano (no cierra vacío, pide paciente); Fix 4/5 determinista; suite 77/77; `validate_flows.py` 19/19.
- Estado: corregido.

### ERR-022 — La búsqueda de cliente por nombre no toleraba errores de tipeo
- Severidad: alto (afecta el nucleo del agente: identificacion del cliente)
- Flujo: identificacion de cliente por nombre
- Sintoma observado: si el cliente escribia el nombre con un error de tipeo (ej. "Animal Planett" en vez de "Animal Planet"), el agente respondia que no encontraba un cliente registrado, aunque la clinica SI existe ("Animal Planet HVP"). El acceso a la BD y el mecanismo de opciones funcionaban bien; el problema era el matching estricto del nombre.
- Diagnostico: bateria `tools/scripts/diag_identificacion.py` contra la BD real (proyecto lztclcorljccioufyimq, 800 clientes / 654 activos) + modelo real. 7 de 8 variantes pasaban (nombre exacto/parcial/en frase, NIT con y sin digito, multi-sede, generico); la unica que fallaba era el nombre con typo.
- Causa raiz: `_name_match_score` exigia que TODAS las palabras de la busqueda estuvieran contenidas EXACTAS (o por prefijo) en el nombre del cliente; con un solo typo el score era 0 y el cliente no aparecia. El `difflib` ya importado solo se usaba para ORDENAR (despues del filtro), nunca para rescatar un typo.
- Solucion aplicada: en `_name_match_score`, una palabra se considera cubierta tambien si es MUY similar a una del nombre (`difflib.SequenceMatcher` ratio >= 0.85, en palabras de 4+ letras). Asi "planett"~"planet" y "bioanimall"~"bioanimal" matchean y se muestran las opciones. Umbral alto + minimo de 4 letras evitan falsos positivos (un nombre muy distinto como "Anpetal" sigue sin matchear).
- Archivos afectados: `app/services/db.py` (`_name_match_score`).
- Verificacion: bateria de identificacion (el typo paso de "no encontrado" a "opciones"; el resto sin cambios) + `tests/test_db_identification.py` 10/10 + suite 77/77.
- Estado: corregido.

### ERR-021 — El cliente daba un dato fuera de orden y el bot lo perdía / repreguntaba
- Severidad: medio
- Flujo: programar recogida / recoleccion de datos del paciente
- Sintoma observado: cuando el bot pedia un campo (ej. la especie) y el cliente respondia con un dato de OTRO campo (ej. "es hembra" = sexo, o "es un Doberman" = raza), el bot no reconocia el dato y repreguntaba con la plantilla generica; el reconocimiento se perdia. Exhibido con el modelo real (flujos F y S de `validate_flows.py`).
- Causa raiz: (1) faltaba una regla que instruyera al modelo a capturar datos dados fuera de orden; (2) cuando el modelo SI capturaba el dato y repreguntaba el campo pendiente, `_avoid_repeated_question` (racimo anti-repeticion) detectaba la repeticion y reescribia el reply con su plantilla enlatada, PISANDO el reconocimiento — aunque en ese turno hubo progreso (campo nuevo capturado).
- Solucion aplicada: (1) R25 en `prompt.py` — capturar cualquier dato valido que el cliente adelante en su campo correcto, reconocerlo y repreguntar el pedido, sin repetir luego (R3); (2) `_avoid_repeated_question` recibe `prev_fields` y NO reescribe si en el turno se capturo un dato de ruta nuevo (hubo progreso => no es bucle). Resultado: el dato se captura, se reconoce ("Perfecto, anoto hembra como sexo. Y decime, ¿la especie?") y no se vuelve a pedir.
- Archivos afectados: `app/prompt.py` (R25), `app/agent.py` (`_avoid_repeated_question`).
- Tests: flujo S de `validate_flows.py` (sexo dado al pedir especie: se captura, se reconoce, cierra coherente). 19/19 flujos OK con modelo real.
- Estado: corregido.

### ERR-020 — El anti-bucle dependía solo de la señal de la IA (cierra ABIERTO-002)
- Severidad: bajo (robustez)
- Flujo: robustez transversal / anti-bucle
- Sintoma observado: el corte por estancamiento (`_offtrack_count`) solo avanzaba si la IA marcaba `user_intent_signal in (unclear, off_topic)`. Si el modelo no marcaba bien esa senal, un bucle podia no cortarse nunca.
- Solucion aplicada: segunda senal DETERMINISTA `_repeats_last_bot_question` — si el modelo vuelve a hacer la MISMA pregunta que el bot acaba de hacer (comparando `_question_keys` contra el ultimo mensaje del bot), tambien incrementa `_offtrack_count`. Excluye la seleccion de analisis (repetir "¿agregas otro?" es normal, L12). Asi el corte al 3er turno ya no depende solo de la IA.
- Archivos afectados: `app/agent.py`.
- Tests: validacion con modelo real (18/18 flujos en `validate_flows.py`, sin regresion).
- Estado: corregido.

### ERR-019 — Pedir dos categorías de análisis en un mensaje perdía la segunda
- Severidad: bajo
- Flujo: programar recogida / seleccion de analisis (racimo de perfil)
- Sintoma observado: ante "quiero un perfil renal y tambien un analisis de orina", el bot atendia solo la primera categoria (renal) e ignoraba la segunda (orina). Exhibido con el modelo real (flujo R de `validate_flows.py`).
- Causa raiz: los guardrails de categoria (diagnostic_label / catalog_profile / test_category) se inhiben mutuamente con el guard `if selected_tests is not None or _diagnostic_label: return`. El primero que captura gana y silencia a los demas; el segundo pedido se perdia.
- Solucion aplicada (acotada): en `_enforce_diagnostic_label_help`, tras armar la sugerencia de la etiqueta, detectar si el MISMO mensaje tambien pide un area distinta (`db.find_tests_by_area`) y anexar una linea que lo reconozca ("Tambien mencionaste X; apenas cerremos este perfil, recuerdamelo y lo vemos"). El cliente ya no pierde su segundo pedido de cara a la conversacion.
- Limitacion conocida: cubre la combinacion etiqueta+area observada; no auto-dispara el segundo flujo (el cliente lo retoma) ni cubre todas las combinaciones. El arreglo completo es el refactor del racimo de analisis (deuda de mantenibilidad, no bug de runtime).
- Archivos afectados: `app/agent.py`.
- Tests: flujo R de `validate_flows.py` (reconoce la segunda categoria).
- Estado: corregido (parche acotado).

### ERR-018 — Corregir un dato en la confirmación dejaba la orden sin registrar
- Severidad: critico
- Flujo: orden de servicio / confirmacion editable
- Sintoma observado: en `fase_4_confirmacion`, tras mostrar el resumen, el cliente decia "corrige el paciente: ahora se llama Rocky" (o cualquier correccion). El bot limpiaba el dato y repreguntaba, pero al decir luego "si, confirmo" NO registraba la orden: volvia a mostrar el resumen y pedia confirmar otra vez. Cada "si" tras una correccion re-mostraba el resumen; nunca cerraba. Detectado con el modelo REAL en `validate_flows.py` (flujo M), no reproducible con los tests mockeados (que se eliminaron por eso, ver L29).
- Causa raiz: el handler de correccion arma la respuesta con `_base_route_response`, que fija `phase="fase_2_recogida_datos"`. Eso saca la conversacion de `CONFIRMATION_PHASE`. El cierre deterministico de `_enforce_confirmation_step` exige `previous_phase == CONFIRMATION_PHASE`; como la correccion habia cambiado la fase, el "si" caia al camino de "orden completa por primera vez" y re-mostraba el resumen en lugar de cerrar. Solapamiento entre el handler de correccion y `_enforce_confirmation_step`. Pariente de ERR-015 (la ENTRADA al resumen) y ERR-008 (el CIERRE): faltaba conservar la fase durante la EDICION.
- Solucion aplicada: tras armar la respuesta de correccion, mantener `ai_response["phase"] = CONFIRMATION_PHASE` (una linea). Mientras se edita el resumen seguimos en confirmacion, y el "si" posterior cierra por el camino deterministico que ya existia. Si la correccion dejo un campo vacio, `_missing_route_field` impide cerrar con datos incompletos.
- Archivos afectados: `app/agent.py`.
- Tests: validacion con modelo real `tools/scripts/validate_flows.py` flujo M (correccion editable cierra con el dato corregido). Los tests con LLM mockeado se descartaron (no detectaban este bug).
- Estado: corregido. Actualizacion: la limitacion (corregir SIN dar el valor y darlo en otro turno) tambien quedo resuelta — un flag `_correction_pending` (seteado por el handler de correccion) hace que, al llegar el dato nuevo y completarse la orden, `_enforce_confirmation_step` re-muestre el resumen antes del "si"; el flag se limpia al re-mostrar o al cerrar. Verificado con el flujo M2 de `validate_flows.py`.

### ERR-017 — "El primero" de la lista de análisis no se capturaba (caso Animal Planet)
- Severidad: critico
- Flujo: programar recogida / seleccion de analisis
- Sintoma observado: el bot mostraba una lista de analisis (ej. orina), el cliente decia "el primero" / "el 2" / el nombre, y el bot entraba en BUCLE ("Para avanzar, puedes decirme...") y terminaba guardando el texto generico "Orina" (exam_type="Orina", selected_tests=[]), dejando una orden inservible.
- Causa raiz: `_enforce_test_category_help` mostraba la lista pero NO guardaba que analisis habia mostrado, asi que la seleccion quedaba a criterio del modelo, que fallaba. Faltaba el camino determinista de seleccion (existia para sedes de cliente, no para analisis). Ademas la lista no estaba numerada.
- Solucion aplicada: la lista ahora es NUMERADA y se guardan las opciones en `_test_menu_options`; un handler determinista (`_select_tests_from_menu` + `_capture_test_menu_selection`) resuelve la seleccion por numero, ordinal ("el primero"), codigo (1601) o nombre, guarda el analisis REAL del catalogo con su codigo en `selected_tests`/`exam_type` y avanza al siguiente dato o al resumen. Mismo patron que `_select_client_match` para sedes.
- Archivos afectados: `app/agent.py`, `tests/test_agent_flows.py`.
- Tests: `test_select_tests_from_menu_resolves_number_ordinal_code_name`, `test_test_menu_selection_captures_real_analysis_and_advances`.
- Estado: corregido. Pendiente relacionado: el modelo a veces alucina una lista de catalogo distinta a la real (ABIERTO) y los 7 guardrails de analisis siguen solapandose (deuda de simplificacion).

### ERR-016 — El cierre por Chatwoot fallaba: check constraint de entry_channel (BUG REAL)
- Severidad: critico
- Flujo: programar recogida / cierre / canal Chatwoot
- Sintoma observado: por Chatwoot, la conversacion funcionaba completa pero al decir "si" en el cierre el bot NO respondia NADA. Por Telegram directo si cerraba.
- Causa raiz: `db.create_request` insertaba `entry_channel="chatwoot"`, pero la columna `requests.entry_channel` tiene un CHECK constraint (`requests_entry_channel_check`) que solo admite "telegram". El insert lanzaba `APIError 23514`, la excepcion subia por `process_turn` y el webhook no enviaba respuesta. Solo el cierre escribe en `requests`, por eso fallaba unicamente el ultimo turno. Verificado contra la BD real (las 34 ordenes historicas son todas "telegram").
- Por que los tests no lo detectaron: la suite mockea `db.create_request`; nunca se ejercitaba el insert real. LECCION: el cierre necesita una prueba de integracion contra la BD real (ver L29).
- Solucion aplicada: la columna usa un valor admitido por el constraint (`_ALLOWED_ENTRY_CHANNELS`, hoy "telegram") y el canal real del agente se conserva en `request_events.event_payload.source`. Cierre por Chatwoot reproducido OK contra la BD real (crea la orden, source="chatwoot").
- Solucion correcta a futuro: migrar el constraint (`db/migrations` + `apply_supabase_migration.py`) para admitir "chatwoot" y agregarlo a `_ALLOWED_ENTRY_CHANNELS`.
- Archivos afectados: `app/services/db.py`, `tests/test_db_identification.py`.
- Estado: corregido (workaround en codigo; migracion de esquema pendiente como mejora).

### ERR-015 — La ENTRADA a la confirmacion dependia del modelo (caso Guzman)
- Severidad: alto
- Flujo: orden de servicio / confirmacion
- Sintoma observado: al completarse la orden (tras elegir el perfil), el bot improvisaba "¿Confirmas?" SIN mostrar el resumen deterministico, y ante respuestas confusas del usuario daba vueltas con mensajes raros ("necesito ese dato" con todo ya capturado). Parecia trabado.
- Causa raiz: en `_enforce_confirmation_step`, el resumen deterministico solo se mostraba si el modelo devolvia una fase TERMINAL. Si el modelo improvisaba la confirmacion en `fase_4` (no terminal), el sistema no tomaba control. Mismo defecto que ERR-008 pero en el otro extremo: ERR-008 forzo el CIERRE; faltaba forzar la ENTRADA al resumen.
- Solucion aplicada: al completarse la orden por primera vez (no veniamos de confirmacion), mostrar SIEMPRE el resumen deterministico, sin depender de la fase que devuelva el modelo.
- Nota: se reprodujo el "si" final con el estado REAL de la sesion y el cierre funciona; el "no responde nada" literal (silencio total) apunta a infraestructura (servidor local sin reiniciar o URL de ngrok vencida), no a la logica.
- Archivos afectados: `app/agent.py`, `tests/test_agent_flows.py`.
- Tests: `test_confirmation_summary_shown_even_when_model_does_not_emit_terminal_phase`.
- Estado: corregido.

### ERR-008 — Confirmacion de orden trabada en fase_4 (caso Luciano)
- Severidad: critico
- Flujo: orden de servicio / confirmacion
- Sintoma observado: en `fase_4_confirmacion`, el usuario respondia "si" para confirmar y la orden NO se registraba; quedaba trabado en la confirmacion.
- Causa raiz: el cierre dependia de que el LLM emitiera `fase_6_cierre`. El guardrail `_enforce_confirmation_step` solo PERMITIA cerrar, no lo forzaba; si el modelo (sobre todo en chats largos con varias ordenes) no devolvia la fase terminal, no se registraba nada.
- Solucion aplicada: cierre DETERMINISTICO en `_enforce_confirmation_step` — si veniamos de `fase_4_confirmacion`, el usuario confirma y la orden esta completa, cerrar siempre (contraentrega -> `fase_6_cierre`; pago_linea -> `fase_7_escalado` + contabilidad), sin depender del LLM.
- Archivos afectados: `app/agent.py`, `tests/test_agent_flows.py`.
- Tests: `test_confirmation_closes_deterministically_when_ai_does_not_emit_terminal_phase`.
- Estado: corregido.

### ERR-009 — Flujo "otra orden": faltaba veterinaria, guia y cambio de cliente
- Severidad: medio
- Flujo: programar recogida (orden de seguimiento)
- Sintoma observado: al crear otra orden no se mostraba la veterinaria ni se orientaba que cambia; y si el usuario decia que era para OTRA veterinaria, el flujo no lo manejaba (quedaba clavado).
- Causa raiz: `_start_followup_service_order_response` solo reofrecia medico/direccion/pago; no habia camino para cambiar de cliente a mitad del armado.
- Solucion aplicada: el bloque de confirmacion ahora incluye la veterinaria y agrega un mensaje guia ("lo que cambia normalmente es paciente, propietario y analisis"); `_wants_to_change_client` + `_restart_identification_for_new_client` descartan la identificacion anterior (incluido `client_id` en BD) y re-identifican.
- Archivos afectados: `app/agent.py`, `tests/test_agent_flows.py`.
- Tests: `test_wants_to_change_client_detection`, `test_stable_confirm_change_clinic_restarts_identification`, `test_stable_confirm_yes_advances_to_patient_without_ai`.
- Estado: corregido.

### ERR-010 — Bucle de identificacion con veterinario independiente (caso Chuuck)
- Severidad: critico
- Flujo: identificacion cliente
- Sintoma observado: un cliente no registrado que decia "ahora estoy de forma independiente" o "me tendria que registrar de nuevo" entraba en bucle repitiendo "comparteme el NIT o el nombre exacto", sin derivar.
- Causa raiz: detectores demasiado literales (`_claims_unregistered_client` solo reconocia frases exactas) y falso positivo de `_provides_new_identifier` (la palabra "veterinaria" en una frase explicativa se tomaba como identificador y bloqueaba la derivacion).
- Solucion aplicada: se amplio `_claims_unregistered_client` a formas naturales ("de forma independiente", "me tendria que registrar", "por mi cuenta") y el gate de identificacion prioriza la senal de "cliente nuevo" aunque el mensaje mencione "veterinaria".
- Archivos afectados: `app/agent.py`, `tests/test_agent_flows.py`.
- Tests: `test_independent_unregistered_vet_escalates_instead_of_looping`.
- Estado: corregido. Motivo el refactor de comprension por IA (ver ERR-011).

### ERR-011 — Interpretacion fragil por listas de tokens (refactor comprension por IA)
- Severidad: medio (deuda estructural)
- Flujo: interpretacion de lenguaje (transversal)
- Sintoma observado: el agente interpretaba la intencion del usuario con ~52 detectores basados en listas de tokens/frases exactas. Cada forma nueva de decir algo que no estaba en la lista rompia el flujo (ERR-010 es un caso). La gente nunca responde con la palabra exacta.
- Causa raiz: la interpretacion del LENGUAJE estaba acoplada al codigo determinista, en vez de delegarse al LLM.
- Solucion aplicada (por etapas, parcial): campo `user_intent_signal` en `app/schema.py` que el LLM llena interpretando intencion; cada guardrail lo usa como FUENTE PRIMARIA y mantiene los detectores de tokens como FALLBACK. Etapa 0 (schema+prompt) y Etapa 1 (identificacion de cliente) hechas. Principio: la IA interpreta el significado; el codigo hace cumplir las reglas de negocio.
- Archivos afectados: `app/schema.py`, `app/prompt.py`, `app/agent.py`, `tests/test_agent_flows.py`.
- Tests: `test_new_client_signal_escalates_even_when_phrase_not_in_any_token_list`, `test_provides_identifier_signal_keeps_searching_not_escalating`.
- Estado: en progreso (Etapas 2-4 abiertas, ver ABIERTO-003).

### ERR-012 — Sucursal/sede nueva dejaba clavado en la lista de sedes
- Severidad: medio
- Flujo: identificacion cliente / sedes
- Sintoma observado: un cliente registrado que pedia una sucursal NUEVA no registrada quedaba en bucle: el bot repetia la lista de sedes sin salida.
- Causa raiz: el bloque de seleccion de sedes no tenia camino para "ninguna, es una sede nueva".
- Solucion aplicada: senal `new_branch` (+ fallback `_wants_new_branch`) que, en cualquier punto del flujo, OFRECE derivar para registrar la sede o seguir con una sede ya registrada (no corta seco). Si acepta, deriva a operaciones.
- Archivos afectados: `app/schema.py`, `app/prompt.py`, `app/agent.py`, `tests/test_agent_flows.py`.
- Tests: `test_wants_new_branch_detection`, `test_new_branch_signal_offers_handoff_not_cut`, `test_new_branch_fallback_phrase_offers_handoff_from_sede_list`, `test_handoff_offer_accepted_derives_to_person`, `test_handoff_offer_declined_continues_flow`.
- Estado: corregido.

### ERR-013 — Sin red de seguridad ante inputs random / fuera de flujo
- Severidad: medio
- Flujo: robustez transversal
- Sintoma observado: ante mensajes random o sin sentido (gente que quiere "romper" el bot), el agente podia clavarse o intentar responder algo fuera de su alcance.
- Causa raiz: no habia un comportamiento por defecto seguro ni un corte duro por estancamiento.
- Solucion aplicada: (1) patron "ofrecer, no cortar" — ante algo que no puede resolver, avisa con calma y ofrece "¿te derivo o seguimos?"; (2) anti-bucle: contador `_offtrack_count` que, tras 3 turnos seguidos marcados `unclear`/`off_topic`, deriva a una persona; cualquier turno que encaja lo reinicia.
- Archivos afectados: `app/agent.py`, `app/prompt.py`, `tests/test_agent_flows.py`.
- Tests: `test_offtrack_third_unclear_turn_derives_to_person`, `test_offtrack_counter_resets_when_turn_makes_sense`.
- Estado: corregido (ver limitacion en ABIERTO-002).

### ERR-014 — validate_coherence.py roto (fake sin parametro channel)
- Severidad: bajo (herramienta de verificacion)
- Flujo: tooling / validacion
- Sintoma observado: `python tools/scripts/validate_coherence.py` fallaba con `TypeError: _fake_get_session() got an unexpected keyword argument 'channel'`.
- Causa raiz: el fake del script no se actualizo cuando `db.get_or_create_session` agrego el parametro `channel`.
- Solucion aplicada: el fake acepta `channel="telegram"`.
- Archivos afectados: `tools/scripts/validate_coherence.py`.
- Estado: corregido.

### ERR-006 — Chatwoot se guardaba como Telegram
- Severidad: medio
- Flujo: canal de entrada
- Sintoma observado: conversaciones de Chatwoot usaban `conversation_id`, pero `telegram_sessions.channel`, `requests.entry_channel` y eventos quedaban como `telegram`.
- Causa raiz: `process_turn()` no recibia canal y `db.create_request()` hardcodeaba `telegram`.
- Solucion aplicada: `main.py` pasa `channel="chatwoot"`, `process_turn()` persiste ese canal en la sesion y `create_request()` usa `session.channel` para `entry_channel` y `request_events.event_payload.source`.
- Archivos tocados: `app/main.py`, `app/agent.py`, `app/services/db.py`, `tests/test_agent_flows.py`, `tests/test_db_identification.py`, `tests/test_webhooks.py`.
- Tests: `tests/test_webhooks.py`, `tests/test_db_identification.py`, `tests/test_agent_flows.py`.
- Estado: corregido.

### ERR-007 — Documentacion de arquitectura no coincidia con el agente real
- Severidad: medio
- Flujo: mantenimiento
- Sintoma observado: docs hablaban de solo Telegram, schema simple, fases `collecting|done` y archivos pequenos; el codigo real usa Telegram/Chatwoot, 8 fases, schema amplio y `agent.py` grande.
- Causa raiz: crecimiento incremental del agente sin una actualizacion global de docs.
- Solucion aplicada: `docs/architecture.md`, `README.md`, `docs/contexto-negocio.md`, la decision de pagos y los archivos de contexto para agentes documentan el estado real actual y dejan el refactor como deuda tecnica por comportamiento probado.
- Archivos tocados: `docs/architecture.md`, `docs/contexto-negocio.md`, `docs/decisions/002-payment-method-in-flow.md`, `README.md`, `AGENTS.md`, `CLAUDE.md`, `app/CLAUDE.md`, `tasks/lessons.md`.
- Validacion: revisión documental y grep de inconsistencias principales.
- Estado: corregido.

### ERR-001 — Resultados ofrecidos pero no implementados
- Severidad: critico
- Flujo: resultados
- Sintoma observado: el menu ofrece consultar resultados, pero no existe integracion real de resultados.
- Causa raiz: V1 omitio la integracion de consulta de resultados, mientras docs principales aun prometian lookup real.
- Solucion aplicada: formalizar V1 como mensaje fijo de no disponibilidad por este medio, sin pedir NIT/direccion/paciente ni llamar al LLM para opcion 2.
- Archivos tocados: `README.md`, `app/prompt.py`, `docs/architecture.md`, `tests/test_agent_flows.py`.
- Estado: corregido como contrato V1; implementar consulta real queda como mejora futura.

### ERR-002 — Cliente nuevo tenia regla de negocio contradictoria
- Severidad: critico
- Flujo: cliente nuevo
- Sintoma observado: reglas base dicen escalar sin registrar, pero el codigo iniciaba captura de datos del cliente potencial en chat.
- Causa raiz: el Flujo B quedo activo en el bot conversacional aunque el alta debe quedar en recepción/plataforma.
- Solucion aplicada: al confirmar cliente nuevo o no registrado, el bot escala a operaciones sin pedir datos adicionales ni crear revision pendiente desde el chat. Las sesiones legacy que ya estaban en `_nc_capturing` se siguen atendiendo para no dejarlas colgadas.
- Archivos tocados: `app/agent.py`, `app/prompt.py`, `docs/architecture.md`, `tests/test_agent_flows.py`.
- Estado: corregido.

### ERR-003 — Cliente sin motorizado recibia mensaje incorrecto
- Severidad: critico
- Flujo: programar recogida
- Sintoma observado: la BD podia crear `error_pending_assignment`, pero el mensaje conversacional podia decir "Nuestro motorizado pasara".
- Causa raiz: el cierre se generaba antes de verificar si `client_courier_assignment` tenia motorizado.
- Solucion aplicada: si no hay courier, el reply reemplaza la promesa de recogida por coordinacion manual y la sesion queda con handoff a operaciones.
- Archivos tocados: `app/agent.py`, `tests/test_agent_flows.py`.
- Estado: corregido.

### ERR-004 — Prompt comunicaba mal el corte 17:30
- Severidad: medio
- Flujo: programar recogida
- Sintoma observado: `rules.py` programa post-corte al segundo dia habil siguiente, pero `prompt.py` decia "siguiente dia habil".
- Causa raiz: texto del prompt no estaba sincronizado con la regla pura.
- Solucion aplicada: prompt actualizado a "segundo dia habil siguiente".
- Archivos tocados: `app/prompt.py`.
- Estado: corregido.

### ERR-005 — Opcion 4 dependia demasiado del LLM
- Severidad: medio
- Flujo: menu inicial
- Sintoma observado: la opcion 4 (`Otro`) podia ser absorbida por el flujo dominante de recogida.
- Causa raiz: no habia intercepcion deterministica para esa opcion.
- Solucion aplicada: detector de opcion 4 y handoff directo a operaciones con request de trazabilidad.
- Archivos tocados: `app/agent.py`, `tests/test_agent_flows.py`.
- Estado: corregido.

---

## Plantilla para nuevos bugs

```md
### ERR-XXX — Titulo corto
- Severidad: critico | medio | bajo
- Flujo: identificacion | ruta | resultados | pagos | cliente nuevo | perfil | canal | docs
- Sintoma observado:
- Reproduccion minima:
- Causa raiz:
- Solucion propuesta/aplicada:
- Archivos afectados:
- Tests agregados/actualizados:
- Validacion manual:
- Estado: abierto | pendiente de decision | corregido | monitoreo
```

---

## Indice automatico

<!-- AUTO-GENERATED:START -->
> Bloque generado con `python tools/scripts/refresh_error_report.py`.

### Lecciones registradas
- L1 — Schema excesivo rompe el modelo
- L2 — Fases rígidas como puertas rompen el flujo
- L3 — Lógica fragmentada es imposible de depurar
- L4 — El bot sonaba como formulario, no como persona
- L5 — System prompt y schema mezclados confunden al modelo
- L6 — Heurísticas de "reintento de identificador" demasiado amplias causan bucles
- L6 — Revisar rutas externas indicadas por el usuario
- L7 — Evitar `Start-Process` en OpenCode (Windows)
- L8 — Limpiar identificación fallida antes de reintentar cliente
- L9 — No convertir datos de paciente en nombre de clínica
- L10 — Identificar clientes solo por nombre o NIT
- L11 — El orden de recolección de la orden vive en DOS lugares sincronizados
- L12 — El guard anti-bucle no debe pisar la selección de análisis
- L13 — Forzar términos en español en el prompt para evitar code-switching
- L14 — El "modo construcción de perfil" debe cerrarse cuando exam_type queda fijado
- L15 — La detección de confirmación debe tolerar lenguaje natural, no exigir palabras exactas
- L16 — Cada intent del menú necesita flujo o mensaje propio, si no el LLM arrastra el dominante
- L17 — Los enforcements que hacen I/O deben tener guard previo y ser defensivos
- L18 — No capturar identificador a ciegas: detectar correcciones/confusión de opción
- L19 — Robustez ante clientes que no siguen los pasos (testeo con lenguaje caótico)
- L20 — El fallback anti-bucle necesita un branch por CADA campo, y los enumerados, red de typos
- L21 — El cierre de ruta no puede prometer motorizado sin asignación real
- L22 — Cliente nuevo no se captura en chat si la regla dice escalar
- L23 — La arquitectura documentada debe describir el sistema real
- L24 — La forma de pago en una ruta no debe arrastrar el intent de contabilidad
- L25 — El cierre tras confirmar debe ser determinístico (caso Luciano)
- L26 — La IA interpreta el significado; las listas de tokens son fallback, no autoridad
- L27 — Ante algo fuera de alcance: ofrecer derivar o seguir, nunca inventar ni clavarse
- L29 — Los mocks ocultan bugs de integración: el cierre debe probarse contra la BD real
- L28 — Red anti-bucle por estancamiento (corte duro universal)
- L30 — Verificar coherencia con el negocio y pedir OK ANTES de crear tests/flujos/cambios
- L31 — Corregir un dato en la confirmación debe conservar la fase (caso Rocky, ERR-018)
- L32 — El flujo MULTI-ORDEN debe aguantar turnos intermedios, herencia y "el mismo X" (ERR-023)
- L33 — La comprensión del lenguaje es del LLM, no de detectores de tokens (ERR-024)
- L34 — Preventa no es una orden: responder primero, identificar después
- L35 — La señal de cliente no registrado gana antes del lookup
- L36 — Memoria multiorden no gana contra cambio explícito de cliente
- L37 — Limpiar puentes del habla antes de buscar nombres de cliente
- L38 — Post-cierre y memoria multiorden requieren señales explicitas y backstops
- L39 — Los guardrails de avance no deben pisar respuestas de lookup
- L40 — Toda frase real se procesa como paquete: datos + preguntas + BD
- L41 — Catalogo generico no es analisis cerrado

### Tareas registradas
- Bucle de especie/typos + fallback robótico (caso Luciano) ✅ COMPLETA
- Capa de coherencia en el flujo de datos del paciente ✅ COMPLETA
- Forma de pago dentro de ruta activa ✅ COMPLETA
- Memoria del cliente + manejo de off-topic ✅ COMPLETA
- Desplegar análisis por área/muestra (ej. "orina") ✅ COMPLETA
- Perfiles por necesidad diagnóstica (etiquetas) ✅ COMPLETA
- Alineación con spec v4.3 — Plan por fases (pendiente de aprobación)
- Número de orden legible (A3-00042) — Plan, pendiente de aprobación
- Mensaje "déjame revisar los registros" antes del lookup de cliente — En curso
- Agente Conversacional — Completado
- Agente Conversacional — Pendiente
- Plataforma Interna — Pendiente (NO es el agente conversacional)
<!-- AUTO-GENERATED:END -->
