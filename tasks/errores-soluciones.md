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
