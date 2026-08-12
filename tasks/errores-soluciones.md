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

### ERR-101 — `/health` devolvía "ok" fijo: el bot podía estar caído y el monitoreo no se enteraba (auditoría de alcance 2026-08-02) — RESUELTO
**Síntoma:** `GET /health` respondía `{"status": "ok"}` sin consultar nada. Con Supabase caído
—sin base no hay sesión, ni cliente, ni orden— el endpoint seguía devolviendo 200, así que
cualquier monitor externo daba el servicio por sano mientras ningún cliente podía ser atendido.

**Causa raíz:** `app/main.py` devolvía un literal. No existía ninguna función de chequeo de
dependencias en el proyecto (`alegra.ping()` era la única, y nadie la llamaba).

**Solución:** nuevo `app/health.py` con `check_all()`, que consulta Supabase de verdad
(`db.ping()`, agregado en `app/services/db.py`), reporta OpenAI como configurado/no configurado
—no se le pega en cada chequeo porque cada llamada cuesta— y consulta Alegra solo si
`ALEGRA_ENABLED`. Distingue **crítico** (Supabase caído → HTTP 503) de **degradado** (Alegra
caído o respuesta lenta → HTTP 200 con `status: degraded`): que falle la facturación no debe
marcar como caída la recogida de muestras. `main.py` solo orquesta, sin importar Supabase,
respetando el invariante de `app/CLAUDE.md`.

**Tests:** `tests/test_health_check.py` — 3 casos (sano, Supabase caído → 503, solo Alegra caído
→ 200 degradado).

---

### ERR-100 — Una orden podía quedar SIN FACTURAR sin dejar ningún rastro (auditoría de alcance 2026-08-02) — RESUELTO
**Síntoma:** si Alegra fallaba al facturar el cierre de una orden, se escribía un `warning` en el
log y se seguía adelante. Peor: si el cliente no tenía NIT, `billing.invoice_order` devolvía
`None` en la primera línea y **no se registraba absolutamente nada**. Nadie podía saber después
qué órdenes habían quedado sin factura — es plata que se pierde sin rastro.

**Causa raíz:** `_try_invoice_in_alegra` (`app/agent.py`) tenía cuatro salidas mudas: `if not
lines: return`, el `None` de `invoice_order` por falta de NIT, el `result` sin `invoice_id`, y los
dos `except` que solo logueaban. Solo el camino feliz escribía en `request_events`.

**Solución:** `_record_invoice_failure()` registra un evento `alegra_failed` en `request_events`
con el motivo (`cliente_sin_nit`, `sin_lineas_facturables`, `alegra_sin_factura`, `error_alegra`,
`error_inesperado`) y el detalle. Todos los caminos que terminan sin factura pasan por ahí. Se
mantiene la garantía de que la facturación **nunca** rompe el cierre de la orden: si ni siquiera
se puede escribir el evento, cae al log y sigue. No toca el esquema de Supabase.

**Tests:** `tests/test_invoice_failure_is_recorded.py` — 5 casos, uno por camino de salida.
Se actualizó `tests/test_alegra_billing.py::test_hook_no_rompe_si_alegra_falla`, que afirmaba
`eventos == []` — es decir, **codificaba este mismo bug** como comportamiento esperado.

---

### ERR-099 — Cambiar de cliente en la confirmación cambia SOLO el nombre: la orden queda con el NIT, la dirección y el motorizado del cliente anterior (QA en vivo por Telegram, 2026-07-28) — ABIERTO, CRÍTICO
**Síntoma (reproducido en vivo, chat 4):** el resumen mostraba `Veterinaria: Pet Agro
Colombia / Dirección de retiro: CL 78C SUR 18G 67`. El cliente pidió corregir y escribió
`"El / Cliente / Soy Animal Pets"`. El bot re-mostró el resumen con
**`Veterinaria: Animal Pets`** y **la misma dirección `CL 78C SUR 18G 67`**. Cuando el
cliente insistió (`"Estoy registrado con otra dirección"`), el bot le pidió que la
escribiera a mano en vez de traerla de la base; y al turno siguiente respondió una frase
sobre especies veterinarias, sin relación con lo que se estaba hablando.

**Estado real de la sesión al terminar** (verificado en Supabase):

| Campo | Valor | A quién pertenece |
|---|---|---|
| `client_id` | `24cb0026-…` | **Pet Agro Colombia** |
| `tax_id` | `1018431256` | **Pet Agro Colombia** |
| `pickup_address` | `CL 78C SUR 18G 67` | **Pet Agro Colombia** |
| `clinic_name` | `Animal Pets` | Animal Pets |

**Animal Pets existe y es otro cliente**: `a88408fe-…`, NIT `53115419-1`, dirección
**`DG 51A SUR 61B-03`** — otra localidad. Si esa orden se hubiera cerrado, se registraba y
facturaba a Pet Agro Colombia, con su motorizado, y el retiro se agendaba a una dirección
que no es la del cliente que figura en la orden. **Es identidad cruzada con impacto
operativo (el motorizado va a la puerta equivocada) y de facturación.**

**Causa raíz — tres piezas que se combinan:**
1. **No existe forma de corregir el cliente.** `_CORRECTION_FIELD_KEYWORDS`
   (`app/detectors/orden.py:57-69`) no tiene ninguna entrada para
   `cliente / veterinaria / clínica / sede`. Los 11 campos corregibles son de la orden, no
   de la identidad.
2. **El detector devuelve el campo equivocado.** Verificado:
   `_detect_correction_field("El\nCliente\nSoy Animal Pets")` → **`patient_name`**, porque
   `"animal"` está en la lista de palabras del paciente (línea 60, junto a "perro", "gato",
   "mascota"). El bot creyó que se corregía el nombre del paciente. De ahí sale también el
   descarrile de los turnos siguientes.
3. **El atajo de cambio de cliente no se dispara.** Verificado:
   `_wants_to_change_client("El\nCliente\nSoy Animal Pets")` → **False**.
   Ese atajo además corre **pre-LLM**, y la identificación completa vive detrás de
   `if not session.get("client_id")` (`app/agent.py`), que con el cliente ya identificado no
   vuelve a ejecutarse nunca.

Con las tres, el modelo escribió `clinic_name = "Animal Pets"` como campo libre y **ningún
código volvió a validarlo contra la base**. Es exactamente la señal de alerta que ya dejó
escrita la lección L55 tras ERR-081: *"un campo capturado por el modelo que ningún código
vuelve a validar contra la base"*. ERR-081 fue el mismo cruce por otro camino (nombre de
sede respondido a la pregunta de la dirección); este es por el carril de corrección.

**Autorización:** el fix toca **B2 · Identificación (✅ APROBADO)** y **B12 · Corrección en
la confirmación (⏳ POR CONFIRMAR)**. Se paró, se avisó y el usuario dio OK explícito para
el arreglo completo (2026-07-28).

**Solución aplicada, en tres partes:**
1. **`app/detectors/orden.py`** — nueva entrada `(("cliente","veterinaria","clinica",
   "clínica","sede"), "clinic_name")` en `_CORRECTION_FIELD_KEYWORDS`. La posición es
   load-bearing y está comentada en el código: **después** de `pickup_address` (para que
   "cambia la dirección de la veterinaria" siga siendo una corrección de dirección) y
   **antes** de `patient_name` (para que "Animal Pets" no lo gane la palabra "animal").
2. **`app/agent.py`** — en los dos puntos donde se procesa el campo a corregir (fase
   terminal y confirmación), `field == "clinic_name"` deriva a
   `_restart_identification_for_new_client`, que ya existía y hace lo correcto: con una
   orden en curso llama a `_switch_client_keep_order`, que descarta
   `_IDENTIFICATION_RETRY_RESET_FIELDS` (**`clinic_name`, `tax_id`, `pickup_address`** y las
   flags de dirección), limpia el `client_id` de la sesión y **conserva** paciente, médico,
   análisis, pago y observaciones (L50: corregir un dato no reinicia el pedido). No se
   escribió lógica nueva de identificación: se conectó el carril que faltaba.
3. **`app/enforcers/orden.py`** — el carril de "¿agregar otro análisis?" cede el turno
   cuando el campo detectado es `clinic_name`, igual que ya hacía con los campos estables.
   El guard existente (`_wants_to_change_client`) no reconocía estos fraseos.

**Invariante anti-recurrencia:** `tests/test_client_change_in_confirmation.py` (17 casos)
fija tres cosas: el detector reconoce el cliente en 5 fraseos reales (incluido el mensaje
literal del chat), los demás campos **no se desplazan** (dirección, paciente, raza, edad,
médico siguen resolviendo igual), y `clinic_name` **no puede quedar junto a**
`pickup_address` tras un cambio de cliente — la forma exacta del cruce.

**Nota sobre el baseline pre-LLM:** `PRE_LLM_RETURNS_BASELINE` sube de 40 a 42 en este mismo
commit. Los dos `return` nuevos no convierten un turno visible en invisible: viven dentro de
bloques que ya retornaban pre-LLM en **todas** sus ramas, y replican el patrón de
`_wants_to_change_client` dos líneas más arriba. Cambia a dónde va el turno, no si el modelo
lo ve.

**Verificación:**
- Detector probado con 9 fraseos, incluido el literal del chat real. Discrimina los tres
  casos que importan: `"El/Cliente/Soy Animal Pets"` → `clinic_name`; `"cambia el nombre del
  animal"` → `patient_name`; `"cambia la dirección de la veterinaria"` → `pickup_address`.
- Suite: **551 passed**, 2 skipped, 1 xfailed.
- Regresión con modelo real: **32/35**, el mismo puntaje que las dos corridas previas al fix.
  El flujo A salió rojo en esa corrida, pero **corrido aislado pasa 2/2**: es el bucle no
  determinista de ERR-096 ("¿qué análisis o perfil desean?"), no una regresión. Se descartó
  además revisando que ningún mensaje de A entre por un camino de corrección.
**Estado:** RESUELTO — **pendiente validación en vivo por Telegram** (rehacer el camino del
chat 4: llegar al resumen con un cliente y pedir el cambio a otro).

### ERR-098 — La API `/api/platform/*` responde datos de todos los clientes SIN autenticación (QA e2e 2026-07-28) — RESUELTO
**Síntoma:** `GET /api/platform/clients?limit=2` devuelve nombre comercial, teléfono, NIT,
dirección, zona y motorizado de los clientes **sin enviar ninguna credencial**. Verificado no
solo en `localhost` sino **desde internet**, por la URL pública de ngrok, durante este QA.
`PATCH /api/platform/requests/<id>/status` también atraviesa el control (devuelve 404 por id
inexistente, no 401): con un `request_id` válido, cualquiera podría cambiarle el estado a una
solicitud.
**Causa raíz:** el decorador `_auth_required` (`app/platform_api.py:23-32`) solo exige el
token **si la variable existe**:
```python
if PLATFORM_API_TOKEN:
    token = request.headers.get("X-Platform-Token", "")
    if token != PLATFORM_API_TOKEN:
        return jsonify({"error": "unauthorized"}), 401
```
`PLATFORM_API_TOKEN` tiene default `""` (`app/config.py:57`), **no está en el `.env`** y en
`.env.example:54` está rotulado como *"Token para la API interna (opcional)"*. Sin la
variable, la puerta queda abierta y no hay ninguna señal de que lo esté: la API responde 200
con normalidad. Es un fallo que **se manifiesta por ausencia de configuración**, que es
exactamente el caso más fácil de que llegue a producción.
**Alcance medido:** las 6 rutas del blueprint (`overview`, `clients`, `requests`,
`requests/unassigned`, `requests/<id>/events`, `PATCH requests/<id>/status`) sobre los 992
clientes reales. Ninguna otra superficie está afectada: el dashboard exige sesión y CSRF
(verificado), y el portal aísla por `client_id` (verificado).
**Solución (aplicada 2026-08-02):** se invirtió el default a **fail-closed**. `_auth_required`
ahora devuelve `503 platform_api_not_configured` cuando `PLATFORM_API_TOKEN` está vacío —la API
queda cerrada, no abierta— y compara el token con `hmac.compare_digest` en vez de `!=`. La
ausencia de configuración ya no puede abrir la puerta.
**Pendiente de configuración:** definir `PLATFORM_API_TOKEN=<valor largo>` en el `.env` local y
en Render antes del deploy; con el fix, hasta que se defina la API responde 503 en vez de servir
datos. Falta también corregir el rótulo "opcional" en `.env.example:54`.
**Tests:** `tests/test_platform_api.py` — `test_platform_api_is_closed_when_token_is_not_configured`
verifica que sin token configurado responde 503 y **ni siquiera consulta la base de datos**;
`test_platform_api_requires_token_when_configured` cubre token ausente y token incorrecto. El
`conftest.py` inyecta un token dummy para que la suite ejercite el camino real y no un bypass.
**Detectado por:** `tools/scripts/qa_web_smoke.py`, que mide esta condición explícitamente.
**Estado:** RESUELTO en código — queda definir la variable de entorno antes del deploy.

### ERR-097 — Un pedido del portal no resuelve el análisis contra el catálogo y queda con valor $0 (QA e2e 2026-07-28) — RESUELTO
**Síntoma:** la solicitud A3-2026-172, creada desde el portal con análisis "Hemograma", se
guardó con `base_profile = {"code": null, "name": "Hemograma", "price": 0}` y
**`total_estimated = 0`**. El mismo pedido hecho por Telegram resuelve el término contra los
159 análisis del catálogo y trae el precio real.
**Causa raíz:** el campo "Análisis solicitado" del portal es un `<input type="text">` libre
(`app/templates/portal/client_new_request.html:28`) y `client_new_request()`
(`app/portal/client_requests.py:49-71`) pasa el texto tal cual a `db.create_request` sin
llamar a `app/catalog.resolve_tests`. El portal nunca tocó la capa de catálogo.
**Consecuencias:** (1) la orden nacida en el portal no tiene valor estimado, ni para el
cliente ni para el dashboard; (2) si esa orden se facturara por Alegra,
`billing.build_invoice_lines` armaría las líneas con `price = 0` — una factura en cero.
**Nota de alcance:** hoy la facturación se dispara desde el cierre del agente, no desde el
portal, así que el riesgo de factura en $0 es potencial, no actual. Pero el camino existe.
**Solución (aplicada 2026-08-02):** se eliminó el texto libre. El formulario del portal ahora
ofrece un `<select>` de perfiles y un multi-select de análisis, ambos poblados desde el catálogo
real (`db.list_catalog_profiles` / `db.list_catalog_tests`). `resolve_catalog_selection()`
(`app/portal/client_requests.py`) traduce lo elegido a `_selected_profile_code/name/price/
description` y `selected_tests` — exactamente los campos que `_profile_event_payload` ya espera —
y arma `exam_type` como etiqueta legible para la tabla.

**Por qué no se reusó `catalog.resolve_tests`:** esa función interpreta lenguaje natural porque
en el chat el cliente escribe libremente. En un formulario web no hay nada que interpretar: se
ofrece la lista y vuelve un código. Un código que no exista en el catálogo se descarta y la orden
no se crea, en vez de inventar un precio. Se cumple igual la lección L48 (lo que afecta dinero no
sale de texto libre), por la vía más simple.

**Tests:** `tests/test_portal_catalog_selection.py` — 5 casos (perfil solo, análisis sueltos,
perfil + extras, códigos inexistentes descartados, selección vacía rechazada). Se reforzó
`tests/test_portal_client.py::test_new_request_uses_session_client_id` para verificar que el
análisis viaja con su código.
**Estado:** RESUELTO (2026-08-02) — el fix está aplicado y con tests. La ficha arrastraba una
segunda línea de estado contradictoria ("ABIERTO — el portal es demostrativo, así que no
bloquea la presentación"), que era la nota previa a aplicar el fix; se retiró el 2026-08-12.

### ERR-096 — Bucle en "¿qué análisis o perfil desean?": el fallo más frecuente del corpus real (QA e2e 2026-07-28) — ABIERTO
**Síntoma:** el bot repite literalmente `"Por último, ¿qué análisis o perfil desean?"` turno
tras turno mientras el cliente responde. En el replay de 8 conversaciones reales de Chatwoot
apareció **16 veces**, más que ningún otro bucle: es el punto donde más gente se queda
trabada. Le siguen `"¿Cuál es la raza del paciente?"` (8), `"¿Quieres agregar algún análisis
más…?"` (4) y `"¿Qué edad tiene el paciente?"` (3).
**Cómo se detectó:** `tools/scripts/replay_chatwoot_qa.py --limit 8` — lenguaje real de los
equipos, lecturas contra los 992 clientes reales, solo las escrituras mockeadas.
**Salvedad de método:** el replay es **fuzzing con lenguaje real, no reproducción fiel** —
los turnos del corpus respondían a versiones anteriores del agente, así que la frecuencia
indica dónde mirar, no cuántas veces pasa hoy. Los 8 segmentos elegidos son además los **más
sospechosos** del corpus por diseño del script (`_suspicion()`), no una muestra
representativa: que den 0/8 limpios no significa que el agente falle siempre.
**Hipótesis de causa (sin confirmar):** la pregunta del análisis es la que más formas de
respuesta admite (código, nombre, perfil, categoría, etiqueta diagnóstica, pedido mixto), y
cuando ninguna resuelve, el flujo vuelve a `missing_route_field_question()` sin acusar que no
entendió. Encaja con el patrón de la lección L50: el flujo sabe avanzar pero no retroceder.
**Próximo paso sugerido:** aislar 3 respuestas concretas del corpus que disparen el bucle y
reproducirlas con `chat_local.py` antes de tocar nada.
**Estado:** ABIERTO — pendiente de confirmar caso a caso.

### ERR-095 — Preguntas de preventa sin dar el NIT: el bot se traba pidiendo identificación (QA e2e 2026-07-28) — ABIERTO
**Síntoma:** el flujo T de `validate_flows.py` falló en **las dos corridas** de este QA, con
dos síntomas distintos del mismo problema:
- Corrida 1: creó una solicitud durante las preguntas de preventa. El cliente preguntó por
  los motivos de muerte de un animal, el bot escaló al equipo humano (correcto) y esa
  derivación registró una solicitud que el flujo no esperaba.
- Corrida 2: **bucle** — repitió dos veces seguidas *"Para gestionar pedidos, A3 atiende
  clínicas y profesionales veterinarios registrados. Para continuar necesito una de estas dos
  opciones: 1) el NIT, o 2) el nombre exacto…"*.
**Observación importante:** las respuestas individuales del bot son **buenas**. Contesta bien
"¿hacen análisis para mascotas?", "¿cómo es la metodología?" y "¿ustedes retiran las
muestras?", y cada vez cierra pidiendo el NIT. El problema no es el contenido: es que cuando
el cliente dice `"estoy registrado te paso mis datos para programar la recogida"` sin dar
todavía el NIT, el bot vuelve a la misma pregunta en vez de reconocer la intención y guiar.
**Por qué importa para la presentación:** las preguntas de preventa son exactamente lo que
haría alguien que ve el bot por primera vez.
**Diferencia con el QA anterior:** el 26-07 T falló en una sola corrida y se clasificó como
no determinista. Hoy falla en las dos: **es un bug real**, no ruido.
**Estado:** ABIERTO — no se tocó, por la decisión de solo documentar en este QA.

### ERR-094 — Corregir un dato en la confirmación borra el valor viejo y RE-PREGUNTA el nuevo (QA 2026-07-27) — RESUELTO
**Síntoma:** en el resumen final el cliente escribe `"cambia el nombre del paciente a Rocky"`
y el bot responde `"¿Cuál es el nombre del paciente?"` con `patient_name=None`. Borró "Laila"
y no leyó "Rocky": le repregunta un dato que el cliente acaba de dar.
**Causa raíz:** `_extract_correction_value` (`app/agent.py:1998`) tenía dos límites duros:
1. `if field != "patient_name": return None` — para edad, médico, raza, propietario o
   dirección **nunca** extraía nada, así que corregirlos en la confirmación costaba siempre
   un turno extra.
2. Aun para el paciente, exigía "se llama / llama / ahora es / paciente es / paciente:".
   La forma natural "cambia el nombre del paciente **a** Rocky" no matcheaba.
Como el flujo (`app/agent.py:2519`) **limpia el campo ANTES** de intentar extraer, el
resultado era el campo en blanco + repregunta.
**Contraste que confirmó el diagnóstico:** la MISMA corrección a mitad del flujo (antes del
resumen) sí funciona — ahí la captura el modelo por el camino normal, no este extractor.
**Solución aplicada:** `_extract_correction_value` reescrito —
`_CORRECTABLE_INLINE_FIELDS` (paciente, propietario, médico, especie, raza, sexo, edad,
dirección) + `_CORRECTION_VALUE_RE` con los conectores reales de la gente
("a", "por", "es", "ahora es", "sería", "debería ser", "se llama", ":"), más limpieza de
artículos ("a un mestizo" → "mestizo"). `exam_type`, `payment_method` y `observations`
quedan FUERA a propósito: el análisis pasa por el catálogo (nada que afecte dinero se toma
de texto libre) y el pago es un enum. La edad sin unidad ("cambiala a 5") se rechaza para
que la pida el flujo normal.
**Verificación con modelo real:** "cambia el nombre del paciente a Rocky" → `patient_name`
= "Rocky"; "cambia la edad a 5 años" → `patient_age` = "5 años" y **re-muestra el resumen
actualizado** sin repreguntar.
**Tests:** `tests/test_correction_value_extraction.py` (10 campos/frases parametrizados +
edad sin unidad + campos con carril propio + sin valor nuevo).
**Suite:** 534 passed.
**Estado:** RESUELTO y verificado con modelo real.

### ERR-092 — El bot acusa "registro Luciano como propietario" y un turno después lo borra (QA en vivo por Telegram, 2026-07-27) — RESUELTO
**Síntoma:** el cliente respondió `Luciano` a "¿Cuál es el nombre del propietario?" y el bot
acusó correctamente `"Perfecto, registro Luciano como propietario. ¿Quieres dejar alguna
observación...?"`. Al turno siguiente el cliente dijo `"No, no tengo ninguna observación"` y
`owner_name` quedó en **"Sin propietario"**. El cliente no tiene forma de detectarlo: dio el
dato, se lo confirmaron, y en la orden va mal.
**Causa raíz (dos piezas que se combinan):**
1. `_detect_which_field_is_being_asked` (`app/detectors/analisis.py:210`) busca la substring
   `"propietario"` en el ÚLTIMO MENSAJE DEL BOT COMPLETO. Como el acuse del turno anterior
   dice "...como propietario", cree que todavía se está pidiendo el propietario.
2. `"ninguna"` está en `_NO_OWNER_TOKENS` (`app/detectors/direccion.py:12`), así que
   `_says_no_owner("No, no tengo ninguna observación")` da True.
Con ambas, el atajo de `agent.py` escribía "Sin propietario" encima del nombre real.
**Solución aplicada (opción elegida por el usuario: blindar el campo, no tocar el detector):**
lógica extraída a `_apply_no_owner_shortcut(fields, prev_captured, user_message, history)` en
`app/agent.py`, que **retorna temprano si ya hay `owner_name`** en `fields` o en
`prev_captured`. La regla de negocio original (paciente callejero → "Sin propietario") sigue
intacta cuando no hay propietario previo.
**Nota:** el detector sigue confundido a propósito — un test lo documenta explícitamente. Si
aparece el mismo choque en otro campo (paciente, médico, raza), la solución de fondo es que
`_detect_which_field_is_being_asked` mire solo la oración interrogativa final.
**Tests:** `tests/test_owner_not_overwritten.py` (4 casos: el detector sigue confundido, el
caso real no borra, protección desde el estado previo, y el callejero sigue funcionando).
**Suite:** 505 passed.
**Estado:** RESUELTO. PENDIENTE validación en vivo.

### ERR-093 — "No seguimos con el pago, te estoy diciendo" re-muestra el menú de perfiles y tira el avance (QA en vivo por Telegram, 2026-07-27) — RESUELTO
**Síntoma:** con la orden casi completa, el bot ofrece "¿agregar otro análisis o seguimos con
el pago?". El cliente responde `"No está bien, yo estaría con eso"` → el bot re-pregunta lo
mismo; el cliente insiste `"No seguimos con el pago, te estoy diciendo"` → el bot **vuelve a
mostrar el menú de perfiles desde cero**, perdiendo el avance.
**Causa raíz:** el atajo que va al pago (`app/enforcers/orden.py:89`) exige
`_wants_to_proceed_to_payment(msg) AND (método de pago explícito OR <= 6 tokens)`. La frase
tiene **8 tokens**, así que no entra; sigue cayendo por la cascada hasta el paso 3, donde
`_doesnt_know_what_to_ask("No seguimos con el pago...")` da **True** y re-lista los perfiles.
La frase además es genuinamente ambigua: "no, sigamos con el pago" vs "no sigamos".
**Solución aplicada (pedido del usuario: ante la duda, preguntar en vez de adivinar):** nuevo
paso 1b en `_handle_extra_analysis_answer` — si el mensaje menciona el pago pero no trae verbo
de agregar/quitar (`_ADD_ANALYSIS_TOKENS` / `_REMOVE_TOKENS`), responde
`EXTRA_ANALYSIS_AMBIGUOUS_QUESTION`: *"Perdona, no te entendí bien: ¿avanzamos con el pago o
quieres agregar otro análisis?"*. Nunca re-muestra el menú ni pierde el perfil elegido.
**Descartado:** filtrar por `_named_analysis_terms` — devuelve palabras sueltas de la frase
("seguimos", "pago"), no análisis del catálogo, así que no discrimina nada.
**Tests:** 3 en `tests/test_extra_analysis_offer.py` (la frase ambigua pregunta y conserva el
perfil; las frases cortas siguen yendo derecho al pago; nombrar un análisis no se secuestra).
**Suite:** 505 passed.
**Estado:** RESUELTO. PENDIENTE validación en vivo.

### ERR-091 — Cliente sin dirección: el bot pide confirmar "sin dirección registrada" como si fuera una dirección (QA en vivo por Telegram, 2026-07-27)
**Síntoma:** con un cliente cuya ficha no tiene dirección (Maxivet), el bot respondió:
`"Tenemos como domicilio de retiro: sin dirección registrada. ¿Es correcta?"` — le pide al
cliente que confirme el texto literal "sin dirección registrada" en vez de pedirle la
dirección.
**Inconsistente (no determinista):** con el MISMO cliente, en prueba aislada previa, el bot
sí había preguntado bien: `"...sin dirección registrada. ¿Cuál es la dirección correcta
donde debemos retirar la muestra?"`. Dos comportamientos para el mismo estado, y la
diferencia la ve el cliente.
**Alcance medido (grande):** **156 de 842 clientes activos (18,5 %) no tienen dirección** en
`clients.address`. Ejemplos reales: Citycan, Clinica Veterinaria Innovet, Novavet, Animal
House Yomasa, Fundación BIODESS. No es un caso de borde: ~1 de cada 5 clientes cae acá.
**Agravante CONFIRMADO en vivo (mismo QA, turno siguiente):** el cliente respondió
`"OK, si no está registrada está bien déjalo así qué hacemos ahora"` y el bot contestó
`"Perfecto, entonces la dejamos sin dirección registrada por ahora. Para dejar la orden de
servicio completa, empecemos con el médico solicitante..."` → **avanzó al siguiente campo
sin dirección de retiro**, que es el dato operativo esencial (sin él el motorizado no sabe
a dónde ir). En la sesión quedó `captured_fields = {'clinic_name': 'Maxivet'}`, sin `address`.
**LA RED DE SEGURIDAD NO PROTEGE (confirmado 2 turnos después):** la sesión quedó con
`pickup_address = 'sin dirección registrada'` — el bot guardó **el texto del placeholder
como si fuera la dirección**. Esto es lo grave: `pickup_address` sí está en
`ROUTE_REQUIRED_FIELDS` (`app/flow.py:21-28`), pero `missing_route_field()` solo comprueba
que el campo sea *truthy*, y `"sin dirección registrada"` es un string no vacío. Es decir,
**el guardrail se satisface con un valor basura y el cierre NO se bloquea**.
**Consecuencia:** se crea una orden con dirección de retiro literal "sin dirección
registrada". No es una orden incompleta (que el sistema rechazaría), es una orden
**inválida que parece válida** y llega al motorizado, que no sabe a dónde ir.
**CAUSA RAÍZ (localizada):** `app/services/ai.py:94`
```python
addr = private.get("_client_address") or "sin dirección registrada"
state_parts.append(f"CLIENTE ENCONTRADO: {name} — Dirección registrada: {addr}")
```
El placeholder se **inyecta en el prompt del modelo** presentado como si fuera el valor real
del campo ("Dirección registrada: sin dirección registrada"). El modelo no tiene forma de
distinguir un texto de relleno de un dato, así que cuando el cliente dice "déjalo así" lo
copia a `pickup_address`. El mismo literal aparece 5 veces más en `app/agent.py:661-701`,
ahí sí legítimamente (son mensajes de presentación al cliente).
**Solución propuesta (NO aplicada):** en `ai.py` no inyectar el placeholder como valor;
cuando `_client_address` está vacío, decirle al modelo explícitamente que el cliente **no
tiene dirección registrada y hay que pedirla**. Complementario: `missing_route_field()`
debería rechazar valores placeholder, no solo cadenas vacías.
**Lección:** un campo obligatorio validado solo por "no vacío" no está validado. Un texto de
presentación (`or "sin X"`) nunca debe entrar al contexto del modelo en la posición donde va
un dato — el modelo lo lee como dato y lo devuelve como dato. Es la lección L54 ("un
docstring que declara una regla de negocio es una decisión") aplicada al prompt: **lo que se
escribe en el prompt es contrato, no decoración**.
**Impacto:** ALTO y silencioso. Afecta al 18,5 % de los clientes activos (156 de 842).
**Detectado:** QA en vivo por Telegram (conv 1), 2026-07-27, con Flask local + ngrok.
**Solución aplicada (2026-07-27, dos capas):**
1. `app/services/ai.py` — si el cliente no tiene dirección, el prompt YA NO recibe el
   placeholder en la posición del dato; recibe una instrucción explícita: *"NO tiene
   dirección registrada en la base. Debes PEDIRLE la dirección de retiro al cliente; no la
   des por válida ni la registres vacía."*
2. `app/flow.py` — nueva `is_placeholder_address()` con los marcadores de relleno
   ("sin dirección", "no registrada", "no aplica", "pendiente"…). La usan
   `missing_route_field()` y `route_ready_for_payment()`, así que una dirección de relleno
   **bloquea el cierre y el paso al pago** en vez de colarse por ser un string no vacío.
**Verificación con modelo real:** el bot ahora responde *"Tenemos como domicilio de retiro:
no tenemos dirección registrada en la base. ¿Cuál es la dirección correcta...?"* y ante
"déjalo así" insiste: *"No puedo dejar la dirección vacía para programar la recogida"*.
`pickup_address` queda en `None`, no con basura.
**Tests:** `tests/test_correction_value_extraction.py` (placeholders vs direcciones reales,
bloqueo del cierre y del paso al pago). **Suite:** 534 passed.
**Estado:** RESUELTO y verificado con modelo real.

### ERR-088 — El escalado a "cliente nuevo" es IRREVERSIBLE: el bot queda mudo aunque el cliente se corrija (QA pre-presentación, 2026-07-26)
**Síntoma:** el cliente responde "creo que no estamos registrados"; el bot escala a
Recepción y setea `_blocked=True`. En el turno siguiente el cliente se corrige — "sí
estamos, somos Maxivet", un cliente REAL de la base — y el bot **no vuelve a responder
nunca**. En el corpus real de Chatwoot (conv 10, Gusmery Ruiz) esto ocurrió de verdad: el
cliente siguió escribiendo **12 turnos al vacío**, incluido su propio nombre.
**Causa raíz:** `_escalate_unfound_client` (`app/agent.py:631`) reutiliza el flag
`_blocked`, que nació para el cliente particular (a quien A3 sí quiere dejar de atender).
En `process_turn` (`app/agent.py:2157`) `_blocked` corta el turno **antes de todo**, así
que ningún dato posterior puede rescatar la sesión. El riesgo ya estaba anotado en la
tabla "Estado de flujos" de este mismo documento ("puede impedir recuperacion si el
usuario luego da datos validos"), pero solo para el caso particular, no para este.
**Alcance medido (no es universal):** de 4 variantes probadas contra clientes reales,
**3 SÍ se recuperan** — escribir mal el nombre ("Citikan"→"Citycan"), dudar ("mmm no sé
bien"→"Maxivet") y dar un nombre inexistente→nombre real. **Solo falla** cuando el cliente
*declara* no estar registrado. Es un camino, no una epidemia.
**Impacto:** en Chatwoot un humano puede rescatar la conversación; en Telegram directo el
cliente queda hablando solo sin ninguna salida desde el chat.
**Reproducción:** `["Hola", "1", "creo que no estamos registrados", "sí estamos, somos Maxivet"]`
→ el 4º turno devuelve `None` y `_blocked=True`.
**Solución propuesta (NO aplicada):** dejar de setear `_blocked` en
`_escalate_unfound_client` y usar un flag propio que permita reabrir el flujo si llega un
identificador que resuelve contra la base. Toca B3 (✅ APROBADO).
**Estado:** ABIERTO — documentado por decisión del usuario (2026-07-26); no se tocó el
código porque el fix cae sobre un paso aprobado del contrato.

### ERR-089 — "Dale Pets": el nombre de un cliente real se descarta por colisión con un token afirmativo (QA pre-presentación, 2026-07-26)
**Síntoma:** tras un primer intento fallido de identificación, el cliente escribe
"Dale Pets" (cliente REAL, `client_id` 8bce027a…). El reintento lo descarta y el bot lo
escala como no registrado.
**Causa raíz:** el guard de reintento (`app/agent.py:1491-1492`) descarta el mensaje si
alguno de sus tokens está en `_CONTINUE_TOKENS | _AFFIRMATIVE_TOKENS | _NEGATIVE_TOKENS`.
`"dale"` está en `_AFFIRMATIVE_TOKENS` (`app/detectors/basico.py:22`), así que "Dale Pets"
se lee como un "dale" de asentimiento y no como nombre propio.
**Familia:** misma raíz que ERR-075 ("Toro"), ERR-078 ("Jorge Toro") y ERR-084 ("José
Toro") — un nombre propio real que colisiona con una palabra funcional.
**Alcance medido:** **1 de 992 clientes** de la base cae en este patrón (nombre ≤4 tokens,
con token funcional y sin palabra de contexto tipo "veterinaria"). Verificado por barrido
sobre `clients.clinic_name`.
**Workaround vigente:** decir "veterinaria Dale Pets" o dar el NIT — ambos ya funcionan,
porque la palabra de contexto salta el guard antes.
**Solución propuesta (NO aplicada):** no descartar el mensaje cuando, además del token
funcional, hay al menos otra palabra que no lo es ("pets").
**Estado:** ABIERTO — documentado por decisión del usuario (2026-07-26). Severidad baja
(1/992 con workaround), pero la familia "nombre propio vs palabra funcional" ya causó 4 bugs.

### ERR-090 — Dos preguntas del cliente se ignoran textualmente a mitad de flujo (QA pre-presentación, 2026-07-26)
**Síntoma:** con el flujo en curso, el cliente pregunta "Y a donde me vas a confirmar" o
dice "Pero ya estaba registrado" y el bot responde **exactamente la misma pregunta
anterior**, sin acusar recibo. Sale del corpus real (conv 10-4), donde el cliente insistió
y terminó escribiendo "No entendí".
**Alcance medido:** de 5 preguntas laterales reales probadas, **3 se atienden bien** —
precio ("$14,000 COP" + retoma), horario de recogida (explica que lo confirma operaciones)
y desconcierto genérico ("Yo ahora que hago" → reformula con calma). Las 2 que fallan son
las que piden *metainformación del proceso* (dónde se confirma, estado del registro), que
B17 no cubre.
**Impacto:** UX, no correctitud — la orden no se corrompe ni se pierde. Visible en una
demo si el cliente pregunta fuera del guion.
**Estado:** ABIERTO — documentado, sin arreglar por decisión de alcance (2026-07-26).

### ERR-103 — Un PERFIL pedido por su código se pierde en la ventana "¿agregar otro análisis?" (simulación con datos reales, 2026-08-12)
**Síntoma:** con un análisis ya registrado, el bot ofrece "¿Quieres agregar otro **análisis o
perfil**…?". El cliente responde "perfil 903" y el bot contesta "Claro. ¿Qué análisis quieres
agregar?"; insiste con "903" y recibe "¿Quieres agregar algún análisis más…?". La orden cerró
SIN el perfil. **El bot ofrece algo que no sabe recibir.**
**Cómo se detectó:** `tools/scripts/sim_cliente_real.py` (nuevo) — una IA hace de cliente
humano contra lecturas REALES de Supabase. Un guion perfecto no lo mostraba: con datos
mockeados la orden al menos cerraba (mal); con un cliente real no cerraba nada. Es la
corrección de método del usuario ese día: *"crea un perfil y vaya respondiendo como un ser
humano normal, no con datos moqueados que son respuestas perfectas"*.
**Causa raíz CONFIRMADA:** análisis y perfiles viven en tablas distintas. En este carril todo
resuelve contra `catalog_tests` (`catalog.resolve_tests`, `get_tests_by_codes_or_names`,
`list_catalog_tests` — `app/enforcers/orden.py:176,182,189`), nunca contra `catalog_profiles`.
Un código de perfil no resuelve nada, y el turno cae al paso 5 ("¿qué análisis querés
agregar?", porque "Sí, perfil 903" es afirmativo) o a la pregunta genérica.
**Es ERR-080 arreglado a medias:** aquella ficha documentó exactamente esto para la
CONFIRMACIÓN y agregó `_add_profile_in_confirmation`, cuyo docstring dice "un código de PERFIL
('1331') no resuelve como análisis". El parche se aplicó solo a la confirmación; la ventana de
la oferta quedó con el agujero original.
**Segunda cara:** el pedido mixto "el 1101 y el perfil 701" resolvía el análisis, retornaba, y
el perfil se perdía en silencio (el juez-IA: "no incorporó el 701 que el cliente pidió varias
veces").
**Solución:** `_attach_profiles_by_code` en `app/enforcers/orden.py`, ubicada ANTES de la
recomendación por "otro/más" (que tapaba el código explícito con una lista genérica) y del
resolvedor de análisis. Consulta TODOS los códigos del mensaje, no solo el primero, porque el
pedido mixto trae análisis y perfil juntos. Con perfil base ya elegido, el nuevo se suma como
adicional (mecanismo ERR-077). Si ya estaba, se acusa "Ese ya está en la orden: …".
**Tests:** `tests/test_profile_by_code_in_offer.py` (7 casos). Suite: 594 passed.
**Verificación en vivo:** simulador con cliente humano y datos reales — orden **A3-2026-901**
para Animal Pets con Perfil Cardiaco III $55.000 + Cuadro Hemático $14.000 = **$69.000**, los
dos ítems presentes. `codigos_mezclados` pasó de MAL a BIEN.
**Autorización:** toca B9.5 (marcado IMPLEMENTADO Y VERIFICADO); OK explícito del usuario.
**Estado:** RESUELTO y verificado en vivo (2026-08-12).

### ERR-088 (bis) — El escalado a "cliente nuevo" era IRREVERSIBLE: el bot quedaba mudo — RESUELTO 2026-08-12
> Nota de numeración: esta ficha es el ERR-088 abierto el 2026-07-26 (escalado irreversible).
> Hay otro ERR-088 más abajo, del 2026-08-03, sobre la cuenta Alegra de Argentina — colisión
> de ID que quedó en la bitácora. Se conservan ambos IDs para no romper referencias previas.

**Síntoma:** si el cliente *declaraba* no estar registrado, el bot escalaba a Recepción y no
volvía a hablar NUNCA, aunque al turno siguiente se corrigiera con un nombre real de la base.
En el corpus real (conv 10, Gusmery Ruiz) hay tres rachas de silencio de 9, 6 y 10 turnos;
el cliente terminó escribiendo *"El bot no esta activo"*.
**Causa raíz CONFIRMADA:** `_escalate_unfound_client` (`app/agent.py:652`) marcaba
`fields["_blocked"] = True` — el MISMO flag del cliente particular/final, donde el silencio sí
es definitivo. Ese flag corta el turno al principio de `process_turn` antes de procesar nada.
**Por qué estuvo abierto tanto tiempo:** no era dificultad técnica sino gobernanza — el fix
cae sobre B3, marcado ✅ APROBADO. El usuario dio OK explícito el 2026-08-12.
**Solución:** el escalado usa su propio flag `_escalated_unfound_client`. La conversación se
reabre SOLO si el cliente aporta un identificador que **existe en la base**
(`_reidentifies_after_escalation` consulta `find_clients_by_tax_id` / `find_client_matches`);
cualquier otro mensaje mantiene el silencio, para no pisar al humano que ya tomó el caso. Ante
error de red devuelve False: falla del lado seguro. Un detector de texto no alcanzaba —
`_provides_new_identifier` exige la palabra "veterinaria" o un NIT, y el caso real es "sí
estamos, somos Maxivet", que no tiene ninguna de las dos.
**Invariantes tocados (ambos en este mismo commit, como exige el test):**
- `PRE_LLM_RETURNS_BASELINE` 42 → 43 en `tests/test_pipeline_invariants.py`. El `return` nuevo
  NO vuelve invisible ningún turno: parte en dos un guard que ya retornaba pre-LLM siempre, y
  al contrario deja pasar al modelo turnos que antes morían ahí.
- `_escalated_unfound_client` catalogado en `FLAGS_IDENTIFICACION` (`app/state.py`).
**Tests:** `tests/test_unfound_client_escalation_is_reversible.py` (5 casos). Suite: 599 passed.
**Verificación en vivo:** simulador con datos reales — "Uy, creo que no estamos registrados"
→ escala; "Ah no, sí estamos, somos Animal Pets" → **"Perfecto, encontramos Animal Pets"** y la
orden sigue. Antes ese turno era silencio.
**Estado:** RESUELTO y verificado en vivo (2026-08-12).

### ERR-084 — "José Toro" (médico) rellena especie=Bovino y sexo=Macho sin preguntar — RESUELTO 2026-08-12
**Síntoma:** un apellido que además es palabra de animal definía la especie y el sexo del
paciente, salteando ambas preguntas. Casos reales: orden **A3-2026-169** cerrada con
"Pipo (Bovino, Sin Determinar, Macho, 5 años)" tras escribir "José toro" como médico; y en la
conv 10 un Equino declarado con raza "Cuarto de Milla" terminó "Fifi (**Bovino**, Cuarto de
Milla, Macho)" porque el propietario se llamaba "Jorge Toro".
**Impacto:** el único de los abiertos con consecuencia CLÍNICA — los rangos de referencia del
laboratorio dependen de la especie, así que la muestra se informa contra los valores normales
de otro animal, y el cliente no lo nota porque el resumen pasa entre otros ocho campos.
**Causa raíz CONFIRMADA:** `_recover_implied_animal_fields` (`app/agent.py:1750`) llamaba a
`apply_implied_animal_fields(fields, user_message)` en TODOS los turnos, sin mirar qué se
había preguntado. La protección de ERR-078 no alcanzaba: si el modelo no re-emite `species` en
ese turno, el campo llega vacío y la inferencia lo escribe igual.
**Solución:** si el último mensaje del bot pedía el nombre de una PERSONA o de la mascota
(`requesting_doctor`, `owner_name`, `patient_name`), la inferencia cede el turno. Reusa
`_reply_asks_for_route_field`, el mismo patrón que ya aplicaban sus dos funciones vecinas
(`_recover_unknown_breed`, `_recover_patient_name_answer`). Requirió pasarle `history`.
El segundo punto de entrada (`_resolve_same_as_previous`, `agent.py:1117`) NO se tocó: ahí el
nombre sale del snapshot de la orden anterior y `user_message` es la frase de referencia
("el mismo"), no un nombre propio — queda documentado en el código.
**Tests:** `tests/test_species_not_inferred_from_person_name.py` (5 casos, incluidos los dos
reales y el camino legítimo "es un toro" al preguntar la especie). Suite: 587 passed.
**Estado:** RESUELTO en tests. Pendiente de aparecer en una conversación real por Telegram.

### ERR-096 — Bucle en "¿qué análisis o perfil desean?" — CERRADO: no reproduce (2026-08-12)
**Resultado de la reproducción que pedía la ficha.** Se aislaron las 3 respuestas del corpus y
se corrieron contra el modelo real. Ninguna reproduce el bucle:

| Respuesta del cliente (corpus) | Comportamiento hoy |
|---|---|
| "Armarlo a medida" | arma el perfil personalizado y sigue |
| "Cuadro hemático, CK NAC, coprológico, coproscópico" | ofrece el menú con los 5 análisis |
| "Tienes perfiles pre quirúrgico?" | ofrece los perfiles armados 701 y 702 |

**Por qué la ficha lo veía:** lo advertía ella misma en su "salvedad de método" — el replay usa
turnos que respondían a versiones anteriores del agente. Los fixes de ERR-045 (categoría),
ERR-076 y ERR-087 (pedido mixto / término vago) ya lo cubrieron.
**Lo que sí salió de esta reproducción:** ERR-103 (perfil por código perdido), que el bucle
original tapaba. La hipótesis de la ficha —"vuelve a `missing_route_field_question` sin acusar"—
resultó FALSA; el problema real era de resolución de catálogo, no de flujo.
**Residuo menor (no arreglado):** responder el menú de perfiles con la categoría
("el prequirurgico") re-muestra el mismo menú idéntico en vez de preguntar cuál de los dos.
Se sale al turno siguiente eligiendo el número.
**Estado:** CERRADO — no reproducible con el agente actual. Reabrir solo con evidencia nueva.

### ERR-088 — La cuenta Alegra nueva es de ARGENTINA: ningún contacto ni ítem se podía crear (preparación de demo, 2026-08-03)
**Síntoma:** al vencer la prueba de Alegra se cargaron credenciales nuevas y
`alegra_demo_invoice.py` falló antes de facturar: `HTTP 400 code 2055 "La condición de IVA
es un campo obligatorio"`. Con el campo agregado, el siguiente error fue `code 2039 "El
tipo de identificación no es válido"`, y luego `code 3140 "La unidad de medida es un campo
obligatorio"` al crear los ítems.
**Causa raíz CONFIRMADA:** `GET /company` devuelve `applicationVersion="argentina"`,
moneda ARS. El módulo construía siempre el contacto con el modelo COLOMBIANO
(`identificationObject.type="NIT"` + `regime` + `kindOfPerson`), que Argentina rechaza:
allá pide `type="CUIT"`, `ivaCondition` obligatoria en el contacto y `unit` obligatoria en
el ítem. Ya estaba anotado como sospecha en un comentario de `alegra.py` (líneas 74-77),
sin resolver.
**Verificado contra la API real:** Alegra Argentina acepta el NIT colombiano de 9 dígitos
tal cual como CUIT (no valida dígito verificador), así que los ~800 clientes de Supabase
facturan sin transformar su NIT.
**Solución:** `alegra.account_country()` resuelve el país UNA vez (`ALEGRA_COUNTRY` del
.env manda; si está vacío lo detecta con `/company`; ante falla asume Colombia) y
`get_or_create_contact` / `get_or_create_item` ramifican el payload. Se invoca solo en los
caminos de CREACIÓN, nunca en las búsquedas, para no agregar llamadas al camino feliz.
El camino colombiano queda intacto para la cuenta del cliente.
**Tests:** suite completa 582 passed, 2 skipped, 1 xfailed (sin tests nuevos: el cambio se
validó end-to-end contra la cuenta real, que es lo que un mock no probaría).
**Verificación en vivo:** `alegra_demo_invoice.py` creó contacto (id 4) + factura
**borrador** `00001-00000001` por $58.000, estado `draft`, y `billing.invoice_to_row` la
mapea bien para el dashboard (NIT 900123456, "Borrador", sin timbrar).
**Pendiente:** la cuenta es ARS y sin DIAN — sirve para demostrar la mecánica, no la
facturación electrónica colombiana. Al migrar a la cuenta del cliente: quitar
`ALEGRA_COUNTRY` del .env (o ponerlo en `colombia`).
**Estado:** RESUELTO y verificado en vivo (2026-08-03).

### ERR-087 — Pedido mixto resumido a UN término vago por el modelo: se pierde todo lo demás (QA en vivo, 2026-07-22, chat 4)
**Síntoma:** primer pedido de análisis "Necesito análisis de sangre u orina, sodio y
potasio" → el bot respondió "Listo, queda análisis de sangre": sodio, potasio y orina se
perdieron y el cliente tuvo que REPETIR el pedido completo (el segundo intento sí funcionó
porque entró por el carril de la oferta, que resuelve el mensaje crudo).
**Causa raíz CONFIRMADA (verificada contra el catálogo real):** el modelo resumió
`exam_type` a "análisis de sangre" (UN término vago) y la compuerta de
`_enforce_multiple_tests_capture` (`len(_split_multiple_exam_items(candidate)) < 2`)
devolvía el turno sin mirar el MENSAJE REAL. El rescate del mensaje crudo de ERR-076
existía pero quedaba DESPUÉS de esa compuerta — inalcanzable. El mensaje crudo resolvía
perfecto: EXACT [1405-Sodio, 1404-Potasio] + pendiente ["análisis de sangre u orina"].
**Hermano de ERR-076:** aquel cubrió "el modelo resume pero deja 2+ ítems"; este es "el
modelo resume a 1 solo término vago".
**Solución:** si el `exam_type` no da 2+ ítems (o no resuelve EXACT), se resuelve el
mensaje crudo con `collect_partial=True`; con 2+ exactos, o 1+ exacto y términos de área
pendientes, sigue el camino de ERR-076 (registrar los unívocos + encolar los ambiguos).
"Quiero un hemograma" (1 exacto sin pendientes) sigue el flujo normal.
**Tests:** 3 nuevos en `tests/test_first_capture_mixed.py` (caso real, control de análisis
suelto, 1 exacto + área). Suite: 443 passed.
**Hallazgos menores del mismo chat (anotados, SIN arreglar por decisión de alcance):**
- Raza en bucle MUDO: "Toro" como respuesta a la raza se rechaza en silencio y se
  repregunta idéntico (el cliente insistió 2 veces); debería explicar y ofrecer "sin
  determinar". Familia ERR-074/075.
- Especie re-preguntada al armar perfil personalizado teniendo `species='Bovino'` ya
  capturada.
- Observación "urgente" guardada BIEN pero sin acuse en la respuesta.
**Estado:** RESUELTO en tests. PENDIENTE validación en vivo.

### ERR-086 — "si no me equivoco" resetea al menú y tira el nombre del cliente (QA en vivo, 2026-07-22, chat 4)
**Síntoma:** el bot pidió NIT/nombre; el cliente respondió "Agrocol estamos registrados si
no me equivoco" y el bot contestó "Tranquilo, sin problema 🙂" + menú de bienvenida,
descartando el "Agrocol" del mismo mensaje. La identificación volvía a cero.
**Causa raíz:** `_wants_to_reconsider_option` (detectors/orden.py) disparaba con el token
"equivoco" de `_OPTION_CORRECTION_TOKENS` sin mirar la NEGACIÓN: "si NO me equivoco" es
muletilla de duda, no "me confundí de opción". El atajo corre PRE-LLM (agent.py:2225) —
misma clase que ERR-067/070/072/073: tokens sueltos deciden antes de que el modelo lea.
**Solución:** el token de equivocación con un "no" hasta 2 palabras antes no dispara, y ese
mismo "no" negador deja de contar como pista en el fallback (`opción` + hints). "Me
equivoqué de opción" y "quiero cambiar de opción" siguen reconduciendo al menú.
**Tests:** `tests/test_reconsider_not_hedging.py` (3: muletillas no disparan, equivocación
real sí, turno completo del chat real busca Agrocol en vez de resetear).
**Estado:** RESUELTO en tests (440 passed). PENDIENTE validación en vivo.

### ERR-085 — 188 veterinarias del roster invisibles para el bot: carga parcial de datos (QA en vivo, 2026-07-22)
**Síntoma:** el usuario probó identificarse como "Agrocolombia" (está en el Excel de
actualización) y el bot no la encontró. Auditoría completa: **188 veterinarias** de
"Clientes y Doctores A3.xlsx" (Hoja1, 663 únicas) no tenían fila en `clients`, aunque SÍ
estaban en `clients_a3_knowledge`/`clients_a3_professionals` (sus médicos cargados).
**Causa raíz:** `import_client_roster.py` por diseño solo insertaba en `clients` a las que
tenían NIT (y como `is_active=False`, invisibles igual); las de solo-nombre quedaban en
knowledge. La identificación del bot busca en `clients` → 188 clientas reales del roster
resultaban "no registradas" y escalaban como cliente nuevo.
**Además:** la primera lectura de `clients_a3_professionals` truncó en 1.000 filas (tope de
PostgREST) y distorsionaba el diagnóstico — la tabla tiene 1.554. Paginar SIEMPRE.
**Solución aplicada (autorizada por el usuario):**
- `tools/scripts/load_missing_clients_2026_07.py`: insertó las 188 como clientes ACTIVOS;
  18 con NIT/dirección/teléfono de "Alegra - Terceros v2" (solo matches de 2+ tokens — se
  descartó un falso positivo de 1 token que le daba a "Tu Vet Friend" el NIT de "My Best
  Friend"). Teléfonos sin dato: placeholder único '5700...' (columna UNIQUE).
- 4 fichas completadas después (VeroPets, Animalbog, Dr. Jhon, Pet House) y 2 terceros de
  Alegra insertados (Gaitan Burgos, Gutierrez Ramirez). 1 duplicado con typo del Excel
  ("Venencia") borrado. Total clients: 804 → 993.
- **Anti-recurrencia:** `tools/scripts/verify_update_documents.py` — 4 checks (veterinarias,
  razas, NITs Alegra, médicos) con exit code; ninguna actualización de documentos se cierra
  sin este verificador en cero. Estado actual: veterinarias 0, razas 0 (332/332), médicos 0.
**PENDIENTE (decisión del usuario):** conflicto Club Animals — la base tiene las 3 sedes
con NIT 23784139(-2) y duplicados viejos sin NIT; Alegra v2 trae NIT nuevo 1055126168
(Nicolas Aguirre). No se pisó el NIT existente sin confirmación.
**Verificación bot:** `find_client_exact('AgrocolombiaSA')` ✓; 'Agrocolombia', 'Fun
Animals', 'VeroPets', 'Citycan', 'Maxivet', 'Kennel Dog' ✓. Motorizado: cliente sin
asignación registra la orden y escala a operaciones (agent.py:2056) — sin acción.
**Estado:** RESUELTO salvo el conflicto Club Animals.

### ERR-083 — "Nose" escrito junto repregunta la raza (QA en vivo del usuario, 2026-07-22, chat 4)
**Síntoma:** el bot preguntó la raza; el cliente respondió "Nose" y el bot repreguntó la
raza. Al escribir "No se" (separado) sí funcionó: `breed='Sin Determinar'` y la orden siguió.
Es el único síntoma que el usuario notó en un test que por lo demás cerró bien (orden
registrada, perfil personalizado con sodio/potasio, pago en línea escalado).
**Causa raíz:** `_says_does_not_know` une los tokens con espacios y busca las frases de
`_UNKNOWN_ANSWER_PHRASES` como substring; "nose" es UN token y "no se" no es substring de
"nose" (ERR-074 cubría las formas separadas).
**Solución:** agregar "nose" y "nolose" a `_UNKNOWN_ANSWER_PHRASES` (agent.py).
**Tests:** 3 casos nuevos en `tests/test_unknown_field_answers.py` ("Nose"/"nose"/"nolose").
**Estado:** RESUELTO en tests (437 passed en la suite del agente). Validado el patrón contra
el chat real.

### ERR-084 — "José Toro" (MÉDICO) rellena especie=Bovino y sexo=Macho sin preguntar (mismo test, 2026-07-22)
**Síntoma:** el cliente dio el médico "José toro"; el bot NUNCA preguntó especie ni sexo
(saltó de paciente directo a raza) y la orden quedó registrada con `species='Bovino'` y
`sex='Macho'` para el paciente "Pipo" — datos inventados que el cliente no notó. Verificado
en la sesión real del chat 4.
**Causa raíz CONFIRMADA:** tercera cara de la familia "Toro" (ERR-075 paciente, ERR-078
propietario). El fix de ERR-078 impide REEMPLAZAR una especie explícita, pero
`_recover_implied_animal_fields` (agent.py) corre en todos los turnos de route_scheduling y
la rama de campo VACÍO sigue llenando especie/sexo desde cualquier token del mensaje —
incluido un apellido respondiendo la pregunta del médico. Con especie y sexo llenos,
`missing_route_field` salta esas preguntas y nadie valida el dato.
**Riesgo:** la muestra se procesa con especie/sexo incorrectos (los rangos de referencia
del laboratorio dependen de la especie).
**Fix propuesto (NO aplicado):** la inferencia implícita no debe correr cuando el mensaje
responde una pregunta de nombre de PERSONA (médico/propietario/paciente/veterinaria), usando
`_detect_which_field_is_being_asked`/`_reply_asks_for_route_field` como ya hace
`_recover_patient_name_answer` (ERR-075). "Tengo un toro para hemograma" seguiría funcionando.
**Decisión del usuario (2026-07-22):** por ahora solo registrar; no tocar la captura de
especie/sexo en esta sesión.
**Estado:** ABIERTO — pendiente de decisión para aplicar el fix.

### ERR-080 — El "Si" de confirmación cae en bucle y la orden NUNCA se registra (mismo chat 10, 2026-07-21)
**Síntoma:** el cliente confirmó el resumen con "Si" (22:18) y el bot respondió "Claro.
¿Qué análisis quieres agregar?" en bucle: "El perfil 1331" → misma pregunta; "1331" →
misma pregunta; hasta que escribió "Exit". Verificado en la sesión real: `request_id=None`
— la orden confirmada jamás se creó. **El peor bug del chat: el cliente hizo todo bien y
se fue sin orden.**
**Causa raíz CONFIRMADA (dos capas):**
1. `_awaiting_additional_test` quedó pegado desde ANTES de la confirmación (turno "Si 3"
   de 22:13, seteado en `orders.py:406`). En `_enforce_confirmation_step`
   (`enforcers/confirmacion.py`), `_confirmation_analysis_adjustment` corre ANTES del
   cierre determinístico, así que el "Si" se intentaba resolver como análisis, fallaba,
   re-armaba el flag y repreguntaba. El cierre era inalcanzable.
2. "1331" es código de PERFIL: `get_tests_by_codes_or_names` no resuelve perfiles
   (hallazgo de diseño ya documentado en ERR-077), así que ni nombrando el código exacto
   había salida del bucle.
**Solución (2 cambios mínimos en `app/enforcers/confirmacion.py`):**
- Al mostrar el resumen por primera vez se hace `pop("_awaiting_additional_test")`: el
  resumen ("¿Confirmas?") supersede cualquier pregunta de agregar abierta en fases previas.
- `_add_profile_in_confirmation` (nueva): si lo que nombró el cliente es un PERFIL del
  catálogo (código primero, nombre de fallback), se suma a `_extra_profiles` (mecanismo de
  ERR-077, el resumen ya lo muestra y suma) o se fija de base si no había; sin duplicar.
**Tests:** `tests/test_confirmation_close_not_looped.py` (5: el escenario real completo
resumen→"Si"→cierre, perfil por código sin bucle, no-duplicado, análisis normal intacto,
"si" tras pregunta legítima no cierra en falso).
**Estado:** RESUELTO en tests (483 passed). PENDIENTE validación con modelo real.

### ERR-081 — Nombre de sede como respuesta a la dirección: identidad cruzada entre dos clientes (mismo chat 10, 2026-07-21)
**Síntoma:** el bot preguntó "¿Cuál es la dirección correcta?" y el cliente respondió
"Centro veterinario La Uribe" (un NOMBRE). El bot solo cambió el texto de la veterinaria:
la orden quedó con `clinic_name='Centro Veterinario La Uribe'` pero `client_id` y
dirección del Centro Médico Veterinario (AV CL 32 19-26). **La sede correcta SÍ existe en
la base** ("Centro Medico Veterinario La Uribe", CL 172A 21A-28): el motorizado habría ido
a la dirección equivocada y la orden se facturaría al cliente equivocado.
**Causa raíz CONFIRMADA:** toda la identificación vive bajo `if not session.get("client_id")`
(agent.py). Con la sesión ya identificada, un `clinic_name` nuevo capturado por el modelo
no dispara ninguna búsqueda: queda como texto suelto encima del cliente viejo.
**Solución (rama nueva y acotada en `app/agent.py`, tras el bloque de dirección):** en la
ventana "dirección rechazada y aún sin respuesta", si el modelo captura un `clinic_name`
distinto al previo: match único → re-vincular (`link_client_to_session` +
`_store_client_context`) y confirmar la dirección de la sede NUEVA (mismo paso aprobado);
varias coincidencias → limpiar la identificación y reusar la lista de selección existente;
ninguna → NO pisar al cliente identificado y repreguntar la dirección.
**Tests:** `tests/test_address_reject_with_clinic_name.py` (4: el caso real re-identifica y
ofrece la dirección nueva, nombre inexistente no pisa nada, varias sedes listan opciones,
responder con una dirección sigue el flujo normal).
**Estado:** RESUELTO en tests. PENDIENTE validación con modelo real.

### ERR-082 — Batch "1 / 1 / 2" atendió solo el último + latencia de ~2 min por turno (mismo chat 10, 2026-07-21)
**Síntoma:** el cliente envió "1" (18:36), no vio respuesta, reenvió "1" y probó "2"; los
tres llegaron CONCATENADOS en un solo mensaje ("1 / 1 / 2") y el bot respondió solo a la
última señal (resultados). Además la latencia general fue de ~1.5–2 min por turno — el
propio cliente se quejó en el chat ("si cada pregunta dura 2 minutos... son 20 min").
**Análisis:** el comportamiento de responder a la última señal del batch es defendible (el
cliente cambió de opción precisamente porque no veía respuesta); la CAUSA fue la latencia.
**Decisión:** sin cambio de código en la lógica de batcheo. Queda como comportamiento
conocido documentado.
**PENDIENTE (tarea de investigación aparte):** medir dónde se van los ~90–120s por turno
(logs de Render: cold start vs latencia del modelo vs queries) y decidir si hace falta un
acuse inmediato ("dame un momentico") o ajuste de infraestructura.
**Estado:** ABIERTO — investigación de latencia pendiente.

### ERR-077 — Menú de perfiles: elige "1, 3 y 6" y solo queda el 1 (QA en vivo del usuario, 2026-07-21)
**Síntoma:** el bot ofreció 6 perfiles recomendados; el cliente respondió "1, 3 y 6" y la
orden quedó SOLO con `101 Perfil Parasitológico I` ($30.000). El 103 ($40.000) y el 1331
($90.000) se perdieron sin ninguna señal. Al insistir ("Te pedí el 1, 3 y 6") el bot
respondió con la oferta genérica de agregar análisis, y a "3 / 6" repitió lo mismo.
**Evidencia:** chat real `external_chat_id=10`, 2026-07-21 22:09–22:12.
**Impacto: bug de DINERO.** La orden se confirma por $30.000 en vez de $160.000, y el
resumen previo tampoco muestra lo que falta, así que el cliente confirma sin notarlo.
**Causa raíz CONFIRMADA (dos capas):**
1. `_select_profile_from_menu` (agent.py:444) hacía `picks[0]` sobre una selección que el
   parser YA resolvía completa. El docstring lo decía explícito: "un perfil es una sola
   elección". El parser NUNCA fue el problema — verificado aislado: `_select_tests_from_menu`
   devuelve `['101','103','1331']` para "1, 3 y 6".
2. `_capture_profile_menu_selection` hace `fields.pop("_profile_menu_options")`, así que la
   insistencia del cliente ya no tenía menú contra el cual matchear.
**NO es ERR-076** (aquel era perfil + sueltos en TEXTO LIBRE en la primera captura, y sigue
resuelto). Esta es la selección NUMÉRICA sobre el menú ya mostrado: otra ruta.
**Hallazgo de diseño:** los perfiles extra NO pueden ir en `selected_tests` — un código de
perfil (103) no resuelve como análisis (`get_tests_by_codes_or_names(['103']) -> []`), así
que el resumen los perdería y el total volvería a quedar corto. Se verificó contra la base
real ANTES de elegir el enfoque.
**Solución (enfoque aprobado por el usuario: primero como base + resto adicional):**
- `_select_profiles_from_menu` (nueva, plural) devuelve todos; `_select_profile_from_menu`
  queda como envoltorio para los call sites que sí fijan un único perfil base.
- `_capture_profile_menu_selection(..., extra_profiles=[...])` guarda `_extra_profiles` con
  código/nombre/precio de catálogo, y los nombra en el acuse. Se limpia SIEMPRE al fijar un
  perfil base nuevo (multiorden: no arrastrar adicionales de la orden anterior).
- `_order_summary_lines` muestra "- Perfiles adicionales:" y los suma al total.
- `_extra_profiles` catalogado en `state.py` (lo exigió `test_state.py`).
**Tests:** `tests/test_multi_profile_menu_selection.py` (5, incluye control de selección
simple y de no-arrastre en multiorden).
**Estado:** RESUELTO en tests (475 passed). PENDIENTE validación con modelo real en Telegram.

### ERR-078 — "Jorge Toro" (propietario) convierte un Equino en Bovino (mismo chat, 2026-07-21)
**Síntoma:** el cliente confirmó "Equino" y su Cuarto de Milla; más tarde dio el propietario
"Jorge Toro". La sesión quedó en `species='Bovino'` y el menú de perfiles llegó a decir
"Para bovino te puedo recomendar". Verificado en la sesión real: `species = 'Bovino'`.
**Causa raíz CONFIRMADA:** `apply_implied_animal_fields` (species.py:80) escribía la especie
siempre que la actual estuviera en `RECOVERABLE_SPECIES`:
`if not fields.get("species") or current_species in RECOVERABLE_SPECIES`. La intención era
NORMALIZAR ('perro' → 'Canino'), pero la condición también permitía REEMPLAZAR una especie
por otra distinta. `"toro"` está mapeado a `("Bovino","Macho")` y aparece como APELLIDO.
El docstring prometía "sin pisar un dato que el cliente ya dio de forma explícita" — hacía
exactamente lo contrario. **También pisaba el SEXO** (Hembra → Macho), descubierto al testear.
**Primo de ERR-075** ("Toro" como nombre de paciente): el mismo apellido, otra ruta.
**Solución:** solo se escribe si la especie actual apunta a la MISMA canónica
(`RECOVERABLE_SPECIES.get(current) == species`), idem sexo. Una corrección real del cliente
llega con el campo ya limpio y entra por la rama de vacío, así que sigue funcionando.
**Tests:** `tests/test_species_not_overwritten.py` (5, incluye normalización y corrección).
**Estado:** RESUELTO en tests. PENDIENTE validación con modelo real.

### ERR-079 — Cantidades sobre un menú cobran análisis no pedidos (hallazgo al revisar ERR-077, 2026-07-21)
**Síntoma:** con un menú de 6 opciones, "5 del 1 y 6 del 3" se leía como las opciones
**5, 1, 6 y 3**: dos análisis intrusos, cobrados. "quiero 3 del 2" → opciones 3 y 2.
No estaba reportado: apareció al probar el pedido del usuario de soportar cantidades.
**Por qué no había explotado antes:** con menús cortos el número de cantidad caía fuera de
rango (`1 <= n <= len(options)`) y se descartaba por casualidad. Con 6 opciones sí entra.
**Decisión del usuario (2026-07-21, revisada):** manejar la cantidad por análisis (registrar
N veces el mismo, "5 del primero") es lógica compleja que POR AHORA no se hace. El bot no
pregunta ni intenta interpretar cantidades: ignora el cuantificador y absorbe solo las
opciones ("5 del 1 y 6 del 3" → opciones 1 y 3). Lo innegociable es no cobrar análisis no
pedidos ni confundir una selección con una cantidad.
**Solución (final):** una sola red defensiva, `_strip_quantities`, limpia el cuantificador
antes de parsear ("5 del 1" → "del 1"). Exige el CONECTOR ("N del/de la/x M"), así "el
primero, el segundo y el tercero" sigue siendo selección múltiple normal (preocupación del
usuario). Se descartó la primera versión que además preguntaba "¿son varios pacientes?"
(`_quantity_note`/`_mentions_quantities`): el usuario pidió no agregar esa lógica
conversacional, así que se quitó para no dejar código muerto (lección L52).
**Tests:** `tests/test_menu_quantity_not_option.py` (6: absorbe opciones, no cobra intrusos,
ordinales no se confunden, selección normal intacta).
**Estado:** RESUELTO en tests. PENDIENTE validación con modelo real.

### ERR-073 — QA de ESTRÉS (8 baterías, modelo+base real): hallazgo de fondo del reorden 3.3 (2026-07-20)
**Método:** batería adversarial cubriendo la mayoría de etapas (identificación, captura de
paciente, análisis, confirmación/retroceso, pago, multi-orden, combos en una frase).
**Resultado por etapa:** identificación 4/4 OK; captura de paciente 3/4 (C2 corrección
especie+nombre sin acuse claro); análisis 3/4; pago/cierre OK salvo fraseos; **cambio de
cliente (C2) fue el más frágil**.
**HALLAZGO DE FONDO (la causa raíz común):** el reorden 3.3 asume que la señal del modelo
manda, pero los atajos determinísticos PRE-LLM (carril de oferta de análisis, bloque "el de
siempre", corrección en confirmación, recomendación de perfil) interceptan el turno ANTES de
que el modelo lo lea. Verificado con spy + llamada directa: el modelo clasifica BIEN
("cambiemos el cliente…" → change_client; "cambia la edad a 5 años…" → correction), pero el
atajo responde primero porque su guard de cesión depende de una red de tokens INCOMPLETA. Es
la misma clase de ERR-072, repetida en varios atajos. El reorden C degradó los 3 atajos de
intención de alto nivel, pero quedaron atajos de conveniencia/corrección que no ceden.
**Solución aplicada (alto impacto, bajo riesgo):** ampliar `_CLIENT_CHANGE_SIGNAL_TOKENS` con
las formas verbales flexivas (cambiala/cambiemos/ponela/pasala/facturala…). La ventana de
adyacencia (ERR-070) evita falsos positivos ('pasa el hemograma' no dispara). Con esto, los
guards de cesión de los atajos SÍ disparan → el turno llega al modelo. Re-QA batería A: de
3/6 fallando a 4/6 OK (+1 defendible como new_branch, +1 flaky del modelo).
**PENDIENTE (misma clase, para la Tanda D / reorden más profundo — NO parchear apresurado):**
- E4: "cambia la edad a 5 años y confirmo" → el atajo de corrección en confirmación limpia el
  campo y repregunta, ignorando el valor "5 años" que el modelo SÍ capturó.
- H1: "ponme un hemograma pero cambiá el paciente a Rocky" (combo análisis+corrección) → el
  atajo de recomendación intercepta; el modelo emite correction pero no se aprovecha.
- Captura: corrección de especie+nombre en un turno sin acuse explícito.
Estos exigen que los atajos de corrección/confirmación CEDAN al modelo (cirugía del pipeline,
Tanda D). Un parche de tokens más no alcanza y arriesga regresiones (lección ERR-072).
**Tests:** test_signal_reorder.py (verbos flexivos + no-falsos-positivos). Suite: 330 passed.
**Estado:** PARCIAL — C2 reforzado; el resto de la clase queda anotado para la Tanda D.

### ERR-076 — PERFIL + análisis sueltos en un mensaje: el perfil se pierde (QA real del usuario, 2026-07-21)
**Síntoma:** el cliente pide un PERFIL y análisis INDIVIDUALES en la misma frase
("necesitamos un pre quirúrgico, un análisis de sodio y uno de potasio") y la orden queda
SOLO con los análisis sueltos. Verificado con modelo real:
`exam_type='Perfil personalizado (2 análisis)'  selected_tests=['1404','1405']` — el Perfil
Prequirúrgico I ($24.000) NO está. El bot incluso responde *"Listo, registro estos 2 análisis…
Ahora vamos con lo siguiente que pediste:"* y la frase queda truncada: ANUNCIA que sigue con
el resto y no sigue.
**Es NO DETERMINÍSTICO.** Tres corridas del mismo guion (flujo QA8 de `validate_flows.py`):
(1) registra solo sodio+potasio y pierde el perfil; (2) ofrece el menú de perfiles y entra en
BUCLE 3 veces, sin crear la orden; (3) igual que (1).
**Impacto: es un bug de DINERO.** La orden sale sin un perfil que el cliente pidió
explícitamente, y el resumen previo a confirmar tampoco lo muestra, así que el cliente
confirma una orden incompleta sin notarlo.
**Origen:** apareció en el QA real del usuario (conversación de Chatwoot 1, 07-21 14:10), donde
el acuse fue todavía más vago: *"Listo, lo anoto"*, sin nombrar análisis ni precios.
**Causa raíz (hipótesis, sin confirmar):** es la clase ya documentada en
`docs/estado-agente-qa.md` — dos intenciones en un mensaje, donde un atajo interno
(`_enforce_multiple_tests_capture`, que mapea ítem→código 1:1) responde antes de que el modelo
resuelva el turno completo. El perfil no mapea 1:1 a un código de análisis individual y se cae
del racimo. NO está causado por el catálogo de razas ni por los cambios de datos de esta sesión.
**Causa raíz CONFIRMADA — un bug de nombre de parámetro, más un ítem que se evaporaba:**
1. `_enforce_multiple_tests_capture` llamaba `_scan_ambiguous_terms(fields, candidate)` con
   `candidate = fields["exam_type"]` (enforcers/orden.py:314), y el parámetro receptor se llama
   literalmente `user_message` (orders.py:305). Si el modelo normalizaba `exam_type` a
   "Sodio, Potasio", el prequirúrgico de la misma frase no estaba en ese texto. El comentario
   inmediatamente anterior decía "los términos con OPCIONES… NO se pierden": la intención era
   correcta y TODA la maquinaria ya existía (`_pending_ambiguous_items` → `_offer_next_pending`
   → `list_catalog_profiles_matching_category`); solo recibía el texto equivocado.
2. `catalog.resolve_tests` caía al fallback sobre el texto completo (catalog.py:257) cuando
   algún ítem no resolvía, y el ítem desaparecía SIN señal de estado.
3. Al elegir el perfil del menú llega solo "el 1": los análisis sueltos del pedido original se
   perdían al fijarse el perfil (la pérdida INVERSA, que apareció al arreglar la primera).
**Solución (Etapas 0-2 del plan, con OK del usuario):**
- `catalog.ResolveResult.unresolved` — campo ADITIVO que reporta los ítems no representados. No
  se tocó la semántica del fallback de :257 (hace funcionar nombres multi-palabra y está cubierto
  por test_catalog_module.py); cambiarlo habría sido repetir ERR-072.
- `_enforce_multiple_tests_capture` recibe `user_message` (default vacío para no romper llamadas
  posicionales) y prioriza `result.unresolved`, con el escaneo de texto como red.
- `_category_profiles_menu_response` (embudo único de los 8 call sites del menú de categoría)
  guarda `_mixed_request_text` cuando el pedido traía varios ítems; `_capture_profile_menu_selection`
  lo reaplica con `_profile_addition_if_mentioned`, que ya sabía descomponer un pedido mixto.
- **Garantía de dinero:** `_prevent_incomplete_route_closure` no deja cerrar la orden con
  `_pending_ambiguous_items`, con tope de 3 ofertas y descarte con acuse (lección de ERR-074:
  un campo obligatorio sin salida de emergencia es un bucle infinito).
**Tests:** `tests/test_first_capture_mixed.py` (+5, incluye el control de que sin residuo la orden
SÍ cierra y el tope de reintentos) y `tests/test_pipeline_invariants.py` (4 invariantes nuevos).
Los 18 de catálogo pasan SIN editar una línea — era el criterio de aceptación.
**Verificado con MODELO REAL y DATOS REALES:** `validate_flows.py QA8` → los tres pedidos quedan
en la orden (`exam_type='Perfil Prequirúrgico I'`, `selected_tests=['1405','1404']`). De paso el
validador dejó de usar una lista de análisis inventada: ahora carga el catálogo real (159 filas),
igual que ya hacía con las razas — ajustar el mock para que un flujo diera verde habría sido
fabricar el resultado.
**Estado:** RESUELTO. Suite: 455 passed.
**Reproducción:** `python tools/scripts/validate_flows.py QA8`

### ERR-074 — "No sé la raza" traba la orden para siempre (QA adversarial de razas, 2026-07-20)
**Síntoma:** el cliente responde "no sé la raza" y el bot NUNCA cierra la orden. El modelo
entiende y decide seguir ("Entiendo, no pasa nada. Para Axolote no manejo una raza específica,
lo dejamos pendiente. ¿Qué edad tiene el paciente?"), pero desde el turno siguiente todas las
respuestas se contestan con "¿Cuál es la raza del paciente?", en bucle infinito. Reproducido en
el flujo QA3 de `validate_flows.py` contra el modelo real.
**Causa raíz:** `breed` está en `ROUTE_REQUIRED_FIELDS` y `missing_route_field` (flow.py:100)
solo comprueba truthiness — no existe forma de decir "no aplica". Cuando el modelo deja el campo
vacío a propósito, `_enforce_first_missing_after_progress` (agent.py) lo vuelve a pedir en cada
turno. El guardrail determinístico le gana al modelo y no hay salida de emergencia.
**Alcance:** NO es exclusivo de especies exóticas. Afecta a todo cliente que no sepa la raza —
mestizos de la calle y rescatados, que son mayoría en varias clínicas. Es la misma clase que los
bugs abiertos en `docs/estado-agente-qa.md`: un atajo interno responde antes que el modelo.
**Solución (con OK del usuario):** `_recover_unknown_breed` en agent.py — si el bot pidió la
raza y el cliente dice que no la sabe, se registra `BREED_UNKNOWN = "Sin determinar"` y el flujo
avanza. No se toca `flow.py` ni el orden de campos del paso B4; una raza real nunca se pisa.
**Detalle que costó el primer intento:** el guard usaba `_detect_which_field_is_being_asked`,
que hace match por substring y evalúa `"especie"` ANTES que `"raza"` (detectors/analisis.py:218).
Un cierre como *"anoto Axolote como especie. ¿Cuál es la raza del paciente?"* resolvía a
`species` y el guard no disparaba nunca. Se cambió a `_reply_asks_for_route_field(..., "breed")`,
que exige la frase completa "raza del paciente".
**Tests:** `tests/test_unknown_field_answers.py` (9 fraseos de "no sé", no pisar una raza real,
solo actuar cuando se preguntó la raza) + flujo E2E QA3 en `validate_flows.py`.
**Estado:** RESUELTO. Verificado con MODELO REAL: la orden cierra. Suite: 437 passed.

### ERR-075 — Paciente con nombre de animal ("Toro") nunca se captura (QA adversarial, 2026-07-20)
**Síntoma:** paciente llamado "Toro". El bot responde "Perfecto, lo anoto. ¿Cuál es el nombre del
paciente?" y repite esa pregunta indefinidamente; la orden nunca avanza. Reproducido en el flujo
QA1 de `validate_flows.py` contra el modelo real.
**Causa raíz:** el prompt (prompt.py:74) instruye explícitamente que "toro", "vaca", "cerdo" son
la ESPECIE y nunca la raza, para evitar que se confundan. Con esa instrucción el modelo lee
"Toro" como especie (Bovino + Macho vía `apply_implied_animal_fields`) y deja `patient_name`
vacío, con el mismo bucle de campo obligatorio del ERR-074.
**Alcance:** nombres de mascota que coinciden con palabras del dominio animal — Toro, Oso, Lobo,
Gato, Puma, Perla. Frecuente en Colombia.
**Solución (con OK del usuario):** `_recover_patient_name_answer` en agent.py — si el bot pidió
el NOMBRE del paciente y la respuesta es UNA sola palabra del dominio animal, se toma como nombre.
La especie no se infiere de esa respuesta puntual; *"es un toro de 3 años"* (varias palabras)
sigue infiriendo Bovino como antes.
**Tests:** `tests/test_unknown_field_answers.py` (Toro/gato/conejo se capturan; la especie queda
libre; no pisa un nombre ya capturado; una frase larga no cuenta) + flujo E2E QA1.
**Estado:** RESUELTO en cuanto al bucle del nombre (verificado con modelo real: "Toro" se captura
y el flujo avanza). El flujo QA1 sigue marcando problemas por OTRA causa ya conocida y abierta:
tres correcciones de raza encadenadas ("no perdón, es criollo" / "me equivoqué, es un Holstein"),
que es la clase documentada en `docs/estado-agente-qa.md` — corrección con el valor nuevo en el
mismo mensaje, pendiente de la reorganización de `process_turn` (Tanda D).

### ERR-072 — Regresión C2: "Antes quiero cambiar el cliente" caía en el bloque "el de siempre" (prueba en vivo del usuario, 2026-07-20)
**Síntoma:** con perfil 152 + sodio/potasio ya cargados y la oferta de análisis activa,
"Antes quiero cambiar el cliente" respondió "Por último, ¿qué análisis o perfil desean?"
en vez de cambiar de cliente. El cambio de cliente funcionaba con otros fraseos ("esta
cuenta va a otra clínica") — de ahí que el QA del 07-18 no lo cazara.
**Causa raíz (efecto colateral del reorden C2):** al degradar el atajo pre-LLM de cambio de
cliente (que corría temprano y ESCUDABA los bloques siguientes), el mensaje llegó al bloque
"el de siempre" (agent.py ~2283). "Antes quiero cambiar el cliente" matchea
`_is_same_as_previous` por la palabra **"antes"** (∈ _SAME_AS_PREVIOUS_TOKENS = "el de
antes") → respondió la re-pregunta del campo. NO llegó al modelo (interceptado pre-LLM).
Es exactamente el riesgo que anota el plan del reorden: al degradar un atajo, verificar que
ningún atajo intermedio agarre mal el mensaje.
**Solución (clase L50, mínima):** guard `and not _wants_to_change_client(user_message)` en
el bloque "el de siempre" — cede ante un cambio de cliente para que la señal del modelo
mande. Verificado con MODELO REAL: "Claro, cambiamos de cliente… mantengo el resto de la
orden". "el mismo" genuino sigue funcionando (no es cambio de cliente).
**Tests:** test_signal_reorder.py (regresión + no-regresión de "el de siempre" real).
**Estado:** RESUELTO. Suite: 330 passed.

### ERR-070 — QA real post-Fase 3: la red de tokens de change_client robaba el turno de another_order (2026-07-18)
**Origen:** QA adversarial con MODELO REAL y base real (5 escenarios, sesiones qa-*),
tratando de romper el agente tras el cierre de Fase 3.
**Síntoma:** tras cerrar una orden, "me quedó pendiente mandarles sangre de otro peludo
DE LA CLÍNICA" respondió "Claro, cambiamos de cliente" (pidió NIT de una nueva veterinaria)
en vez de iniciar la otra orden. REGRESIÓN del reorden C2: antes el guard de fase terminal
frenaba el falso positivo; post-reorden la fase ya está mutada cuando corre el handler.
**Causa raíz (clase ERR-066, palabras sueltas donde el dato es una secuencia):**
`_wants_to_change_client` matcheaba "otro"+"clinica" SUELTOS en toda la frase — la mención
casual de la clínica no es un cambio de cliente.
**Solución (en la fuente, beneficia a TODOS los call sites):** el detector exige señal de
cambio y sustantivo de cliente/sede CERCANOS (ventana de 3 palabras). Además, defensa en el
handler C2: su red de tokens no aplica si la señal es another_order ni si la fase de ENTRADA
del turno (`_turn_prev_phase`) era terminal. Verificado con modelo real: el fraseo inicia la
otra orden reofreciendo estables, y "el de siempre" resuelve al médico recordado.
**Tests:** test_signal_reorder.py (falso positivo + fraseos reales siguen matcheando).
**Estado:** RESUELTO. Suite: 328 passed.

### ERR-071 — QA real: 4ª ruta de la clase ERR-067 — el menú de área machacaba los exactos en la primera captura (2026-07-18)
**Síntoma:** "sodio potasio y orina" como PRIMER pedido, cuando el modelo no capturaba
nada, caía en `_enforce_test_category_help`: el menú del área ponía `selected_tests=[]`
y Sodio+Potasio se perdían EN SILENCIO (la orden cerró solo con Parcial de Orina $16k).
**Causa raíz (clase ERR-067, "el primer match del área gana"):** ese helper no descomponía
el pedido mixto — 4ª ruta de la misma clase (tras 067 agregado-a-perfil, 067d primera
captura vía exam_type, 067e categoría de perfil).
**Solución (mismo patrón):** antes de ofrecer el menú del área, `resolve_tests` con
`collect_partial`: lo inequívoco se registra ya y el menú del área se ofrece como AGREGADO
(`_test_menu_adds_to_profile`: la selección SUMA, no reemplaza). "orina" pelado (sin
exactos) conserva el comportamiento clásico. Verificado con modelo real: "Listo, registro
1404-Potasio $12k, 1405-Sodio $12k. Ahora vamos con lo siguiente que pediste: [menú uro]".
**Observaciones del QA (menores, anotadas SIN tocar):** (a) cuando el modelo emite un
código ADIVINADO (p.ej. Electrolitos por "sodio potasio"), el grounding ofrece el menú del
área del adivinado (minerales) antes que el del término del mensaje — diseño de ERR-053,
no pierde datos; (b) "quiero ver perfiles para gatos" durante la recogida se ignora con la
re-pregunta seca del campo pendiente (clase ERR-069 pero con PREGUNTA; candidato a la
auditoría L50 pendiente).
**Tests:** test_signal_reorder.py (mixto conserva exactos + área pelada sin cambio).
**Estado:** RESUELTO. Suite: 328 passed.

### FASE-3-CIERRE — Refactor de raíz: 3.2 + 3.3 + 3.4a completados (2026-07-18)
**Qué se cerró** (plan `snug-dancing-tiger`, tandas con suite verde y commit cada una):
- **3.4a** (`cee8ec7`, `f5e9a5f`): 21/21 enforcers en `app/enforcers/` (nuevos:
  `confirmacion.py`, `resultados.py`); capa de helpers de respuesta en `app/laterales.py` +
  text/menus/orders. agent.py 3.582→3.181 líneas, sin ningún `_enforce_*`. Puro movimiento.
- **3.2** (`86f7183`): FSM en modo BLOQUEO de ESTADO — `FSM_ENFORCE=true` en `.env` local;
  `heal()` probado en el embudo (el par de flags pegadas llega REPARADO a `update_session`).
  Decisiones: flags fantasma no se dropean en runtime (typo = fallo de suite, test app-wide);
  transiciones ilegales quedan en detección (grafo descriptivo). Flip del default en
  `config.py` PENDIENTE de la prueba en vivo.
- **3.3** (`5fe8737`, `9c86290`, `ba5ee3a`): reorden pre-LLM completo — los 3 atajos de
  intención (otra-orden, cambio cliente/sede, no-registrado) degradados a handlers
  post-modelo SEÑAL-primero con tokens de red y guards portados (rama de sede, menús
  limpios sobre prev_captured, bypass ERR-037). El carril de la oferta cede cambio de
  cliente al modelo. Trade-off: +1 llamada LLM en esos turnos raros.
**Validación:** suite 325 passed; `validate_flows.py` (modelo real): los flujos de las áreas
tocadas (B, K, L, T) OK; los problemáticos NO son regresión — A falla IGUAL en el commit
base `784b799` (verificado con worktree) y F/M/M2/S/T varían entre corridas (flakiness).
**Pendientes que deja:** (a) prueba en vivo del usuario → flip del default FSM_ENFORCE;
(b) Tanda D (partir `process_turn` en `app/turno/`) en sesión aparte cuando C repose;
(c) ABIERTO-VALIDATOR: el flujo A del validador (multi-orden tras resumen) falla
PREEXISTENTE — en la corrida observada, "contraentrega" disparó una recomendación de
perfiles y "sí, quiero otra orden" sobre el resumen no cerró la orden. Diagnosticarlo
como bug propio (no es del reorden).

### ERR-069 — La corrección de un dato del paciente se guardaba SIN acuse y los carriles la devoraban (prueba en vivo Chatwoot #4, 2026-07-17)
**Síntoma:** "Me confundí con la raza es un tobiano" → el modelo capturó bien (breed=Tobiano
desde el PRIMER intento) pero la respuesta fue la plantilla genérica "Perfecto, lo anoto.
¿propietario?" — el cliente no supo si su corrección fue tomada. Insistió 3 veces; con la
oferta de agregar análisis activa, cada intento respondía "¿Qué análisis quieres agregarle?"
(bucle). No fue pérdida de dato: fue falta de ACUSE + carriles que no ceden.
**Causa raíz (clase): empuje determinístico que no cede ante una corrección.**
- `_handle_extra_analysis_answer` (PRE-modelo) interceptaba todo turno del carril; "modificar"
  incluso matchea `_wants_partial_analysis_change` → el mensaje ni llegaba a la IA.
- `_enforce_first_missing_after_progress` (POST-modelo) pisaba la reply del modelo con
  "Perfecto, lo anoto. {faltante}" sin distinguir corrección de progreso.
- La política correcta YA existía formulada en `_enforce_payment_step` (LÓGICA DE RETROCESO
  L50: señal correction → el empuje cede) pero solo estaba aplicada ahí.
**Solución (diseño pedido por el usuario: acusar el cambio + retomar el paso):**
- Carril PRE-modelo: si `_detect_correction_field` apunta a un campo ESTABLE de la orden
  (`_STABLE_ORDER_FIELDS`: paciente/médico/dirección), el carril devuelve None y la IA lee
  el turno ("la IA lee todo, el código verifica").
- POST-modelo: `_corrected_stable_fields` (había valor y cambió = corrección) → reply
  determinística "Listo, corrijo raza: Tobiano." + el paso pendiente (pregunta del faltante,
  o la re-oferta `EXTRA_ANALYSIS_OFFER` si el carril está activo). Progreso normal conserva
  "Perfecto, lo anoto.".
- Movidos a capa correcta (fuente única, sin ciclos): `_detect_correction_field` +
  `_CORRECTION_FIELD_KEYWORDS` → `detectors/orden.py`; `FIELD_LABELS` → `flow.py`.
**Límite conocido:** re-enviar el MISMO valor ya guardado (2º intento idéntico) no genera
acuse determinístico (no hay cambio) — responde el modelo con historial. El acuse del primer
intento previene la insistencia.
**Pendiente (clase, tarea aparte):** auditar los demás empujes que reescriben `reply` o
interceptan pre-modelo y aplicarles la misma guarda L50.
**Tests:** `tests/test_correction_ack.py` (5, mensajes reales). Suite: 311 passed (6 fallos
preexistentes de red, ajenos).
**Estado:** RESUELTO en código — pendiente prueba en vivo del usuario.

### ERR-067d/e — El pedido MIXTO en la PRIMERA captura de análisis perdía datos (prueba en vivo Chatwoot #4, 2026-07-17)
**Origen:** análisis del historial real (conversación Chatwoot #4). Dos órdenes seguidas
perdieron análisis. ERR-067 arregló el camino "agregar a un perfil YA anclado"; estos son los
HUECOS GEMELOS en la PRIMERA captura, que no pasaban por ese camino.
**Síntoma:**
- **ERR-067d:** "Sodio potasio y orina" como primer pedido → `_enforce_multiple_tests_capture`
  absorbía Sodio(1405) y Potasio(1404) pero SE TRAGABA orina: ni la ofrecía ni la encolaba.
- **ERR-067e:** "un perfil prequirúrgico" dado por NOMBRE (categoría con 6 variantes) → el
  early-return de `_looks_like_catalog_profile` en `_enforce_loose_exam_catalog_resolution`
  ("lo resuelve su propio camino") lo dejaba como texto suelto sin código ni precio; el camino
  propio solo ancla perfiles ÚNICOS, así que se perdía del resumen. "prequirúrgico" PELADO
  (sin "perfil") sí funcionaba — de ahí la diferencia.
**Causa raíz (clase):** la lógica paso-a-paso (absorber lo de opción única + encolar lo de
opciones múltiples: `_scan_ambiguous_terms` + `_pending_ambiguous_items` + `_offer_next_pending`)
vivía SOLO en el camino de agregado a perfil. La primera captura tenía su propia resolución que
no descomponía el pedido mixto.
**Solución (mínima, reusa lo existente):**
- `_enforce_multiple_tests_capture`: tras absorber los de opción única, `_scan_ambiguous_terms`
  sobre el texto capturado → los términos con OPCIONES quedan en `_pending_ambiguous_items` y
  `_analysis_settled_response` los ofrece uno por uno (paso a paso, en orden de pedido).
- `_enforce_loose_exam_catalog_resolution`: si el texto parece perfil PERO no es específico
  (`not _looks_like_specific_profile_query`), ofrecer `_category_profiles_menu_response` (las
  variantes reales) antes del early-return. Un perfil específico ('...I', '152') sigue su camino.
**Nota de deploy:** el síntoma EN VIVO (ofreció orina y perdió sodio/potasio) es de código
VIEJO — el código actual de la branch ya no lo produce (reproducción determinística). El bot que
se probó a las 15:17 corría sin los commits ERR-067 de las 13:32–14:00 → **redesplegar la branch**.
**Tests:** `tests/test_first_capture_mixed.py` (4, mensajes reales del chat). Suite: 306 passed
(6 fallos preexistentes de dashboard/portal_auth por red a Supabase, ajenos).
**Estado:** RESUELTO en código — pendiente redeploy y prueba en vivo del usuario.

### ERR-067 — El pedido MIXTO (área + tests nombrados) perdía los nombrados; el compuesto dependía del verbo (prueba en vivo, 2026-07-17)
**Síntoma:** "le quiero agregar un análisis de ORINA, SODIO y POTASIO" mostró el menú de
orina pero PERDIÓ sodio y potasio (pedidos DOS veces, ausentes de la orden final). Y el
compuesto con typo ("le quiero ARRESTAR aparte...") perdió todo el agregado.
**Causa raíz (clase):** en el camino de agregar-al-perfil, "el primer match gana": el menú
del área respondía primero y se tragaba los nombres exactos del mismo mensaje. Y la
detección de "quiere agregar" dependía del VERBO ("agregar"), no del contenido.
**Solución:** `orders._profile_addition_if_mentioned` — mira el CONTENIDO: resuelve primero
lo nombrado inequívoco (se agrega ya, con precio, vía resolve_tests collect_partial) y
ADEMÁS ofrece el menú del área si la frase la menciona (pedido mixto descompuesto, mismo
patrón del anclaje ERR-061). La selección de perfil lo consulta siempre (el verbo queda de
fallback) → el typo es irrelevante. "El 152" pelado no dispara nada (test).
**Tests:** tests/test_mixed_profile_addition.py (3, con los mensajes reales del chat).
**Estado:** RESUELTO. Suite: 300 passed.

### ERR-066 — El match exacto no probaba SECUENCIAS de palabras: 'Sisi es animal Pets' no encontraba a Animal Pets (prueba en vivo, 2026-07-17)
**Síntoma:** tras rechazar la lista de coincidencias ("estoy seguro que ya me tienen
registrado"), el flujo entra al modo solo-match-EXACTO. Ahí "Sisi es animal Pets" y
"Ya te lo di / Animal Pets" dieron "No encuentro ningún cliente" DOS veces, con el nombre
correcto adentro, hasta que el cliente escribió el nombre pelado.
**Causa raíz (clase: palabras sueltas donde el dato es una secuencia):** el reintento
exacto probaba el nombre capturado (venía sucio) y tokens SUELTOS ("sisi", "animal",
"pets") — ningún cliente se llama exactamente "Animal" ni "Pets", pero "animal pets"
(el bigrama) sí es el nombre exacto y nunca se probaba.
**Solución:** el reintento prueba también los PARES y TRÍOS consecutivos de palabras
significativas (tríos primero, más específicos). Sigue siendo match exacto: no cambia el
diseño aprobado post-rechazo. Verificado directo: find_client_exact("animal pets") → Animal Pets.
**ERR-066b (mismo chat, menor):** el menú de orina se tituló "Para HORMONAS..." — la
etiqueta del área salía del PRIMER hit (Cortisol en Orina, categoría Hormonas). Ahora es
la categoría más común entre los hits (test en test_catalog_module).
**Estado:** RESUELTO. Suite: 297 passed. Lo demás del test funcionó completo (cabra→Caprino,
compuesto 152+sodio/potasio, menú de orina, ráfaga combinada, pago natural, cierre).

### ERR-065 — Ráfagas de mensajes: cada fragmento se procesaba por separado (prueba en vivo, 2026-07-16)
**Síntoma:** el cliente escribió "Si como no" / "La veterinaria es" / "Animal PET" en 6
segundos (así habla la gente real). El bot procesó cada fragmento solo: buscó "Si como no"
como nombre de veterinaria → "No encuentro ningún cliente… ¿Eres cliente nuevo?" dos veces,
antes de que llegara el dato real.
**Causa (lógica de transporte, no del flujo):** los webhooks procesaban cada mensaje entrante
de inmediato; no existía noción de "el cliente todavía está escribiendo".
**Solución:** buffer de ráfagas con debounce (`app/services/debounce.py`, capa de transporte —
el agente no cambia): al llegar un mensaje se esperan `MESSAGE_DEBOUNCE_SECONDS` (5s, en
`.env`); si llegan más, se acumulan y la espera se reinicia; al parar la ráfaga TODOS los
fragmentos se procesan como UN solo mensaje (unidos con salto de línea) y se responde una vez.
Tope duro `MESSAGE_DEBOUNCE_MAX_WAIT` (20s) para ráfagas interminables. Con 0 queda apagado
(modo tests: webhooks síncronos como antes). Estado en memoria del proceso — si se escala a
varios workers en Render, moverlo a Supabase/Redis (anotado en el módulo).
**Trade-off asumido:** TODA respuesta ahora tarda ~5s más (el costo de esperar la ráfaga).
**Tests:** `tests/test_debounce.py` (5: ráfaga real combinada, chats no se mezclan, tope duro,
fallo no rompe el buffer, passthrough síncrono). Suite: 290 passed.
**Estado:** RESUELTO — pendiente prueba en vivo del usuario mandando la ráfaga real.

### ERR-064 — Auditoría de trampas léxicas: 5 palabras comunes del español auto-agregaban tests (2026-07-16)
**Origen:** tras ERR-063 el usuario preguntó si había más frases "raras" latentes ("la gente
habla con muchas palabras que no se conectan"). Se construyó una AUDITORÍA determinística:
~200 palabras comunes del español conversacional disparadas contra el catálogo real por los
tres caminos (resolución EXACT, menú de área, anclaje names_test).
**Hallazgos (bugs latentes, nunca reportados):** una sola palabra común auto-agregaba un test:
"cálculo" → Estudio de Cálculo **$83.000** ("hazme el cálculo"), "básico" → Espermograma Básico
$44.000, "panel" → Panel Coagulación $74.000, "cuadro" → Cuadro Hemático $14.000, "lectura" →
Lectura Sedimento $7.000. Y "medio" activaba el menú de Microbiología.
**Causa raíz (clase):** `_name_is_named_by` aceptaba que UNA palabra genérica del español
nombrara un test si era parte de su nombre (primer token distintivo o ≥50% de cobertura).
**Solución (clase):** `catalog.GENERIC_DESCRIPTORS` (~40 descriptores genéricos: básico,
completo, total, parcial, panel, cuadro, lectura, cálculo, control…): solos JAMÁS nombran un
test — solo apoyan junto a una palabra distintiva del dominio ("cuadro HEMÁTICO" sí). Aplica a
la resolución, al anclaje (names_test) y a ambos buscadores de área. El nombre completo de cada
test sigue resolviendo EXACT (verificado).
**Tests:** `test_catalog_module.py::test_generic_spanish_word_alone_never_names_a_test` (frases
de plata reales: "hazme el cálculo del total" ya no agrega nada). Suite: 285 passed.
**Verificación:** re-auditoría → 0 trampas en los tres chequeos. El script de auditoría queda
como herramienta (correrlo tras cada cambio de catálogo).
**Estado:** RESUELTO.

### ERR-063 — "vamos CON el 152..." ofrecía el menú de Coagulación: una preposición elegía el área (prueba en vivo, 2026-07-16)
**Síntoma:** "vamos con el 152 y le quiero agregar potasio y sodio si?" registró bien el perfil
152 pero ofreció el menú de COAGULACIÓN (PT, PTT, Dímero D…) — nada que ver con lo pedido.
**Causa raíz (matching por palabra estructural, la clase de siempre):** el camino compuesto
("perfil + agregar") prueba primero el ÁREA con el mensaje completo; `find_tests_by_area`
filtraba tokens solo por longitud (≥3) y la preposición **"con"** matcheó la muestra
"Tubo Tapa Azul CON 3/4 de sangre" → área = Coagulación. El mismo hueco existía en
`catalog._resolve_area`. Bug latente: cualquier mensaje con "con"/"para"/"las" podía disparar
un menú de área fantasma.
**Solución (de clase, vocabulario único):** `catalog.STRUCTURAL_TOKENS` (fillers + sustantivos
genéricos + verbos de pedido) como fuente única; `db.find_tests_by_area` y `catalog._resolve_area`
excluyen esas palabras de ambos lados del match — una palabra estructural jamás identifica un
área. Con esto, el camino compuesto cae al match por nombre y agrega Potasio+Sodio directo.
**Tests:** `test_catalog_module.py::test_structural_words_never_match_an_area` +
`test_db_identification.py::test_find_tests_by_area_ignores_structural_words` (con control
positivo: "tubo tapa azul" sí matchea). Suite: 284 passed. Verificado en vivo con modelo real.
**Estado:** RESUELTO.

### ERR-061 — El modelo estructuraba selected_tests él solo y elegía un test AMBIGUO en silencio (prueba en vivo, 2026-07-16)
**Síntoma:** "quiero hacer potasio sodio y orina" → el bot respondió "Listo, lo anoto" sin
mostrar precios y con 'Parcial de Orina' (1601) ya elegido POR EL MODELO entre las 5 opciones
de orina del catálogo — el cliente nunca eligió ni vio el menú.
**Causa raíz (I3 por la puerta lateral):** el resolvedor unívoco (`resolve_tests`, Fase 1) solo
corre cuando el análisis llega como TEXTO; si el modelo estructura los códigos directamente en
`selected_tests`, ningún guardrail validaba que cada código correspondiera a un análisis que el
cliente NOMBRÓ. El I1 solo chequea que el código exista. Además el intro de la oferta ("Listo,
lo anoto") no mostraba ítems ni precios.
**Solución:** nuevo guardrail `_enforce_selected_tests_grounding` + `catalog.names_test` (mismo
criterio de contenido distintivo que la resolución): cada código NUEVO capturado por el modelo
debe estar anclado al texto del cliente (mensaje, turnos recientes o la oferta previa del bot);
lo anclado se registra MOSTRANDO ítems y precios, y la adivinanza se convierte en MENÚ de su
área (elige el cliente, nunca el modelo). El pop de menús pegados de ERR-060 se refinó: solo
descarta menús ARRASTRADOS (idénticos a prev), un menú puesto en el turno se respeta.
**Tests:** `tests/test_selected_tests_grounding.py` (5) + 2 en `test_extra_analysis_offer.py`
(lógica pura, estado real, sin fingir el modelo — L51). Verificado en vivo con modelo real.
**Estado:** RESUELTO.

### ERR-062 — El borrador de Alegra facturaba $48.000 cuando el chat cotizó $41.280 (prueba en vivo, 2026-07-16)
**Síntoma:** la orden A3-2026-148 (4 pruebas sueltas) se cerró cotizando $41.280 (subtotal
$48.000 − 14% descuento por volumen) pero el borrador creado en Alegra quedó en $48.000.
**Causa raíz:** `billing.build_invoice_lines` arma las líneas a precio pleno de catálogo y no
conocía el descuento por volumen de los perfiles personalizados (los tramos DISCOUNT_TIERS se
configuraron después de escribir billing). Además `db._profile_event_payload` persistía el
total sin descuento (`calculate_profile_adjusted_total`) para el perfil personalizado puro.
**Solución:** para el perfil personalizado (sin perfil base con precio): (1) `billing` aplica el
% del tramo como descuento por línea (solo pruebas no-convenio) → la factura suma exactamente lo
cotizado; se elimina la línea de perfil $0; `invoice_order` pasa `discount` al item de Alegra.
(2) `db._profile_event_payload` persiste el total cotizado (subtotal, volume_discount, total).
Los perfiles armados (precio fijo) siguen sin descuento, igual que el chat.
**Tests:** 3 nuevos en `tests/test_alegra_billing.py` (total = $41.280 exacto; perfil base sin
descuento; el % viaja al item de Alegra). Suite: 280 passed.
**Estado:** RESUELTO — pendiente de verificar el monto en la cuenta zidong en el próximo cierre
de orden del usuario.

### ERR-060b — El reescritor anti-bucle adivinaba el campo por PALABRAS del reply y tapaba la pregunta real (prueba en vivo, 2026-07-16)
**Síntoma:** con "es un toro" (Bovino/Macho implícitos) y la RAZA pendiente, el usuario respondió
"macho" (no es una raza). El bot quedó en bucle infinito repreguntando "¿el paciente es macho o
hembra?" — un dato que YA tenía — y nunca volvió a preguntar la raza. 3 turnos idénticos.
**Causa raíz (parche de palabra, la clase que L50 prohíbe):** `_rephrased_repeated_question`
elegía la pregunta canned adivinando el campo por tokens del TEXTO del reply. El reply del modelo
re-confirmaba "Macho como sexo" mientras repetía la pregunta de raza → contenía "macho"/"sexo" →
el reescritor la sustituía por la pregunta de sexo, pisando la de raza. Como "macho" tampoco
avanzaba la raza, el ciclo se repetía cada turno.
**Solución (fuente de verdad, no palabras):** `_avoid_repeated_question` ahora recibe `session` y
pregunta el campo REALMENTE pendiente con `_missing_route_field` (determinístico); el canned por
tokens queda solo de último fallback cuando no hay campo de ruta pendiente. La pregunta re-escrita
siempre corresponde al dato que de verdad falta.
**Tests:** `tests/test_avoid_repeated_question.py` (3, lógica pura sobre el estado exacto del bug,
sin fingir el modelo — L51). Suite: 270 passed. Verificado en vivo reproduciendo la secuencia real
con modelo real.
**Origen forense (verificado en git a pedido del usuario):** NO fue regresión de los cambios de
julio. El mecanismo (adivinar por palabras del reply) existe desde el 2026-05-20 (`e5d8456`) y la
rama "¿macho o hembra?" desde el 2026-06-16 (`694e518`, caso Luciano). Estaba byte-idéntico en el
estado aprobado del 07-13 (`b0a1471`); el diff de esas funciones entre ese estado y el previo al
fix es vacío. Latente un mes: disparó por primera vez el 07-16 porque nunca antes un usuario había
respondido la raza con una palabra de sexo.
**Estado:** RESUELTO.

### ERR-060 — Menú de perfiles PEGADO inhibe la oferta de "agregar otro" (replay del chat real, 2026-07-14)
**Síntoma:** al reproducir el chat 4 real con el modelo real, tras "Potasio y sodio" (armado a
medida) el bot a veces saltaba directo a preguntar el pago en vez de ofrecer "¿agregás otro o
cerramos?". No-determinístico: otras corridas sí ofrecían.
**Causa raíz (bandera pegada, la clase que la Fase 3.2 detecta):** al pasar de "elegir un perfil
armado" (menú `_profile_menu_options`) a "armar a medida", el menú NO se limpiaba y sobrevivía al
turno siguiente. Con los análisis ya capturados, `_enforce_extra_analysis_offer` se abstenía por el
menú pegado (guarda contra menús a medio resolver), dejando la oferta a merced de lo que el modelo
decidiera generar → variabilidad. El estado quedaba incoherente: menú de elección + `selected_tests`
llenos coexistiendo.
**Solución (determinística, ataca la raíz):** en `_enforce_extra_analysis_offer`, si la orden YA
tiene análisis, se descartan los menús pegados (`_profile_menu_options`/`_test_menu_options`/
`_test_menu_adds_to_profile`) antes de evaluar la guarda — un menú de elección y análisis ya
seleccionados no pueden coexistir. Así la oferta sale siempre, sin depender del modelo.
**Tests:** `tests/test_extra_analysis_offer.py::test_stuck_profile_menu_does_not_block_extra_offer`
(lógica pura sobre el estado real, sin fingir el modelo). Suite: 267 passed. Verificado en vivo con
el replay del chat 4 (modelo real).
**Estado:** RESUELTO. Refuerza el valor del observador de la Fase 3.2 (detecta este tipo de bandera
pegada) y la lección [[L51]] (validar con el chat real, no con mocks).

### ERR-059 — Dos LÓGICAS de fallo (no frases): el flujo no sabía retroceder y corregir un dato reiniciaba todo (2026-07-11)

- **Origen:** corrección directa del usuario (→ L50 en lessons.md): "resolvé la lógica del fallo, no la palabra — ningún cliente repite el fraseo exacto". Análisis de los 2 chats que rompieron al agente.
- **LÓGICA 1 — retroceso de paso:** el flujo solo sabía avanzar; el "empuje" del paso actual (p. ej. re-preguntar el pago) pisaba cualquier pedido de volver atrás. **Fix:** `_enforce_payment_step` CEDE ante `user_intent_signal="correction"` (fuente primaria — cualquier fraseo que el modelo entienda como cambio/retroceso); el detector de tokens queda de red. Prompt reforzado: la definición de `correction` incluye "volver a un paso anterior mientras se pregunta otra cosa".
- **LÓGICA 2 — corrección puntual ≠ reinicio:** "cambiar el cliente" reiniciaba TODA la orden (re-preguntaba médico, paciente, especie... — el cliente repetía todo; ahí nació "el que ya te dije"). **Fix:** `_restart_identification_for_new_client` distingue por estado — orden EN CURSO → `_switch_client_keep_order` (motor unificado con el cambio de sede: conserva médico/paciente/análisis/pago/observaciones; re-verifica solo identidad y dirección); orden YA REGISTRADA (terminal) → reset como antes (pedido nuevo).
- **Sub-fallo detectado en el re-QA:** al re-identificar el cliente nuevo, el modelo re-capturaba del historial la dirección del cliente ANTERIOR (el resumen viejo está en el contexto) y el flujo la aceptaba sin confirmar → orden con dirección equivocada (logística real). **Fix de lógica:** `_address_written_by_user` — una dirección solo vale como "dada por el usuario" si la escribió en su mensaje (≥60% de sus tokens); si no coincide con la del cliente nuevo y no la escribió, se descarta y se confirma la registrada del nuevo.
- **Tests:** `test_qa_realista_guardrails` (+3: el empuje cede ante correction; cambiar cliente en curso conserva la orden; tras registrar sí resetea). Suite: **234 passed, 1 xfailed**. QA con modelo real usando FRASEOS NUEVOS (distintos a los chats) para validar que es la lógica y no la palabra.
- **Estado:** ✅ CORREGIDO (validación con fraseos nuevos en curso).


### ERR-058 — Prueba en vivo del usuario (chat 4, 2026-07-08): 3 fallos del "20% restante" (2026-07-08)

- **Severidad:** alto (uno de dinero/orden). Prueba en vivo real del usuario tras la Fase 3; el 80% funcionó (cabra→Caprino+Hembra, typo "potacio" resuelto, menú de orina ofrecido, cambio de cliente y corrección de dirección OK). Tres fallos concretos:
- **BUG-B (dinero) — menú de PERFILES pegado:** pidió "prueba de orina" (menú de análisis nuevo) → dijo "1" → registró **"152 Perfil Prequirúrgico I"** del menú de perfiles VIEJO (mostrado antes de "armar a medida"), pisando el perfil personalizado armado. Variante de perfiles del menú pegado (el de análisis se arregló en ERR-055). **Fix de raíz:** menús mutuamente excluyentes — `_store_test_menu_options` descarta `_profile_menu_options` y el nuevo helper `_store_profile_menu_options` (reemplaza 5 asignaciones directas dispersas) descarta el menú de análisis.
- **BUG-A — "antes de cerrar quiero agregar otro análisis" pisado por la pregunta de pago:** (mismo fallo del historial del "toro", seguía abierto). `_enforce_payment_step` re-preguntaba el pago ignorando la intención. **Fix:** si el mensaje pide agregar (`_wants_partial_analysis_change`) y aún no hay pago, se reabre el paso de agregado (`_awaiting_additional_test="add"` + `_offering_extra_analysis`) en vez de re-preguntar el pago.
- **BUG-C — "el que ya te dije" capturado LITERAL como médico** (`requesting_doctor="El Que Ya Te Dije"`; mismo patrón que ERR-030 con clinic_name). **Fix:** guard post-LLM `_reject_reference_phrases_as_names` — un valor NUEVO de campo de nombre (médico/paciente/dueño/clínica) que sea frase-referencia ("...dije", "el mismo", "el de siempre") se descarta y el pipeline re-pregunta; los nombres reales ("Sr Juan") pasan limpios.
- **Refinamiento adicional del resolvedor (detectado en el re-QA):** "necesito una PRUEBA de orina" ofrecía un menú absurdo (Prueba de Coombs...) porque "prueba" matcheaba nombres tipo "Prueba Cruzada de Coombs". Fix en `catalog.py`: el matching por nombre usa solo tokens de CONTENIDO (`_content_only`: sin fillers, sin sustantivos genéricos, sin palabras de área, sin verbos de pedido `_REQUEST_WORDS`) en AMBOS lados; y multi-pick con desempate real ("cuadro hematico sodio" → ambos tests; "una glucosa" → ambiguo entre las 3 glucosas). En el handler, resolve=NONE con mención de área → `_area_options_for_profile_addition(require_question=False)` ofrece el menú del área real.
- **Tests:** `test_qa_realista_guardrails` (+3: menús excluyentes en ambas direcciones, agregar-vs-pago, frases-referencia). Suite: **231 passed, 1 xfailed**.
- **Validación (modelo real, flujo EXACTO del usuario):** **4/4 OK** — "antes de cerrar quiero agregar" reabre el agregado; "prueba de orina" ofrece el menú de uroanálisis completo; el "1" elige 1507 del menú nuevo manteniendo intacto el perfil personalizado (1101/1404/1405); "el que ya te dije" no queda literal.
- **Estado:** ✅ CORREGIDO y validado con modelo real.


### FASE-3.4 (arranque) — Descomponer el monolito: patrón demostrado (2026-07-08)

- **Tipo:** refactor puro (mover código, no cambiar lógica). `agent.py` tiene ~5.600 líneas; se parte gradualmente en módulos cohesivos, con la suite (228) como oráculo en cada extracción.
- **Extraído:** `app/text.py` (utilidades de texto puras: `tokenize`, `money`, `catalog_item_key`, `strip_price_text`, `ACCENT_TRANSLATION`) y `app/species.py` (modelo de dominio de animales: `ANIMAL_DOMAIN` + `apply_implied_animal_fields`). `agent.py` las re-exporta con los nombres `_*`, así las cientos de referencias existentes no se tocan (cero cambio de comportamiento).
- **Patrón establecido:** capa base (`text`) → módulos de dominio (`species`, y ya antes `catalog`, `state`) que importan de la base. Sin dependencias circulares.
- **Verificación:** `import app.agent` OK; suite **228 passed, 1 xfailed** tras cada extracción.
- **Pendiente (gradual):** extraer los grupos grandes restantes (detectores de intención, enforcers, formateo de respuestas) módulo por módulo, cada uno con la suite verde. No urge y no bloquea; baja el riesgo del reorden del pipeline (3.3 completo) cuando se encare.
- **Estado:** ✅ patrón demostrado (text.py, species.py). Resto = trabajo incremental.

### FASE-3.3 (piloto) — Invertir el orden de decisión: confirmación de dirección por señal del LLM (2026-07-08)

- **Tipo:** primer paso del 3.3 (el que reduce la variabilidad de raíz). A diferencia de 3.1/3.2 (que solo formalizaron), aquí SÍ cambia CÓMO se decide — pero solo un detector, para validar el patrón con evidencia antes de extenderlo.
- **Qué:** la confirmación/rechazo de dirección deja de decidirse solo por listas de tokens. Nuevos `_confirms_address_now(ai_response, msg)` y `_rejects_address_now(...)` con `user_intent_signal` como FUENTE PRIMARIA (affirm→confirma; negate/correction/change_client→no) y los detectores de tokens (`_confirms_address`/`_rejects_address`) como FALLBACK. Molde idéntico a `_confirms_order_now` (cierre, ya probado). Migrados los 3 usos post-LLM en `process_turn`.
- **Valor:** una confirmación coloquial fuera de lista ("no hay drama, esa dirección está bien" — que los tokens RECHAZAN por el "no") ahora confirma; y un "sí" incidental NO confirma si la IA leyó negación/corrección. La señal manda; los tokens son red.
- **Seguridad:** si el modelo no llena la señal (o es `unclear`), cae al comportamiento por tokens de hoy → sin regresión. `tests/test_address_pending_reask.py` (+3, incl. señal vs tokens engañosos). Suite: **228 passed, 1 xfailed**. QA de flujos (cierre con confirmación) sin regresión.
- **Estado:** ✅ HECHO (piloto). Con esto validado, el patrón se puede extender detector por detector (otra orden, cambio de análisis, "el mismo", etc.) — cada uno reduce un poco más la variabilidad tokens-vs-LLM.

### FASE-3.2 — FSM explícita: fases tipadas y transiciones documentadas (2026-07-08)

- **Tipo:** refactor arquitectónico (NO cambia comportamiento). Segundo paso de la Fase 3.
- **Antes:** las fases eran strings mágicos (`"fase_4_confirmacion"`…) que el modelo proponía y los enforcers reescribían libremente; las constantes estaban dispersas (`CONFIRMATION_PHASE` en agent.py, `TERMINAL/DONE/ESCALATED_PHASES` en rules.py). Sin grafo de transiciones ni forma de detectar un salto incoherente.
- **Ahora (`app/state.py`):** enum `Phase` (hereda de `str` → compatible con todo el código), `TERMINAL/DONE/ESCALATED_PHASES` tipadas, `LEGAL_TRANSITIONS` (grafo del flujo real documentado), `is_legal_transition()` e `is_terminal()`. `agent.CONFIRMATION_PHASE` ahora deriva de `state.Phase.CONFIRMACION.value` (una sola fuente de verdad; string idéntico → cero riesgo de serialización). `rules.py` se deja intacto (convención: solo depende de config); un test verifica que el enum y las constantes de rules coinciden.
- **Modo:** formalización + DETECCIÓN (no se bloquea ninguna transición todavía, igual que 3.1 no impuso el estado). `is_legal_transition` queda disponible para el paso 3.3.
- **Verificación:** `tests/test_state.py` (+3: consistencia enum↔constantes, transiciones del flujo, is_terminal). Suite: **225 passed, 1 xfailed**. QA real de cierre de orden.
- **Estado:** ✅ HECHO. Con 3.1 (estado) da el cimiento tipado para 3.3 (invertir el orden de decisión: el LLM decide, el código valida) y 3.4 (partir el monolito).

### FASE-3.1 — Estado explícito de la conversación (refactor del "cómo", 2026-07-08)

- **Tipo:** refactor arquitectónico (NO cambia comportamiento). Primer paso de la Fase 3 del plan `~/.claude/plans/podemos-hacer-podemos-hacer-lively-waterfall.md`. Insight del usuario: el QUÉ (lo que el cliente ve) está bien; el CÓMO (estructura interna) es el problema y genera la variabilidad.
- **Antes:** el estado eran ~42 flags `_*` sueltas mezcladas con los datos de negocio en un dict libre, arrastradas a mano turno a turno (bucle inline en `process_turn`), sin schema ni invariantes.
- **Ahora:** nuevo `app/state.py::ConversationState` — envuelve el mismo dict (compat total con Supabase/ai.py), con: catálogo de flags agrupado por concepto (identificación/análisis/dirección/cierre) como fuente única de verdad; `carry_over()` que reemplaza el merge inline (equivalencia byte a byte probada); `assert_valid()` con invariantes (dirección no confirmada+pendiente, cliente no encontrado+no-encontrado, bloqueado no registra); `unknown_flags()` para detectar flags fantasma; helpers `clear_menus()`/`has_analysis`.
- **Integración:** en `process_turn` la copia manual de flags → `state.ConversationState(fields).carry_over(prev_captured)`. Nada más cambia; el resto del código sigue leyendo el dict.
- **Verificación:** `tests/test_state.py` (6, incluye equivalencia con el bucle viejo y que el catálogo cubre todas las flags usadas en `agent.py`). Suite: **222 passed, 1 xfailed**. QA real de confirmación end-to-end.
- **Estado:** ✅ HECHO. Cimiento para 3.2 (FSM), 3.3 (invertir orden de decisión), 3.4 (partir el monolito).


### ERR-057 — Interpretación inconsistente de especie/raza ("toro" a veces especie, a veces raza) — fix de CORE (2026-07-07)

- **Severidad:** medio (core del dominio). Del historial del "toro": "un toro" se interpretaba de 4 formas distintas entre corridas (especie "toro", raza "Toro", "Bovino"…). A3 atiende TODAS las especies (bovinos, porcinos, equinos, ovinos, caprinos, conejos, aves, etc.), no solo perros/gatos.
- **Causa raíz (no era un parche, era el core incompleto):** el modelo de dominio de animales estaba a medias y FRAGMENTADO en dos mapas: `_RECOVERABLE_SPECIES` tenía las especies canónicas pero sin las palabras coloquiales (faltaban toro/vaca/puerco/oveja/cabra/gallina…), e `_IMPLIED_ANIMAL_FIELDS` (especie+sexo) solo cubría perro/gato/caballo. Sin normalización determinística, el LLM improvisaba → inconsistencia.
- **Solución (fuente única de verdad):** un solo `_ANIMAL_DOMAIN` (`app/agent.py`) — palabra coloquial → (especie canónica, sexo implícito cuando es inequívoco: toro=Macho, vaca=Hembra; genéricos como perro/cerdo/caballo NO asumen sexo). `_RECOVERABLE_SPECIES` e `_IMPLIED_ANIMAL_FIELDS` se DERIVAN de él (sin duplicar). Cubre caninos, felinos, bovinos, porcinos, equinos, ovinos, caprinos, conejos, roedores, aves y reptiles con sus variantes. Prompt actualizado: A3 atiende todas las especies y "toro/vaca/cerdo" son ESPECIE+sexo, nunca la raza (la raza es Holstein, Angus, Brahman…).
- **Validación (modelo real):** QA de especies 5/5 (toro→Bovino+Macho, vaca→Bovino+Hembra, cerdo→Porcino, conejo→Conejo, oveja→Ovino+Hembra; ninguno quedó como raza). Tests: `tests/test_species_domain.py` (19). Suite: 216 passed, 1 xfailed.
- **Estado:** ✅ CORREGIDO de raíz. El modelo de dominio de animales es ahora completo y determinístico.


### ERR-056 — 'Análisis de sangre' ofrecía Coagulación / registraba 'Sangre Oculta'; 'prequirúrgico' entraba en bucle (2026-07-07)

- **Severidad:** medio (flujo; el dinero ya estaba blindado). Del historial real del "toro" (Animal PET).
- **BUG G — término de área vaga mal resuelto:** "Quiero hacer un análisis de sangre" → ofrecía opciones de **Coagulación** (PT/PTT), y `resolve_tests` daba un falso EXACT a **1704 Sangre Oculta** ("sangre" es el token inicial de ese nombre). **Fix (dos capas):** (1) `app/catalog.py`: un término cuyo contenido significativo es solo una palabra de ÁREA vaga (`_AREA_WORDS`: sangre/orina/heces/suero…) NO resuelve a un test — se deja para la ayuda de área dedicada. (2) `app/services/db.py::find_tests_by_area`: excluye muestras ultra-genéricas ('sangre','suero','plasma') del match por tipo de muestra (casi todo análisis es de sangre → no identifica un área). Resultado: "análisis de sangre" → `_enforce_generic_blood_analysis_help` ofrece **Hematología**.
- **BUG F — 'un prequirúrgico' durante el agregado → bucle:** confirmado resuelto (el handler ofrece los perfiles de la categoría, ERR-055).
- **BUG H — 'Un pre quirúrgico 1' registraba PT:** era consecuencia de que "análisis de sangre" abría mal el menú de coagulación; resuelto de raíz con BUG G.
- **Validación (modelo real):** QA del tramo del historial (Animal PET) **4/4 OK**: "análisis de sangre" ofrece hematología, no registra basura; "un prequirúrgico" ofrece perfiles; sin PT espurio.
- **Tests:** `test_catalog_module` (área vaga → NONE), suite 197 passed, 1 xfailed.
- **Estado:** ✅ CORREGIDO y validado con modelo real.


### ERR-055 — QA EXTREMO (nivel "toro") reveló 5 bugs de flujo/dinero (2026-07-07)

- **Severidad:** alto. Batería adversarial larga (multi-orden, correcciones tercas, cambio de sede, análisis inexistentes) contra `process_turn` + modelo real. 11/15 invariantes en la 1ª pasada.
- **BUG A — menú pegado:** un `_test_menu_options` no consumido (el cliente dijo "mejor no") quedaba activo; un dígito incidental posterior ("2 años" = edad) seleccionaba una opción vieja y agregaba un análisis NO pedido (PTT). **Fix:** (1) `_select_tests_from_menu` no toma un dígito como opción si va seguido de una unidad de magnitud (`_MAGNITUDE_UNITS`: años/meses/kilos…); (2) en `process_turn` se descarta el menú si el mensaje es largo (>6 tokens) o abre otra orden.
- **BUG E — precio con fuzzy:** `_catalog_price_answer` usaba el matcher viejo → "glucosa en ayunas, ¿cuánto es el total?" arrastraba "Colesterol Total (Ayunas)". **Fix:** migrado a `catalog.resolve_tests(collect_partial=True)` (cotiza lo nombrado e ignora el ruido de la pregunta) + **desempate por cobertura** en `_resolve_one` ("glucosa EN AYUNAS" → Glucosa (Ayunas), no las otras glucosas).
- **BUG F — perfil por categoría durante el agregado:** "un prequirúrgico" repetido caía en bucle "¿qué análisis?". **Fix:** `_handle_extra_analysis_answer` ofrece los perfiles de la categoría (`_category_profiles_menu_response`) antes de tratarlo como análisis suelto.
- **BUG C — quitar+poner ('sacá eso y ponme una glucosa'):** se ignoraba. **Fix:** detectar reemplazo (remove + `_ADD_ANALYSIS_TOKENS` + análisis concreto) → limpia lo suelto y agrega el nuevo.
- **BUG D — cambio de sede mal interpretado** ("esta orden es para la otra sede" → registró Perfil Felino IV espurio): causa = el MODELO alucinó la selección (ni `_profile_codes_from_text` ni `_wants_to_change_client` la detectaban), inducido por un menú de perfiles felinos pegado en el contexto y por no reconocer "otra sede" como cambio de cliente. **Fix:** `_wants_to_change_client` ahora incluye los sustantivos de sede (`_BRANCH_NOUN_TOKENS`: sede/sucursal/local) + señal de cambio → "esta orden es para la otra sede" se maneja como cambio de cliente determinísticamente, antes de que el modelo alucine. Verificado que no rompe "confirmo los datos del cliente" ni "la sede del norte está bien".
- **Tests:** `test_client_match_selection` (menú/edad), `test_qa_realista_guardrails` (glucosa ambigua), resolvedor con desempate. Suite: 196 passed, 1 xfailed.
- **Métricas QA extremo (modelo real):** 11/15 → 12/15 → (final con A/C/E/F/D). Falsos negativos corregidos: X1-e (resumen antes de cerrar = correcto), X3-b (la cotización era correcta).
- **Mejora BUG D (cambio de sede sin perder la orden):** el interceptor distingue cambio de SEDE (misma orden) de cambio de CLIENTE. Nueva `_switch_branch_keep_order`: ante "esta orden es para la otra sede" descarta solo identificación + dirección y re-verifica la sede, MANTENIENDO paciente, análisis, médico, pago y observaciones (antes reiniciaba todo). Test: `test_client_match_selection::test_branch_switch_keeps_patient_and_analysis`.
- **Estado:** A/C/D/E/F ✅ corregidos y en verde (196 passed, 1 xfailed). Pendiente menor: cotizar (`_catalog_price_answer`) no estructura la selección — el precio es correcto pero el cliente re-confirma (variante QA-6, no dinero).


### ERR-054 — QA con modelo real reveló 3 bugs de flujo (selección de sede, captura en bloque, glucosa $0) (2026-07-07)

- **Severidad:** alto (identificación y dinero). Detectados con batería QA adversarial contra `process_turn` + OpenAI real + Supabase real (no mocks).
- **Bug #1 — selección de sede por nombre con relleno:** con 2 sedes del mismo NIT, "la de quinta paredes" NO seleccionaba (el substring del texto COMPLETO `la_de_quinta_paredes` no estaba en el nombre) → bucle de identificación. "quinta paredes" sí funcionaba. **Fix:** `_select_client_match` puntúa por PALABRAS distintivas compartidas (tokens ≥4) y elige la de mayor coincidencia única; empate por palabra común no elige. Tests: `test_client_match_selection::test_selection_by_distinctive_word_with_filler` y `::..._common_to_both_stays_ambiguous`.
- **Bug #2 — bloque de datos del paciente ignorado:** con dirección pendiente de confirmar, un bloque de 6+ datos del paciente hacía que el bot re-preguntara la dirección ya conocida (perdía el turno). La guarda `progressed` solo miraba turnos anteriores. **Fix:** contar también un BLOQUE de 3+ campos nuevos del paciente en el turno actual como avance (confirma la dirección por progresión). Exige 3+ campos para no regresar ERR-046 (un solo dato no confirma).
- **Bug #3 — análisis genérico ambiguo → $0:** "una glucosa" (varias variantes reales: Ayunas/Pre y Pos/Insulina) quedaba como texto suelto con precio $0. **Fix:** `_enforce_loose_exam_catalog_resolution`, ante `resolve_tests`=AMBIGUOUS, OFRECE las opciones (`_test_options_response`) en vez de dejar texto con $0. Test: `test_qa_realista_guardrails::test_loose_exam_ambiguous_offers_options_instead_of_zero_price`.
- **Validación:** re-QA con modelo real **10/10 invariantes OK** (identificación, sin análisis basura, precios del catálogo, cierre informal, bloque de datos). Suite: 196 passed, 1 xfailed.
- **Estado:** ✅ CORREGIDO y validado con modelo real. Pendiente: batería QA EXTREMA (multi-orden/correcciones/cambio de sede) en curso.


### ERR-053 — El bot agregaba análisis que el cliente NUNCA pidió (match por subcadena) (2026-07-07)

- **Severidad:** crítico (dinero/orden incorrecta)
- **Flujo:** perfil (agregar análisis a un perfil elegido)
- **Síntoma observado:** en prueba real (chat=1) el cliente elige "Perfil Prequirúrgico II" y luego, al intentar agregar análisis sueltos, el bot pegaba tests basura: "Quiero agregar otro análisis" → `1201-PT`, "Análisis sanguíneos" → `1408-Gases sanguíneos Plus`, "Parasitologico 3" → `1501-T3 Total`. `selected_tests` quedó `[1201, 1408, 1501]`.
- **Reproducción mínima:** `db.get_tests_by_codes_or_names(_named_analysis_terms("Parasitologico 3"))` devolvía `T3 Total` porque el término `"3"` estaba contenido en `"t3 total"`.
- **Causa raíz:** dos piezas combinadas. (1) `get_tests_by_codes_or_names` (`db.py`) matcheaba con `lookup in name_key` — **subcadena** — así que un fragmento cortito caía dentro de cualquier nombre que lo contuviera. (2) `_named_analysis_terms` (`agent.py`) admitía **dígitos sueltos** (`t.isdigit()`) y verbos/muletillas de ≥4 letras ("quiero", "agregar", "otro"). El match del mensaje completo daba `[]`; era el fallback por términos sueltos el que inventaba el test y lo agregaba en silencio.
- **Solución aplicada:** (1) `db.py`: nuevo `_tokens_contained()` — el término debe aparecer como secuencia contigua de **palabras completas** dentro del nombre (límite de palabra), no subcadena arbitraria. (2) `agent.py`: `_named_analysis_terms` descarta dígitos de <3 cifras (los códigos tienen ≥3) y verbos de acción vía `_ACTION_STOPWORDS`.
- **Archivos afectados:** `app/services/db.py`, `app/agent.py`.
- **Tests:** suite de perfiles/análisis en verde (79 tests: `test_category_profile_menu`, `test_profile_addition_invariant`, `test_add_analysis_during_adjustment`, `test_analysis_options_restore`, `test_profile_price_resolution`, `test_extra_analysis_offer`, `test_price_answers`, `test_qa_realista_guardrails`). Pendiente: agregar regresión dedicada de los 3 casos.
- **Validación manual:** reproducción contra BD real: "Parasitologico 3" → `[]`, "Quiero agregar otro análisis" → `[]`, "hemograma"/"cuadro hematico"/"1201"/"PT" siguen resolviendo bien.
- **Residual conocido (primer parche):** "Análisis sanguíneos" todavía resolvía a `Gases sanguíneos Plus` porque `"sanguineos"` es una palabra COMPLETA del nombre. Era un match por token, no el bug de subcadena. → cerrado abajo con la corrección de fondo.
- **Corrección de FONDO (2026-07-07, refactor eje catálogo Fase 1):** en vez de seguir endureciendo el matcher de bajo nivel, se atacó la causa raíz del cluster (~20 parches): la resolución texto→código se centralizó en un módulo puro **`app/catalog.py::resolve_tests`** que solo AGREGA con match inequívoco (código exacto, nombre canónico completo, o token inicial/≥50% de cobertura del nombre). Un término genérico o de área ("sanguíneos", "orina") devuelve `AMBIGUOUS` → el flujo ofrece opciones (menú que SUMA al perfil) en vez de adivinar un test suelto. Integrado en `_handle_extra_analysis_answer` (el punto donde el usuario reprodujo el bug en vivo). Principio: ante la duda, ofrecer — nunca adivinar (regla de dinero, L48).
- **Red de seguridad (Fase 0, previa al refactor):** `tests/test_catalog_resolution.py` (ejercita la resolución REAL con catálogo inyectado en `db._client`) + `tests/test_money_invariants.py` (invariantes I1 códigos válidos / I2 sin precio inventado / I4 total por códigos, end-to-end sobre `process_turn`).
- **Guardrails migrados a `resolve_tests` (Fase 1.4a):** `_enforce_loose_exam_catalog_resolution` y `_enforce_multiple_tests_capture` dejaron su matching propio (loops de `get_tests_by_codes_or_names`) y ahora delegan en el resolvedor unívoco. Unifica la resolución texto→código en un solo lugar y elimina la duplicación que causaba variantes del bug por rutas distintas.
- **Validador I1 (red dura, Fase 1.2):** nuevo `_enforce_selected_tests_are_catalog_codes`, corre JUSTO antes de registrar: descarta cualquier `selected_tests` que no sea un código real del catálogo (fail-safe si no hay catálogo). Garantiza que ninguna orden se cree con un análisis fantasma ni payload en $0, pase lo que pase en los guardrails previos. Test: `test_money_invariants::test_invalid_code_from_model_is_dropped_before_registering`.
- **Tests nuevos:** `tests/test_catalog_module.py` (9, resolvedor puro), `test_extra_analysis_offer::test_generic_area_term_offers_options_instead_of_autoadding` y `::test_named_exact_test_still_adds_via_resolver`, `test_money_invariants` (3). Suite: **192 passed, 1 xfailed**.
- **Estado:** ✅ CORREGIDO de raíz. El eje catálogo/dinero (cluster de ~20 parches) queda centralizado en `app/catalog.py`. Deuda documentada (xfail estricto): retirar del todo la función laxa `get_tests_by_codes_or_names` de bajo nivel cuando se migren sus últimos call-sites (precios/remove). Pendiente sin empezar: Fase 2 (intención por IA, Etapas 2-4 de ERR-011) y Fase 3 (FSM explícita).

### RESUELTO-026 — "Animal Pet es la clínica..." se extraía como "Con La Que Trabajo" (2026-07-03)

- **Síntoma:** En Chatwoot `chat=1`, el usuario respondió `animal Pet es la clínica con la que trabajo` y el bot contestó `No encuentro ningún cliente registrado con ese dato. ¿Eres cliente nuevo?`.
- **Reproducción mínima:** `_extract_clinic_name_candidate("animal Pet es la clinica con la que trabajo")` devolvía el tramo descriptivo en vez de `animal Pet`.
- **Causa raíz:** `_extract_clinic_name_candidate` cubría frases del tipo `clínica ... es X`, pero no el orden inverso `X es la clínica...`. En la sesión quedó persistido `clinic_name="Con La Que Trabajo"`; la búsqueda falló correctamente porque ese cliente no existe. La BD sí tiene `Animal Pets` activo y `Animal Pet` singular está inactivo.
- **Solución (`app/agent.py`):** agregar extracción para el patrón inverso `X es la clínica/veterinaria...` antes de los marcadores existentes, con filtro para no aceptar pronombres como nombre.
- **Tests:** `tests/test_db_identification.py::test_extract_clinic_name_from_reverse_marker_phrase`.
- **Validación manual:** `db.identify_client(name="animal Pet")` encuentra `Animal Pets` activo; `check_supabase_state.py` OK.
- **Estado:** ✅ CORREGIDO.

### RESUELTO-025 — Sesión con cliente identificado saltaba al médico solicitante sin pedir NIT (2026-06-24)

- **Síntoma:** Cliente dice "necesito analizar unas muestras". El bot responde "¿Cuál es el médico solicitante?" sin haber preguntado NIT ni confirmado datos del cliente.
- **Causa raíz:** La condición de multiorden (línea 4321 en `agent.py`) exigía `intent_current == "route_scheduling"`. Cuando la sesión tenía `client_id` pero `intent_current` era otro valor (ej. estado inconsistente entre pruebas), la condición fallaba. El pipeline normal del AI tomaba el turno: el AI veía al cliente identificado + dirección confirmada + `requesting_doctor` vacío → preguntaba el médico directamente sin mostrar el resumen de datos previos.
- **Contexto:** Confirmado en conversación del 2026-06-24 con chat_id "4". La sesión tenía `client_id=a88408fe...`, `pickup_address="DG 51A SUR 61B-03"`, `_order_registered=True`, pero `intent_current` en estado parcial.
- **Solución:** Ampliar el trigger de multiorden para que se active también cuando `session.get("client_id")` está establecido (no solo cuando `intent_current == "route_scheduling"`). Se añade además la guarda `not prev_captured.get("_stable_confirm_pending")` para no re-disparar durante el paso de confirmación de datos estables. Ver `app/agent.py` línea ~4324.
- **Tests:** Verificar con sesión que tenga `client_id` + `_order_registered=True` + `intent_current != "route_scheduling"`: el bot debe mostrar el resumen de la orden anterior, no preguntar el médico directamente.
- **Estado:** RESUELTO 2026-06-24

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
- Progreso (2026-07-07): migrado el CIERRE de orden (`_confirms_order_now` en `_enforce_confirmation_step`) a `user_intent_signal=affirm` como fuente primaria, con salvaguardas (no cierra si la IA leyó correccion/negacion/cambio/otra orden/cancelar). Cierra confirmaciones fuera de lista ("me sirve así, avancemos"). Test: `test_profile_price_resolution::test_confirmation_closes_on_affirm_signal_outside_token_list`.
- **Hallazgo arquitectonico clave (por qué el plan previo se estancó):** el grueso de los detectores de Etapa 2/3 vive en la cascada PRE-LLM de `process_turn` (~40 `if token: return` ANTES de llamar al modelo), donde `user_intent_signal` todavía NO existe. Solo los detectores POST-LLM (como el cierre) pueden usar la señal limpiamente. Completar Etapa 2-4 requiere PRIMERO reordenar el pipeline para que el LLM corra antes de los atajos de token — eso ES la Fase 3 (FSM/reorden). Etapa 2 y Fase 3 están acopladas; NO son independientes como asumía el plan previo.
- Estado: en progreso (cierre migrado; el resto depende del reorden del pipeline — Fase 3). Requiere validacion en vivo con modelo real de que la señal se llena bien antes de seguir.

---

## Correcciones aplicadas

### ERR-052 — El descuento por volumen no se mostraba: el total parecía un cálculo mal hecho
- Severidad: medio (confianza: el cliente cree que el bot calcula mal; el número era correcto)
- Flujo: resumen de la orden / registro de análisis del menú
- Síntoma observado (prueba real del usuario, chat 1, 2026-07-06): eligió 2 análisis ($14.000 + $8.000) y el bot mostró "Valor estimado: $19,360 COP" sin explicación. $22.000 − 12% de descuento por volumen (DISCOUNT_TIERS de config.py, 2 análisis → 12%…15+ → 27%) = $19.360 — matemática correcta, pero ni el mensaje de registro ni el resumen mencionaban el descuento. El usuario pensó que el cálculo estaba mal (se repitió en cada orden con 2+ análisis sueltos; las respuestas de PRECIO sí desglosaban vía `_format_tests_total`).
- Causa raíz: tres puntos mostraban solo el total (`_capture_test_menu_selection`, `_enforce_multiple_tests_capture`, `_order_summary_lines` rama selected_tests) sin el desglose que la respuesta de precios ya tenía.
- Solución aplicada: helper único `_estimated_total_text(totals)` — con descuento, SIEMPRE "Subtotal $X, descuento por volumen -$Y → valor estimado $Z"; el resumen agrega las líneas "- Subtotal:" y "- Descuento por volumen:" antes del valor estimado. Sin descuento, el texto queda simple.
- Archivos afectados: `app/agent.py` (4 cambios), `tests/test_qa_realista_guardrails.py` (3 tests nuevos).
- Tests: suite 195 passed (4 fallos preexistentes de test_dashboard).
- Nota: `calculate_profile_adjusted_total` (perfil base + agregados) NO aplica descuento — esa rama no necesita desglose. Verificar con el negocio que los tramos de `DISCOUNT_TIERS` (12%–27%, comentario "Sección 5 del spec") sean los vigentes del cliente.
- Estado: corregido (pendiente re-prueba del usuario).

### ERR-051 — QA adversarial contra BD real: precios inventados, análisis no pedidos y capturas de texto libre sin catálogo
- Severidad: crítico (dinero: órdenes reales con precio inventado, perfil no pedido de $130.000 y payloads con precio 0)
- Flujo: captura de análisis / precios / confirmación de dirección / edad
- Síntoma observado (batería QA adversarial 2026-07-05: 10 personas-IA contra `process_turn` + Supabase REAL, doble revisión juez-IA + manual):
  1. QA-1: "un coprologico" → orden registrada con "Coprológico **$23k**" (precio real: $12.000, código 1701). El modelo escribió el precio en exam_type y nada lo validó.
  2. QA-7: TODOS los payloads de análisis suelto quedaron `code: null, price: 0, total_estimated: 0` — dashboard y facturación leerían $0.
  3. QA-5: el bot nunca preguntó el análisis, saltó al pago y registró "**Perfil Senior Canino V — $130.000**" que el cliente jamás nombró (pidió "prequirúrgico con parcial de orina"); el cliente confirmó sin notarlo.
  4. QA-5b: "¿cuánto queda el total con el parcial de orina incluido?" → cotizó "PTT (Tiempo **parcial** de Tromboplastina) + Cortisol en **Orina**" (fuzzy multi-término en `_catalog_price_answer`, ruta no cubierta por ERR-050).
  5. QA-6: "quiero cuadro hemático y creatinina juntos, ¿cuánto sale el total?" → respondió el precio correcto pero PERDIÓ la elección y re-preguntó qué análisis desean.
  6. QA-2: "si, correcta. necesito coprologico para luna... y contraentrega" (confirmación + datos en bloque) → "¿Cuál es la dirección de retiro?" pisando TODO el turno. Causa real (reproducida determinísticamente): el atajo de "forma de pago fuera de turno" intercepta ANTES del bloque de confirmación de dirección; con `_address_confirmation_pending=True` la dirección cuenta como faltante y el atajo la re-pregunta descartando la captura y el pago.
  7. QA-3: edad "2" sin unidad → el modelo registró "2 años" inventando la unidad (regla #10 pide repreguntar).
- Causa raíz (la misma clase que ERR-050, en rutas no cubiertas): el análisis suelto capturado como TEXTO LIBRE nunca se resolvía contra el catálogo; los precios podían salir del texto del modelo; y dos atajos deterministas (price answer, pago fuera de turno) interceptaban turnos compuestos pisando lo capturado.
- Solución aplicada (6 fixes, mismo principio: catálogo/estructura como única fuente):
  - A. `_enforce_loose_exam_catalog_resolution` + `_strip_price_text`: exam_type suelto NUEVO se resuelve contra el catálogo (selected_tests con código; exam_type = "código nombre"); cualquier cifra escrita por el modelo se descarta; sin match único queda el texto limpio sin precio.
  - B. `_enforce_exam_type_grounding`: un exam_type NUEVO debe tener anclaje textual en lo que el cliente dijo (mensaje actual o turnos recientes); si no, se descarta y se pregunta el análisis. Excluye menús mostrados, snapshot multiorden, "el mismo", etiquetas y perfiles/estructura previa.
  - C. `_catalog_price_answer`: mensaje completo primero; mención de ÁREA → lista las opciones reales de esa área con precios (y guarda el menú marcado para AGREGAR si hay orden en curso); términos sueltos solo como último fallback.
  - D. `_expresses_order_request`: pedido + consulta de precio en el mismo mensaje NO se responde como side-question; el pipeline captura la selección ("quiero saber cuánto…" sigue siendo consulta).
  - E. Atajo de pago fuera de turno: resuelve la confirmación de dirección del mismo mensaje ANTES de decidir qué falta, y NO pisa la respuesta si el turno trajo datos nuevos en bloque.
  - F. `_enforce_age_unit_grounding`: si la unidad de la edad no vino del cliente, se guarda solo el número y la regla existente re-pregunta con ejemplos.
- Ajustes tras el PRIMER re-test adversarial (mismo día):
  - El invariante de ERR-050 duplicaba los análisis INCLUIDOS del perfil como agregados cuando el modelo re-escribía exam_type con la descripción ("Perfil Parasitológico II: Coprológico y Coproscópico" → $23.000 pasó a $50.000 entre confirmación y cierre). Fix: los ítems presentes en `_selected_profile_description` nunca se suman.
  - exam_type = CATEGORÍA de perfiles ("PREQUIRURGICO", capturado del historial) llegaba al resumen sin precio (payload $0). Fix: la resolución de análisis suelto ofrece el menú de perfiles armados de la categoría (`_category_profiles_menu_response`) — una categoría nunca pasa al resumen como análisis.
  - "los dos juntos, confírmame el total" no se detectaba como pedido → tokens `confirmame/confirmás/confirma` agregados (con exclusión de "¿me confirmas el precio?").
  - La edad sin unidad capturada del HISTORIAL también se detecta (el grounding revisa los turnos recientes del usuario, no solo el mensaje actual).
- Ajustes tras el SEGUNDO re-test: "buen día" contaba como unidad de edad ("dia" quitado del set; la edad en días se dice en plural); exam_type con VARIOS análisis como texto ("Cuadro Hemático Completo, Creatinina" → payload $0) ahora se estructura si cada ítem resuelve 1:1.
- Archivos afectados: `app/agent.py` (11 cambios), `tests/test_qa_realista_guardrails.py` (20 tests nuevos, incluye el turno QA-2 completo end-to-end), runner QA adversarial en scratchpad (BD real, spies de create_request, Alegra off, limpieza selectiva).
- Tests: suite 192 passed (4 fallos preexistentes de test_dashboard).
- Verificación adversarial final (BD real, modelo real): caotico_typos BIEN (resumen y cierre "1701 Coprológico / $12,000 COP" reales y consistentes; payload total 12000); perfil_agregado registró el Perfil Prequirúrgico IV $36.000 REAL que sí incluye Parcial de Orina (payload perfecto) — el FAIL del juez es de COMUNICACIÓN (no explicitó que el parcial venía incluido), no de dinero; precios BIEN (cotiza, captura y cierra).
- Residuo conocido (ABIERTO menor, comunicación/pulido): ante un pedido complejo ("el más completo que incluya parcial de orina"), el menú intermedio puede salir de un área equivocada y el bot no explicita qué incluye el perfil elegido. Sin impacto en dinero ni en datos.
- Datos del QA: todo lo generado se limpió en cada corrida (requests + eventos, sesiones, mensajes; verificado 0 residuos); `create_pending_client_review` bloqueada durante el QA (0 intentos de insertar clientes reales).
- Estado: corregido (pendiente re-prueba del usuario por Telegram).

### ERR-050 — Agregar un análisis a un perfil ya elegido: ruteo roto y el agregado se perdía del total
- Severidad: crítico (el resumen y el total de la orden perdían plata en silencio: $24.000 en vez de $40.000)
- Flujo: perfil / personalización (agregar análisis a un perfil base)
- Síntoma observado (prueba real del usuario, chat 4, 2026-07-04 12:25–12:31, con perfil 152 elegido):
  1. "quiero agregarle un analisis mas a este perfil" → menú de perfiles recomendados por especie (Perfiles Cachorros para una perra de 7 años) en vez de preguntar cuál agregar.
  2. "quiero el perfil 152 y agregarle un analisis mas a este si ?" → el MISMO menú, textual.
  3. "quiero agregarle un analisis de orina al perfil" → "Listo, agrego 1507-Cortisol en Orina $33k": fuzzy-match de "orina" a un test suelto, sin confirmar.
  4. "que analisis de orina hacen?" → muestrario mixto de todas las áreas que además BORRABA selected_tests y exam_type (el Cortisol desapareció en silencio).
  5. "el parcial de orina esta bien!" se leyó como "está bien, sigamos" (frase de proceder al pago) y el análisis nunca se agregó; el modelo lo anotó después como TEXTO en exam_type ("Perfil Prequirúrgico I + Parcial de Orina $16k") pero selected_tests quedó vacío → resumen final "Perfil Prequirúrgico I — $24,000 / Valor estimado: $24,000". Además, tras capturar el pago re-preguntó el perfil (paso atrás) porque exam_type había quedado en None con el perfil base activo.
- Causa raíz (dos capas):
  1. RUTEO: los guardrails de recomendación tenían precedencia sobre la intención de AGREGAR — en `_handle_extra_analysis_answer`, la condición `"perfil" + "mas"` disparaba la lista por especie; la mención de un área en afirmativo no llegaba a `_area_options_for_profile_addition` (gate de pregunta) y caía al fuzzy de `get_tests_by_codes_or_names` ("orina" ⊂ "Cortisol en Orina"); `_is_catalog_overview_question` corría antes que todo y `_test_options_response` limpiaba la orden en curso.
  2. ESTADO: el agregado no tenía fuente única — podía vivir como texto en exam_type (LLM), en selected_tests (estructura) o solo implícito en `_selected_profile_*`; el resumen y el payload (db.py:1120 arma added_tests desde selected_tests) solo leen la estructura, así que todo lo anotado como texto se perdía. Los fixes por detección de frase (RESUELTO-014) no cubrían estas variantes.
- Solución aplicada (invariante + ruteo, no parches por frase):
  - INVARIANTE `_enforce_profile_exam_type_integrity` (pipeline post-AI): con perfil base, exam_type es EXACTAMENTE el nombre del perfil; los agregados anotados como texto se resuelven contra el catálogo y se suman a selected_tests; exam_type vacío con perfil activo se restaura (mata el paso atrás post-pago). Resumen/total salen SIEMPRE de la estructura.
  - RUTEO con perfil elegido: (a) intención de agregar → `_selected_profile_addition_response` (nunca el menú de recomendación; nuevo paso 2b en `_handle_extra_analysis_answer`, respeta un código de perfil nombrado y excluye los pedidos de QUITAR); (b) mención de área en afirmativo → menú del área marcado para AGREGAR (`_area_options_for_profile_addition(require_question=False)`, también en `_confirmation_analysis_adjustment`); (c) pregunta de catálogo con análisis en curso → menú del área (o muestrario) marcado para AGREGAR, sin tocar la orden; (d) lookup por nombre: mensaje completo primero, términos sueltos solo como fallback; (e) selección de menú tolera palabras alrededor (matching del nombre sin paréntesis, mínimo 5 caracteres) — "el parcial de orina esta bien!" selecciona en vez de leerse como "proceder al pago"; (f) `_capture_test_menu_selection` (reemplazo total) limpia el perfil base viejo.
  - Menor: concordancia de género en "el mismo" (`_FIELD_GRAMMAR`: "la dirección de retiro es la misma", "¿Cuál es el médico solicitante?") + R19 alineada en el prompt.
- Archivos afectados: `app/agent.py` (9 cambios), `app/prompt.py` (R19), `tests/test_profile_addition_invariant.py` (11 tests nuevos), caso X en `tools/scripts/validate_flows.py`.
- Tests: suite 172 passed (los 4 fallos de test_dashboard/exec_alerts_count son preexistentes). Modelo real (`ALEGRA_ENABLED=false`): caso X OK end-to-end — "agregarle un análisis más" pregunta cuál, "análisis de orina" da el menú del área, la selección suma estructurada y el resumen cierra con "Agregados: 1603-Urocultivo $52k / Valor estimado: $76,000 COP". Vecinos A/G/H/Q/R/U/W OK.
- Nota: el caso V (ERR-046) es flaky por no-determinismo del modelo (misma corrida alterna OK/PROBLEMAS con código idéntico; depende de si el modelo captura el análisis en el turno esquivo). No es regresión de este fix.
- Estado: corregido (pendiente re-prueba del usuario por Telegram).

### ERR-048 — "Tienes perfiles pre quirúrgico?" (con espacio) respondía "Perfecto, lo anoto" y re-preguntaba el análisis
- Severidad: alto (mismo síntoma reportado en ERR-045; el fix de ERR-045 no cubría esta variante)
- Flujo: catálogo / pregunta por perfiles de una categoría
- Síntoma observado (prueba real del usuario, chat 4, 2026-07-03 18:02, tras el reset): el bot preguntó el análisis y el cliente respondió "Tienes perfiles pre quirúrgico?"; el bot contestó "Perfecto, lo anoto. Por último, ¿qué análisis o perfil desean?" — no mostró nada y repitió la pregunta.
- Causa raíz (dos fallas encadenadas):
  1. `db.find_diagnostic_label` no matchea "pre quirúrgico" SEPARADO (solo "prequirurgico" junto), y la frase no trae tokens de recomendación ni "armados": ninguna entrada al menú por categoría de ERR-045 se disparó. El flujo cayó a `_enforce_analysis_help_fallback`, que armó el menú genérico por especie (Cachorros).
  2. `_enforce_first_missing_after_progress` pisó esa respuesta con la plantilla "Perfecto, lo anoto. + dato faltante": protege `_test_menu_options` pero NO `_profile_menu_options`. (Este guard es también el culpable del turno "Pre quirúrgicos te pedí" → "lo anoto" del reporte original de ERR-045.)
- Solución aplicada:
  1. En `_enforce_diagnostic_label_help`, el intento de perfiles armados por categoría corre con `label or candidate`: si la etiqueta no resuelve, el matcher de categoría (normaliza tildes Y espacios) igual reconoce "pre quirúrgico" en el texto crudo.
  2. `_enforce_first_missing_after_progress` ya no pisa una respuesta con `_profile_menu_options` recién ofrecido (el menú ES la pregunta del análisis).
- Archivos afectados: `app/agent.py` (2 cambios puntuales), `tests/test_category_profile_menu.py` (2 tests nuevos), caso W en `tools/scripts/validate_flows.py`.
- Tests: suite 124 passed. Modelo real: caso W (la frase exacta de la prueba fallida, "Tienes perfiles pre quirúrgico?") → OK end-to-end: menú de armados, "el 1" registra 701 con precio, orden cerrada.
- Nota operativa: el Flask local corría el código previo al fix; se reinició (y se relevantó ngrok, que estaba caído) para que la prueba real use esta versión.
- Estado: corregido (pendiente re-prueba del usuario).

### ERR-046 — Respuesta esquiva daba por confirmada la dirección pendiente en silencio
- Severidad: alto (una confirmación de negocio se asumía sin que el cliente la diera)
- Flujo: confirmación de dirección de retiro
- Síntoma observado (validate_flows con modelo real, flujo H, 2026-07-03; señalado por el usuario): con "¿Es correcta la dirección?" pendiente, el cliente respondió "quiero un análisis de orina" y el bot dio la dirección por confirmada en silencio y siguió con "¿Cuál es el médico solicitante?"; la confirmación se perdía.
- Causa raíz: el guardrail de progreso (`agent.py`, bloque `_address_confirmation_pending`) contaba los datos capturados en ESE MISMO turno como "el flujo ya avanzó" y bajaba el flag. La regla existía para sesiones legacy con el flag pegado, pero tragaba la pregunta recién hecha.
- Solución aplicada (criterio del usuario: responder a lo que dijo, conservar el dato, pero SIEMPRE re-preguntar lo pendiente):
  1. "Ya avanzó" solo cuenta datos de turnos ANTERIORES (`prev_captured`), no del turno actual.
  2. Si en el mensaje da OTRA dirección, esa vale como corrección confirmada.
  3. Si responde otra cosa: lo capturado se conserva, el pipeline responde al mensaje (menú/dato/precio) y AL FINAL del turno se re-pregunta la dirección (inyección después de la cadena de guardrails, para que un menú no la pise; una versión previa inyectada antes de la cadena era sobrescrita por `_enforce_diagnostic_label_help`).
- Archivos afectados: `app/agent.py` (bloque de dirección pendiente + inyección final), `tests/test_address_pending_reask.py` (nuevo), caso V en `tools/scripts/validate_flows.py`.
- Tests: 4 nuevos (re-pregunta conservando el dato, confirmación normal, dirección nueva como corrección, auto-confirmación legacy multi-turno intacta); suite 122 passed. Modelo real: caso V OK (menú de uroanálisis + re-pregunta de dirección en el mismo mensaje, dirección confirmada después) y A/G/H/Q/R/U OK.
- Estado: corregido.

### ERR-047 — "sí, esa está bien" no seleccionaba la coincidencia única de cliente (ex ABIERTO-004)
- Severidad: medio (la identificación se descarrilaba y terminaba escalando a un cliente registrado)
- Flujo: identificación de cliente (selección de coincidencias)
- Síntoma observado (validate_flows con modelo real, flujos G/H, 2026-07-03): ante la lista de coincidencia ÚNICA ("¿Es esta? Responde con el número 1, o dime si no es ninguna."), "sí, esa está bien" no seleccionaba; el bot re-pedía el nombre exacto y terminaba en cliente nuevo/escalado. Flaky (Q/R con turnos idénticos sí identificaban): dependía de la interpretación del modelo. Preexistente — verificado con git stash.
- Causa raíz: `_select_client_match` solo resolvía número, ordinal o nombre; la afirmación simple con UNA opción no tenía camino determinista.
- Solución aplicada: con exactamente 1 opción listada, una afirmación selecciona esa opción. Fuente primaria: la lectura semántica de la IA (`user_intent_signal == "affirm"`); fallback: tokens afirmativos. No aplica si el mensaje dice ser cliente nuevo/no registrado (eso mantiene el camino de escalado).
- Archivos afectados: `app/agent.py` (`_select_client_match` + señal en los 2 call sites), `tests/test_client_match_selection.py` (4 tests nuevos + parches de db para las rutas sin selección).
- Tests: afirmación con 1 opción selecciona (tokens y señal semántica sin tokens exactos), con 2 opciones NO selecciona (ambiguo), "somos cliente nuevo" no se toma como selección. Modelo real: G y H pasaron a identificar correctamente.
- Estado: corregido.

### ERR-045 — Pedir un perfil por categoría (prequirúrgico) ignoraba los perfiles armados del catálogo
- Severidad: alto (la orden llegó al resumen con un análisis inexistente en el catálogo, sin análisis concretos ni valor)
- Flujo: catálogo / recomendación de perfiles / etiqueta diagnóstica
- Síntoma observado (chat 4 Chatwoot, 2026-07-03 16:18–16:43, Pet Agro Colombia): (1) ante "¿Cuál me recomiendas pre quirúrgico, qué perfil tienen?" el bot recomendó la lista genérica por especie (Panel Inflamación + 5 perfiles de Cachorros, para una perra de 2 años), aunque el catálogo tiene 11 perfiles Prequirúrgicos armados (152–162); (2) "Pre quirúrgicos te pedí" → "Perfecto, lo anoto. Por último, ¿qué análisis o perfil desean?" (bucle); (3) con la etiqueta PREQUIRURGICO activa, "¿No tienes perfiles armados?" re-preguntó la especie ya capturada (respondió el modelo, sin guardrail); (4) "Ya te dije q especie es" terminó con `exam_type="PREQUIRURGICO CANINO"` (no existe en el catálogo) y salto directo a la pregunta de pago; el resumen final salió sin análisis incluidos y sin valor estimado.
- Causa raíz: ninguna vía de recomendación consideraba la CATEGORÍA que el cliente nombró. La rama determinista pre-AI y `_enforce_profile_recommendation_help` listaban solo `list_catalog_profiles_for_species` (genérico); `_enforce_diagnostic_label_help` saltaba directo a pruebas sueltas a medida aunque la categoría tuviera perfiles armados; y con `_diagnostic_label` activo no había respuesta determinista para "perfiles armados", así que el modelo improvisaba (re-preguntar especie, inventar un exam_type sin respaldo de catálogo ni precio).
- Solución aplicada:
  1. `db.list_catalog_profiles_matching_category(text, species)`: perfiles activos cuya categoría normalizada (sin tildes/espacios: "pre quirúrgico" → "prequirurgico") aparece en el texto; lógica de filtrado en `filter_profiles_by_category_mention` (pura, testeable).
  2. `agent._category_profiles_menu_response`: menú seleccionable (`_profile_menu_options`) con los perfiles armados de la categoría (códigos y precios reales), limpiando análisis previo y `_diagnostic_label`; menciona que también se puede armar a medida.
  3. Conectado categoría-primero en: rama pre-AI de recomendación, `_enforce_profile_recommendation_help`, `_enforce_diagnostic_label_help` (perfiles armados antes que pruebas sueltas) y `_diagnostic_label_profile_turn` (nuevo detector `_asks_for_armed_profiles` para "¿no tienes perfiles armados?").
- Archivos afectados: `app/services/db.py`, `app/agent.py`, `tests/test_category_profile_menu.py` (nuevo), `tests/test_analysis_options_restore.py` (patch de la nueva función).
- Tests: 7 nuevos en `tests/test_category_profile_menu.py`; suite 151 passed (los 4 fallos de `test_dashboard.py` por `exec_alerts_count` son preexistentes, verificado con git stash). Verificado además contra el catálogo real: el mensaje exacto de la prueba devuelve los 11 perfiles 152–162 con precios, y "¿No tienes perfiles armados?" con la etiqueta activa responde el menú sin re-preguntar la especie.
- Validación con modelo REAL (2026-07-03): nuevo caso U en `tools/scripts/validate_flows.py` (réplica de la conversación fallida; perfiles Prequirúrgicos en el catálogo mock y `list_catalog_profiles_matching_category` parcheada con el filtro puro real) → OK end-to-end: "¿cuál me recomiendas pre quirúrgico?" ofrece el menú de armados, "el 1" registra 701 con $24.000, el resumen muestra análisis y valor estimado, y la orden cierra. Flujos Q y R (etiqueta + personalización) siguen OK. Durante esta validación apareció ABIERTO-004 (identificación, preexistente).
- Estado: corregido (pendiente prueba conversacional real del usuario).

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
- L58 — Identificación de cliente también viene como "X es la clínica", no solo "clínica es X" (RESUELTO-026)
- L57 — Alegra debe buscar contactos con y sin DV antes de crear (RESUELTO-019)
- L56 — La intención compuesta también llega como “análisis extra”, no solo “agregar” (RESUELTO-018)
- L55 — Nunca armar texto normalizado desde un set; un paso conversacional repetible necesita salida explícita (RESUELTO-017)
- L54 — Las listas de opciones las arma el CÓDIGO desde la BD, no el modelo; los guards disparan con el mensaje del usuario, no solo con exam_type (RESUELTO-016)
- L53 — Una afirmación pelada significa "cliente nuevo" SOLO si el bot lo preguntó (RESUELTO-015, recurrencia de L46)
- L52 — Una pregunta abierta por área durante el ajuste de un perfil debe listar opciones, no caer al resumen (RESUELTO-014)
- L51 — En confirmación, un ajuste parcial gana sobre el cierre (RESUELTO-013)
- L50 — El resumen debe combinar concepto y precio en una sola línea (RESUELTO-012)
- L49 — Una confirmación de perfil se resuelve por intención, no por frase exacta (ERR-044)
- L48 — Los códigos del catálogo ganan sobre etiquetas diagnósticas (ERR-043)
- L47 — Banderas de estado deben reconciliarse con el avance real, no quedar pegadas (RESUELTO-010)
- L47 — Resolver perfiles por CÓDIGO, y llevar el NIT a facturación (ERR-041)
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
- L42 — Una respuesta operativa fija solo aplica a PREGUNTAS, no a ordenes impacientes
- L45 — Agregar análisis a un perfil del catálogo no debe perder el precio base (ERR-039)
- L44 — "No sé qué pedir" necesita guard determinista; y distinguir cambio TOTAL vs PARCIAL del análisis (ERR-038)
- L46 — Interpretar por contexto/intención, nunca por longitud del mensaje (ERR-040)
- L43 — Testear con una IA-cliente adversarial, nunca con respuestas del LLM hardcodeadas
- L47 — Una pregunta pendiente se re-pregunta al final del turno; nunca se asume por progreso del mismo turno (ERR-046)
- L48 — Los datos con plata viven en UNA estructura; el texto libre del modelo nunca es fuente de verdad (ERR-050)

### Tareas registradas
- Fix: ERR-050 — agregar análisis a un perfil elegido (prueba real 2026-07-04, chat 4) — COMPLETADO
- Fix: ERR-046 + ERR-047 (confirmación pendiente y selección de coincidencia) — COMPLETADO
- Fix: perfiles armados por categoría ignorados (prueba 2026-07-03, chat 4) — COMPLETADO
- Módulo "Facturación" (Alegra) — Completado (falta aplicar migración 014)
- Personalización de columnas en tablas del CRM — Completado (falta aplicar migración)
- Bug: agregar otro análisis/perfil se traba (chat 4 real) — En curso
- Integración de Alegra (facturación electrónica DIAN) — Por fases — En curso
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
