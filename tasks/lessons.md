# Lecciones aprendidas — A3 Laboratorio Veterinario

> Actualizar después de cada corrección del usuario.
> El objetivo es no repetir el mismo error.

### L57 — Alegra debe buscar contactos con y sin DV antes de crear (RESUELTO-019)
**Problema:** una orden válida no apareció como borrador en Alegra aunque el hook corrió. El log mostró `POST /contacts -> HTTP 400 code 2006`: el contacto ya existía con identificación `53115419` y DV `1`, pero el lookup previo buscaba `53115419-1`; al no encontrarlo intentó crearlo y Alegra lo rechazó como duplicado.
**Regla:** para NIT colombiano, la idempotencia de contactos no puede depender de una sola representación textual. Antes de crear, buscar por el valor original y por el número sin DV (`_split_nit`). Si no hay evento `alegra_invoiced`, revisar primero el warning de Alegra y el evento `created`: si hay líneas/precio/NIT, el fallo está en API/contacto, no en el perfil.

### L56 — La intención compuesta también llega como “análisis extra”, no solo “agregar” (RESUELTO-018)
**Problema:** `sí quiero el perfil 152 más un análisis extra` seleccionaba el perfil 152 pero descartaba la intención de agregar algo más, y respondía con la oferta genérica de pago. El detector solo reconocía verbos (`agregar`, `sumar`, `agrégale`), no el sustantivo natural `análisis extra`. Además, cuando la selección venía desde un menú de perfiles, el handler elegía el perfil y no procesaba el resto del mensaje.
**Regla:** un turno de selección no termina al encontrar el número/código: hay que consumir el mensaje completo. Frases con `análisis/prueba/examen + extra/adicional` son ajuste parcial del perfil base y deben abrir el paso “¿qué análisis quieres agregarle?”, tanto por código directo como por selección desde menú.

### L55 — Nunca armar texto normalizado desde un set; un paso conversacional repetible necesita salida explícita (RESUELTO-017)
**Problema:** al implementar la oferta "¿agregar otro análisis o seguimos?", `_wants_to_proceed_to_payment` construía el texto normalizado con `" ".join(set(tokens))`. Como el orden de un set no es determinista (depende del hash seed), el match de frases ("asi esta bien") pasaba o fallaba según la corrida → test intermitente y, peor, comportamiento inconsistente en producción.
**Regla:** para detectar FRASES (substrings de varias palabras), normalizar SIEMPRE con los tokens en su orden original (`" ".join(_tokenize(text))`), nunca desde un set (los sets solo sirven para pertenencia de un token suelto). Además, todo paso conversacional que se REPITE (ofrecer agregar más) debe tener una salida explícita y robusta ("si ya está, seguimos con el pago") y un detector de "seguir" que gane sobre el de "agregar", para no reabrir el bucle histórico. Centralizar el "qué sigue tras el análisis" en una sola función (`_analysis_settled_response`) y que los guards de pago/siguiente-campo respeten el flag de la oferta. Verificar el loop completo contra el modelo real.

### L54 — Las listas de opciones las arma el CÓDIGO desde la BD, no el modelo; los guards disparan con el mensaje del usuario, no solo con exam_type (RESUELTO-016)
**Problema (reporte del usuario):** al pedir el análisis y responder vago/por área/por síntoma ("no sé", "algo de orina", "dolor de panza"), dejó de mostrarse la lista seleccionable con precios reales. Los guards de área/etiqueta dependían de que el modelo guardara el término en exam_type; el modelo empezó a improvisar la lista en el texto (sin menú detrás, no seleccionable, precios potencialmente inventados).
**Regla:** cualquier lista de perfiles/análisis con precios la construye el código desde la base de datos y la guarda como menú seleccionable (`_test_menu_options`/`_profile_menu_options`); el modelo SOLO clasifica (etiqueta/área canónica en exam_type, o null) y NUNCA escribe la lista. Los guards de selección deben disparar con el MENSAJE del usuario como respaldo cuando el modelo deja exam_type vacío y el bot acaba de pedir el análisis (`_analysis_help_candidate`), y siempre debe existir un catch-all determinístico (perfiles por especie) para que jamás quede una lista improvisada. Sincronizar prompt + guardrails: si el prompt permite que el modelo liste, lo hará mal. Verificar contra el modelo real (`repro_reco.py`), no solo mocks.

### L53 — Una afirmación pelada significa "cliente nuevo" SOLO si el bot lo preguntó (RESUELTO-015, recurrencia de L46)
**Problema (reporte del usuario):** al elegir la opción 1 del menú con "Si la uno", el bot escaló a recepción como cliente nuevo. `_confirms_new_client` da True para cualquier afirmación de ≤4 palabras con "sí", y el flujo de identificación la trataba como "soy cliente nuevo" sin contexto. Mismo patrón que L46: clasificar por longitud, no por contexto.
**Regla:** una afirmación pelada ("sí", "la uno", "dale") solo se interpreta como "soy cliente nuevo" cuando el bot ACABA de preguntar "¿eres cliente nuevo?" (verificar `_asks_if_new_client(_last_bot_message(history))`). La mención EXPLÍCITA de "cliente nuevo" (`_explicitly_says_new_client`) o frases de no-registro cuentan siempre. Antes de escalar a un handoff por una respuesta corta, preguntarse: ¿qué preguntó el bot en el turno anterior? La respuesta corta responde ESA pregunta, no una intención inventada. Auditar otros usos de heurísticas por longitud (`len(tokens) <= N`) con la misma lente.

### L52 — Una pregunta abierta por área durante el ajuste de un perfil debe listar opciones, no caer al resumen (RESUELTO-014)
**Problema (reporte del usuario):** mientras agregaba un análisis a un perfil, el cliente preguntó "que analisis de orina tienen" y el bot repitió el resumen sin responder. Quedó trabado. La causa: el ajuste solo resolvía nombre/código EXACTO; los helpers que listan por área se auto-desactivan cuando ya hay perfil base/`selected_tests`, así que la pregunta abierta nunca llegaba a `find_tests_by_area`.
**Regla:** todo punto del flujo donde el cliente puede elegir análisis debe aceptar también la pregunta abierta por ÁREA ("qué análisis de orina/sangre tienen") y responder con la lista, no solo el nombre exacto. Durante el ajuste de un perfil, esas opciones se marcan para AGREGAR al perfil base (`_test_menu_adds_to_profile`), nunca para reemplazarlo. Atender la intención COMPUESTA en un solo mensaje ("el perfil 152 al que le quiero agregar un análisis extra"): fijar el perfil y abrir el ajuste, sin saltar al pago descartando la segunda intención. Verificar contra la base real que el área se resuelve, no solo con mocks.

### L51 — En confirmación, un ajuste parcial gana sobre el cierre (RESUELTO-013)
**Problema:** `sí, pero agrégale glucosa` cerraba la orden porque el cierre determinístico veía el `sí` antes de procesar el ajuste del análisis.
**Regla:** en `fase_4_confirmacion`, detectar primero ajustes parciales del análisis (`agregar/quitar`). Si hay ajuste, modificar campos, recalcular resumen y conservar `fase_4_confirmacion`; solo cerrar cuando el mensaje sea confirmación limpia.

### L50 — El resumen debe combinar concepto y precio en una sola línea (RESUELTO-012)
**Problema:** B10 mostraba un perfil de catálogo dos veces: `Análisis: X` y `Perfil base: X ($Y)`, separando el precio del dato principal.
**Regla:** si el `exam_type` ya representa el perfil elegido, el precio base va en esa misma línea (`Análisis: X — $Y COP`). Las líneas extra (`Agregados`, `Quitados`, `Valor estimado`) solo explican ajustes reales, no repiten el perfil base.

### L49 — Una confirmación de perfil se resuelve por intención, no por frase exacta (ERR-044)
**Problema:** después de mostrar el detalle del `Perfil General`, `no asi esta bien` debía confirmar el perfil; pero el guard de catálogo corrió antes y rebuscó `Perfil General`, devolviendo varias coincidencias (`1339` y `151`).
**Regla:** cuando `_profile_detail_offered` está activo, el siguiente turno pertenece al contexto de ese perfil: confirmar, personalizar o repetir detalle por código. No volver a buscar `exam_type` por nombre/categoría antes de resolver esa respuesta pendiente. La confirmación/personalización se decide por `user_intent_signal` primero; tokens como `agregar` no ganan si la IA entendió `no quiero agregar nada` como `negate`.

### L48 — Los códigos del catálogo ganan sobre etiquetas diagnósticas (ERR-043)
**Problema:** `perfil 151` fue reinterpretado por el LLM como `Perfil General`; el guard de perfil diagnóstico corrió primero, encontró la etiqueta `GENERAL` y abrió un perfil personalizado, aunque el usuario había dado un código cerrado del catálogo.
**Regla:** cuando el usuario escribe un código de perfil (`151`, `504`, etc.), resolverlo por código desde el texto real del usuario ANTES de cualquier guard de etiqueta diagnóstica o recomendación genérica. El código es determinístico; la categoría/nombre que infiere el modelo es solo auxiliar.
Si después el usuario ajusta ese perfil (`agrégale X`, `quítale X`), la personalización gana sobre el paso de pago hasta que diga `cerramos así`.

### L47 — Banderas de estado deben reconciliarse con el avance real, no quedar pegadas (RESUELTO-010)
**Problema:** el cliente confirmó la dirección con "sisi"; el LLM entendió y avanzó al médico, pero el guardrail determinista `_confirms_address("sisi")` devolvió False (solo reconocía "si"/"sí"/"sip", no la forma pegada). La bandera `_address_confirmation_pending` quedó en True y, como `_missing_route_field` la trata como "falta la dirección" mientras esté encendida, el bot volvió a pedir la dirección turnos después, aunque `pickup_address` ya tenía valor.
**Regla:**
- Reconocer confirmaciones coloquiales tolerando variantes pegadas/alargadas ("sisi", "sisisi", "siii", "sí sí"), no solo el token exacto. Mismo espíritu que L46: entender el significado, no exigir la forma canónica.
- Toda bandera de "pendiente de confirmar" necesita una RED DE SEGURIDAD que la reconcilie con el avance real del flujo: si ya se capturó un campo posterior y el dato existe, darla por confirmada. Evaluar esa red sobre el estado ACTUAL del turno (los `fields` ya actualizados), no solo sobre el snapshot previo, o el desfase de un turno la deja pegada.
- Cuando el LLM avanza por una confirmación que el código no reconoce, el guardrail y el estado se desincronizan: ese es el patrón a cazar. Ver RESUELTO-010.

---

## Integración Alegra / precios

### L47 — Resolver perfiles por CÓDIGO, y llevar el NIT a facturación (ERR-041)
**Problema:** una orden con "Perfil Prequirúrgico I" cerró con precio $0 y no facturó en Alegra. (1) El `exam_type` venía como "152-Perfil Prequirúrgico I" (código+nombre); el backstop resolvía por nombre, que no matchea la cadena combinada y por nombre suelto devolvía un perfil de la misma familia con número distinto ($90k en vez de $24k). (2) Al identificar al cliente por NOMBRE, el NIT del cliente no se copiaba a `fields`, así que la facturación recibía `tax_id=None` y se saltaba en silencio.
**Regla:**
- Para resolver un perfil del catálogo, usar el CÓDIGO como fuente determinística (`_profile_codes_from_text` + `db.get_catalog_profiles_by_codes`). El match por nombre es ambiguo entre perfiles de la misma familia (I/II/X) — solo fallback.
- El precio del perfil debe quedar correcto en las TRES superficies a la vez: resumen al cliente, evento persistido (dashboard) y factura Alegra. El backstop en el resumen las cubre porque muta los `fields` que luego se persisten; verificar el valor en el evento real, no solo en el resumen.
- Facturar exige NIT: `_store_client_context` debe copiar `client.tax_id` a `fields` (un cliente identificado por nombre igual tiene NIT en la BD). Y un cliente sin `tax_id` en Supabase NO se puede facturar (DIAN) — es dato faltante, no bug.
- Verificar la integración contra la cuenta de pruebas real (`scripts/alegra_demo_invoice.py`): la factura se crea en BORRADOR (`create_invoice` sin `status`); se ve en Alegra filtrando por borradores, en la cuenta del token (`ALEGRA_EMAIL`), no en la vista de emitidas. Ver ERR-041, ERR-039.

## Del agente V1 (razón del reinicio)

### L1 — Schema excesivo rompe el modelo
**Problema:** El JSON schema tenía 14 campos obligatorios. El modelo OpenAI prestaba más
atención al formato que a la respuesta conversacional.
**Regla:** Schema máximo 7 campos. Solo lo que realmente se usa.

### L2 — Fases rígidas como puertas rompen el flujo
**Problema:** 8 fases internas que el modelo debía mantener en sync con la BD.
Cualquier desincronía rompía el flujo.
**Regla:** Las fases son tracking interno (`collecting | confirming | done | escalated`).
No son puertas rígidas. Si el usuario da múltiples datos, capturarlos todos y avanzar.

### L3 — Lógica fragmentada es imposible de depurar
**Problema:** `main.py` de 307 KB con lógica mezclada entre archivos.
**Regla:** Un archivo = una responsabilidad. Todos < 200 líneas.
`main.py` solo I/O. `rules.py` solo lógica pura. `services/` solo llamadas externas.

### L4 — El bot sonaba como formulario, no como persona
**Problema:** Preguntas estructuradas A→B→C predecibles. El cliente sentía que
llenaba un formulario.
**Regla:** Una sola pregunta por turno. Tono cercano, colombiano.
Verificar `captured_fields` antes de cada pregunta. No repetir.

### L5 — System prompt y schema mezclados confunden al modelo
**Problema:** El system prompt incluía instrucciones de tono Y de schema en el mismo texto.
**Regla:** `prompt.py` = tono e intenciones. `schema.py` = estructura JSON. Separados.

---

## De sesiones de trabajo futuras

### L6 — Heurísticas de "reintento de identificador" demasiado amplias causan bucles
**Problema:** Tras "No encuentro el cliente. ¿Eres cliente nuevo?", cualquier mensaje
corto del usuario ("Registrame", "Que hacemos", "Sal de ese ciclo") se interpretaba como
un nuevo nombre de veterinaria y se re-buscaba → bucle infinito de "Tampoco encuentro un
cliente registrado". `_confirms_new_client` era muy estrecho (solo "cliente nuevo" literal
o "sí" ≤4 palabras) y no captaba confirmaciones naturales.
**Regla:** Cuando el bot hace una pregunta sí/no (p. ej. "¿eres cliente nuevo?"), la
siguiente respuesta debe tratarse como respuesta a ESA pregunta, no reciclarse como dato
para re-buscar. Solo volver a buscar si el usuario da un identificador genuino (NIT nuevo o
nombre con palabra clave veterinaria/clínica/dr). Las heurísticas que convierten "texto
corto" en "intento de identificador" deben tener una salida clara hacia escalamiento.
**Cómo se detecta:** el último mensaje del bot (`_last_bot_message`) es la fuente de verdad
del contexto, no solo los flags de `captured_fields` (que persisten varios turnos).

### L6 — Revisar rutas externas indicadas por el usuario
**Problema:** Se asumió que el dashboard debía estar dentro de `A3 ULTIMO`, pero el usuario lo tenía en otra carpeta/ZIP.
**Regla:** Cuando el usuario mencione una ruta externa, verificar esa ubicación antes de concluir que una pieza no existe.

### L7 — Evitar `Start-Process` en OpenCode (Windows)
**Problema:** Al levantar procesos en segundo plano con `Start-Process` (Flask/ngrok), el runner puede fallar con `ChildProcess.kill`, dejar estados inconsistentes o parecer "trabado".
**Regla:** En OpenCode, priorizar ejecución controlada en un solo comando/script (inicio + verificación + cierre limpio). Evitar procesos detached persistentes durante la sesión.

### L8 — Limpiar identificación fallida antes de reintentar cliente
**Problema:** Una sesión con `_client_not_found` podía conservar un `clinic_name` o `tax_id` viejo y bloquear búsquedas posteriores de veterinarias existentes.
**Regla:** Si el usuario responde con un nuevo identificador después de una identificación fallida, limpiar los campos de identificación contaminados antes de volver a consultar la BD.

### L9 — No convertir datos de paciente en nombre de clínica
**Problema:** Si el bot esperaba NIT o nombre de veterinaria, una respuesta evasiva como "el paciente se llama Toby" podía quedar capturada como `clinic_name`.
**Regla:** Cuando se espera identificación de cliente, filtrar términos de paciente/análisis antes de buscar clínicas en la BD.

### L10 — Identificar clientes solo por nombre o NIT
**Problema:** Pedir teléfono como verificación de identidad confundía el flujo y podía asociar órdenes a sedes o clientes incorrectos.
**Regla:** Para identificar clientes usar solo NIT o nombre registrado. El teléfono, si se pide, es únicamente dato de contacto de la orden.

### L11 — El orden de recolección de la orden vive en DOS lugares sincronizados
**Problema:** El `clinic_phone` se pedía apenas se identificaba el cliente (posición 2), no junto a los datos del paciente. Para moverlo hubo que tocar `prompt.py` (lista del PASO 3 que sigue el AI) Y `agent.py` (tupla `_ROUTE_ORDER_FIELDS_BEFORE_PAYMENT` que fuerza el orden cuando el AI se desvía).
**Regla:** Al cambiar el orden o el conjunto de campos de la orden de servicio, actualizar SIEMPRE ambos: la lista numerada del PASO 3 en `prompt.py` y `_ROUTE_ORDER_FIELDS_BEFORE_PAYMENT` en `agent.py`. Si quedan desincronizados, el AI pregunta en un orden y los guardrails lo reescriben a otro.

### L12 — El guard anti-bucle no debe pisar la selección de análisis
**Problema:** Al armar un perfil (cardíaco, personalizado), repetir "¿agregás otro análisis?" comparte tokens con preguntas previas, y `_avoid_repeated_question` lo confundía con un bucle, reemplazándolo por el fallback genérico "Para avanzar, puedes decirme: 1) el análisis o perfil...", descarrilando la conversación un turno.
**Regla:** Los guards anti-repetición no aplican durante la selección activa de análisis (`selected_tests` no nulo con `exam_type` aún vacío, o `_profile_customizing`). En ese modo el bot solo itera sobre análisis y repetir la pregunta es esperado, no un bucle.

### L13 — Forzar términos en español en el prompt para evitar code-switching
**Problema:** El bot escribió "profiles" en inglés ("¿qué análisis/profiles están disponibles?") porque todo el código interno usa `profile/profiles` y el LLM se contagia.
**Regla:** Cuando un término técnico del código tiene una forma en inglés que el LLM puede filtrar a la respuesta, fijar la forma en español con una regla ortográfica explícita en `prompt.py` (como R18: usar "perfil/perfiles", nunca "profile/profiles").

### L14 — El "modo construcción de perfil" debe cerrarse cuando exam_type queda fijado
**Problema:** En `process_turn`, la inyección del catálogo de análisis individuales + el bloque "PERFIL PERSONALIZADO EN CONSTRUCCIÓN" se activaba con la sola condición `selected_tests is not None or removed is not None`. Como esos campos persisten tras cerrar el perfil, el sistema seguía inyectando el modo construcción INDEFINIDAMENTE aunque `exam_type` ya estuviera fijado. El AI quedaba en bucle pidiendo análisis ("¿agregás otro?" → fallback "Para avanzar, puedes decirme: 1) el análisis o perfil...") sin avanzar nunca a paciente/médico. El cierre del perfil ("cerramos así") no rompía el bucle.
**Regla:** El modo construcción/personalización de perfil sigue activo SOLO si `(selected_tests/removed no nulos) AND (not exam_type OR _profile_customizing)`. Misma condición que usa `_avoid_repeated_question` (L12). Una vez que `exam_type` queda fijado y no se está personalizando un perfil base, el perfil está cerrado: dejar de inyectar catálogo/resumen y avanzar a los datos del paciente. Mantener sincronizadas ambas condiciones (selección de contexto en `process_turn` y guard anti-repetición).

### L15 — La detección de confirmación debe tolerar lenguaje natural, no exigir palabras exactas
**Problema:** El gate de confirmación de dirección usaba `_is_affirmative_text`, que exige `len(words) <= 5` y un vocabulario cerrado (`sí/ok/dale/...`). En la práctica la gente confirma con deícticos ("sí es ese", "esa misma", "esa está bien") y a veces mezcla una pregunta en el mismo mensaje ("si es ese, ¿vienen igual si llueve?" = 9 palabras). Esas confirmaciones válidas se descartaban → el flag `_address_confirmation_pending` quedaba pegado y el bot repreguntaba la dirección 3-4 veces. Peor: con el flag pegado, un "no" posterior (a observaciones) se interpretaba como rechazo de la dirección, reseteándola. Verificado en el historial real del chat 4.
**Regla:** Para gates de confirmación, usar detectores tolerantes: incluir deícticos ("ese/esa/eso/correcta"), NO limitar la longitud cuando hay señal afirmativa clara, y dejar que una negación explícita gane. Crear funciones específicas del contexto (`_confirms_address`/`_rejects_address`) en vez de tocar la detección global. Además, todo flag de "confirmación pendiente" debe tener una salida segura: si el flujo ya avanzó más allá de ese paso, bajar el flag automáticamente para no reinterpretar respuestas posteriores. Un flag que solo se limpia con detección exacta termina pegado.

### L16 — Cada intent del menú necesita flujo o mensaje propio, si no el LLM arrastra el dominante
**Problema:** La opción 2 del menú (results) no tenía flujo en ningún lado: ni una sección en `prompt.py` ni lógica en `agent.py` (`route_scheduling` era el único con flujo real + ~12 `_enforce_*`). Al elegir "2", el modelo no tenía guía y arrastraba el único flujo detallado que conoce (route_scheduling): pedía NIT, dirección, etc. El usuario percibía que la opción 2 hacía "lo mismo" que la 1.
**Regla:** Toda intención ofrecida en el menú debe tener un comportamiento explícito y determinista, aunque sea un mensaje fijo. No basta con listarla en el prompt: el flujo dominante la "absorbe". Patrón: (1) sección breve en el prompt para clasificar bien, (2) enforcement determinista por intent en `agent.py` que garantice el comportamiento, (3) intercepción temprana para la elección directa del menú. Y al cortar un flujo, preservar siempre `pending_intents` (multi-intención): un usuario puede pedir resultados Y programar una ruta en el mismo mensaje.
**Refinamiento (robustez de la intercepción):** No detectar el "contexto de menú" comparando el último mensaje del bot con la constante por igualdad exacta de string (`== WELCOME_MESSAGE`): es frágil. Mejor detectar por marcadores de contenido ("Consultar resultados" + "número") O por estado de sesión al inicio (intent unknown + sin client_id + sin datos de orden). Esto cubre también sesiones reusadas donde el menú no fue el último mensaje. Y acotar el detector de la opción (len de tokens ≤ 4) para no confundir "2 años" (edad, en una orden activa) con la elección "2" del menú. Recordatorio operativo: Flask sin `--reload` sirve el código viejo en memoria — un cambio "que no se aplica" casi siempre es eso.

### L17 — Los enforcements que hacen I/O deben tener guard previo y ser defensivos
**Problema:** Al agregar `_enforce_test_category_help` (despliega análisis por área, ej. "orina"), llamaba `db.find_tests_by_area` (query a Supabase) en CADA turno de route_scheduling con exam_type. Esto: (1) rompió 30 tests con ConnectError, porque la función nueva no estaba mockeada y los tests usan una URL de Supabase falsa; (2) en producción haría una query pesada (5000 filas) en cada paso posterior (paciente, dirección, cierre) aunque exam_type no cambiara. Los enforcements existentes no rompían porque evitan I/O con guards previos (`_looks_like_catalog_profile`, `_looks_like_specific_profile_query`) o try/except (`list_diagnostic_labels`).
**Regla:** Un enforcement que consulta la BD debe (1) tener un guard que limite CUÁNDO hace I/O —idealmente solo cuando el dato relevante es nuevo en el turno (comparar con `prev_captured`), no en cada turno— y (2) la función de `db` debe ser defensiva (try/except → vacío) si su ausencia no debe romper el flujo. Patrón de guard "campo nuevo": `if not candidate or candidate == prev_fields.get(campo): return`. Además, toda función nueva de `db` que un enforcement invoque necesita su mock en los tests que ejercitan ese flujo.

### L18 — No capturar identificador a ciegas: detectar correcciones/confusión de opción
**Problema:** En el gate de identificación, `_extract_clinic_name_candidate` tomaba casi cualquier frase corta (con letras, ≤8 tokens) como nombre de veterinaria. Cuando el usuario respondía "Perdón me confundí de opción" (una corrección, no un dato), el sistema lo buscaba como cliente, no lo encontraba y respondía "No encuentro ningún cliente… ¿Eres cliente nuevo?". Verificado en el chat 4 (Chuck). La captura era determinista, así que el LLM ni siquiera podía "razonar" sobre la coherencia.
**Regla:** Antes de capturar un dato en un gate determinista, descartar mensajes que claramente NO son ese dato. Para el identificador: detectar señales de corrección/confusión de opción ("confundí", "me equivoqué", "otra opción", "volver al menú") con `_wants_to_reconsider_option` e interceptar ANTES de la extracción/búsqueda, reconduciendo al menú con calidez (`OPTION_RECONSIDER_MESSAGE`) y reseteando el estado de identificación. Defensa adicional: sumar esas palabras a `_NON_IDENTIFIER_TOKENS` para que la extracción de nombre las rechace por otros caminos. Y reforzar el prompt (R23) para los flujos que sí pasan por el LLM. Patrón general: los detectores de "esto no responde la pregunta" deben correr antes de la captura, no después.

### L19 — Robustez ante clientes que no siguen los pasos (testeo con lenguaje caótico)
**Problema:** Testeando como "cliente normal que no lee" salieron 3 fallas: (1) decir "tengo un perrito malito" hacía que el bot lo clasificara como particular y se trabara (escalaba y no se recuperaba aunque después diera el nombre real); (2) el nombre del cliente dentro de un mensaje largo ("…soy de adryvete") no se extraía (límite de tokens + palabras de pedido lo descartaban); (3) "el de siempre" pedido para el médico (sin médico recordado) hacía que el modelo reofreciera la dirección (el único dato disponible en "Datos ya capturados").
**Regla:**
- La barrera B2B NO es detectar "particular" por el lenguaje, sino la verificación contra la base: solo se atiende a quien tiene NIT/nombre en el registro. Mencionar una mascota NO convierte a alguien en particular (los veterinarios hablan de mascotas). Prompt: no escalar por eso; sí escalar solo si lo dicen explícito.
- Extraer el nombre del cliente tras un marcador claro ("soy de X", "somos la veterinaria X") aunque esté al final de un mensaje largo (`_extract_clinic_name_candidate` con búsqueda de marcador al final + `_has_client_marker` para correr la extracción aunque el bot no haya pedido el identificador todavía). Filtrar muletillas en la búsqueda de cliente (`_CLIENT_QUERY_STOPWORDS`).
- El reofrecimiento de memoria ("el de siempre") debe ser SIEMPRE del campo que se está pidiendo. Como el modelo agarra cualquier dato de "Datos ya capturados", el prompt no basta: intercepción determinista que, si se pide un campo sin dato recordado (ni en `_client_memory` ni en `_prev_order_snapshot`), pide ese dato y no deja que el modelo reofrezca otro. Y el hint de memoria solo se inyecta para el próximo campo faltante. Recordar incluir "siempre"/"de siempre" en los detectores de "reusar dato".
- Verificación: los fixes que dependen del prompt no se confirman sin re-testeo con el LLM (es no-determinista). Re-correr los escenarios que fallaron, no asumir que el cambio de prompt bastó.

### L20 — El fallback anti-bucle necesita un branch por CADA campo, y los enumerados, red de typos
**Problema:** Pidiendo la especie, el cliente respondía "Kanino"/"Kany" (variante/typo de canino). El modelo no lo capturaba y repetía la pregunta idéntica; `_avoid_repeated_question` lo detectaba como bucle y lo reemplazaba por `_rephrased_repeated_question`, pero esa función NO tenía branch para especie (ni sexo ni pago) → caía al `return` genérico robótico "Para avanzar, dime el dato que tengas a mano o escribe 'hablar con alguien'". El usuario lo encontró testeando una conversación real (Luciano); yo había declarado el flujo "funcionando" sin probar este camino.
**Regla:**
- `_rephrased_repeated_question` debe tener un branch con opciones cálidas y concretas para CADA campo que pueda repetirse (NIT, dirección, análisis, especie, sexo, pago, médico, resto). Si falta uno, ese campo cae al genérico robótico. El genérico final nunca debe sonar a "escribe 'hablar con alguien'": ofrecer retomar el dato y, suave, la opción de un humano.
- Los campos ENUMERADOS (especie, sexo) necesitan una red de recuperación determinista de variantes/typos (`_recover_enumerated_answer` + tablas `_RECOVERABLE_SPECIES`/`_RECOVERABLE_SEX`): si el modelo no captura "kanino"/"perrito"/"masho", lo normalizamos nosotros y dejamos que `_avoid_redundant_route_field_question` corrija el reply al siguiente campo. Así el bucle no llega a ocurrir. Lo genuinamente ambiguo ("Kany") queda para que el modelo confirme ("¿te refieres a canino?", reforzado en prompt R5b + PASO 3).
- No subir el umbral del anti-bucle globalmente: dos tests (identificación y perfil cerrado) dependen de que UNA repetición dispare el reemplazo. El arreglo es por-campo, no por-umbral.
**Proceso (corrección del usuario):** No declarar "el flujo funciona" sin recorrer los caminos del cliente que no sigue los pasos (typos, off-topic, respuestas ambiguas). Los tests unitarios con el modelo mockeado verifican los guardrails deterministas, pero la captura real del LLM solo se confirma en sesión local con la API. Testear esos caminos ANTES de cerrar, no esperar a que el usuario los encuentre.

### L21 — El cierre de ruta no puede prometer motorizado sin asignación real
**Problema:** La BD podía crear una solicitud con `status=error_pending_assignment` cuando el cliente no tenía motorizado, pero el reply de cierre seguía diciendo "Nuestro motorizado pasará a recoger la muestra". El estado operativo quedaba correcto, pero la conversación prometía algo falso.
**Regla:** El mensaje final de una ruta debe depender del courier real de `client_courier_assignment`. Si no hay courier, reemplazar cualquier promesa de recogida por coordinación manual de operaciones, dejar `requires_handoff=true` y `handoff_area=operaciones`. Los tests que no están probando falta de motorizado deben mockear un courier real para no ocultar el caso.

### L22 — Cliente nuevo no se captura en chat si la regla dice escalar
**Problema:** El bot tenia un Flujo B que pedia clinica, medico, direccion y telefono para clientes no registrados. Eso contradecia la regla base: alta de cliente siempre escala a recepcion/operaciones y el bot nunca registra ni toma datos extensos en chat.
**Regla:** Si una regla de negocio dice "siempre escala", no agregar subflujos de captura conversacional aunque parezcan utiles. La trazabilidad puede quedar en `requests`, pero los datos del alta se capturan desde recepcion/plataforma. Si existen sesiones persistidas a mitad de un flujo viejo, se pueden atender como compatibilidad, pero no deben existir nuevas entradas a ese flujo.

### L23 — La arquitectura documentada debe describir el sistema real
**Problema:** `docs/architecture.md` y los archivos de contexto para agentes seguian describiendo el diseño ideal inicial: solo Telegram, fases `collecting|done`, schema pequeno y limites de lineas que el agente ya no cumplia. Eso ocultaba deuda tecnica y confundia las pruebas esperadas.
**Regla:** Cuando el agente crece, actualizar la documentacion principal con el estado real antes de planear refactors. Separar "estado actual" de "objetivo/refactor pendiente" y anclar cada cambio a pruebas o decisiones vigentes.

### L24 — La forma de pago en una ruta no debe arrastrar el intent de contabilidad
**Problema:** En una ruta activa, el usuario respondia "pago en linea" cuando el bot pedia forma de pago y el modelo podia clasificarlo como `accounting`. Eso creaba una solicitud terminal incompleta o saltaba la confirmacion editable. Tambien podia descarrilar si el usuario decia la forma de pago antes de que tocara ese campo.
**Regla:** La fuente de verdad es el campo que el bot acaba de pedir. Si la pregunta activa es `payment_method`, normalizar la respuesta como dato de la ruta (`contraentrega`/`pago_linea`) y mantener `intent=route_scheduling`; si todavia falta otro campo, una forma de pago fuera de turno no cierra ni escala, se vuelve al campo faltante. Cubrir con test deterministico y revalidar con `validate_flows.py` usando modelo real.

### Formato de entrada

```
### L[N] — [Título del patrón]
**Problema:** [qué pasó]
**Regla:** [cómo evitarlo en el futuro]
```

### L[+] — Memoria de datos estables entre órdenes
**Problema:** al iniciar una orden de seguimiento, `_reset_order_fields` borraba médico/pago y el bot los repreguntaba en blanco; la memoria solo se reofrecía con la frase exacta "el de siempre". Los clientes que repiten veterinario/clínica se frustraban.
**Regla:** los datos estables (médico, dirección, pago) se conservan vía `_client_memory` + `_prev_order_snapshot` y se reofrecen en bloque al crear otra orden (`_carry_over_stable_fields`). NUNCA borrar memoria del cliente en los resets de orden; solo reiniciar datos del paciente. La resolución de "el mismo" debe caer a `_client_memory` aunque no exista snapshot.

### L[+] — Convertir entradas libres a catálogo solo con mapeo 1:1
**Problema:** capturar varios análisis de un mensaje como perfil personalizado es frágil porque `get_tests_by_codes_or_names` puede devolver varios tests por término ambiguo (ej. "química").
**Regla:** al auto-convertir texto libre a códigos de catálogo, exigir que cada ítem resuelva 1:1 (exactamente un test). Ante ambigüedad o ítem inexistente, hacer back-off y dejar el flujo normal/AI, nunca capturar a ciegas.

### L[+] — Backstops determinísticos para cerrar flujos que dependen del modelo
**Problema:** el cierre del perfil personalizado dependía 100% de que el modelo fijara `exam_type`; si no lo hacía, el bot repreguntaba "¿agregás otro?" sin fin.
**Regla:** todo paso de cierre crítico necesita un backstop determinístico. Si el estado (selected_tests no vacío, sin exam_type) más una señal clara del usuario (cerrar) bastan para avanzar, hacerlo en código, no confiar solo en el prompt.

### L[+] — Código muerto que contradice una regla de negocio = borrar, no tolerar
**Problema:** el "Flujo B" de cliente nuevo estaba definido pero nunca se invocaba, y registraba clínica/médico/dirección, violando "el bot nunca registra cliente nuevo".
**Regla:** el código muerto que además puede violar una invariante de negocio es un riesgo, no deuda inofensiva. Borrarlo, dejar que las sesiones legacy se auto-sanen, y cubrir con un test que pruebe que el flujo activo sigue escalando.

### L25 — El cierre tras confirmar debe ser determinístico (caso Luciano)
**Problema:** en `fase_4_confirmacion`, el "sí" del usuario solo cerraba la orden si el LLM emitía `fase_6_cierre`. El guardrail permitía cerrar pero no lo forzaba; en chats largos el modelo no siempre lo emitía y la orden quedaba trabada sin registrarse.
**Regla:** todo cierre crítico que dependa de una confirmación necesita un backstop determinístico. Si el estado (venimos de confirmación + orden completa) y la señal del usuario (confirma) bastan, cerrar en código, no confiar en que el modelo devuelva la fase terminal. Ver ERR-008.

### L26 — La IA interpreta el significado; las listas de tokens son fallback, no autoridad
**Problema:** ~52 detectores de tokens decidían la intención del usuario (confirma, es nuevo, "el mismo"). Cada forma nueva de decir algo rompía el flujo (caso Chuuck: "soy independiente" no estaba en la lista → bucle).
**Regla:** la interpretación del LENGUAJE se delega al LLM vía `user_intent_signal` (señal semántica), que los guardrails usan como FUENTE PRIMARIA; las listas de tokens quedan como FALLBACK. El código determinístico hace cumplir las REGLAS DE NEGOCIO, no interpreta lenguaje. Migrar por etapas, manteniendo los tests verdes. Ver ERR-011.

### L27 — Ante algo fuera de alcance: ofrecer derivar o seguir, nunca inventar ni clavarse
**Problema:** pedidos random o fuera de los 4 servicios (sucursal nueva, etc.) dejaban el bot clavado o intentando responder algo que no puede.
**Regla:** el bot tiene alcance cerrado (4 servicios). Todo lo demás cae a 3 destinos seguros: fuera de tema inofensivo → responder breve y retomar; no puede pero es legítimo → ofrecer "¿te derivo o seguimos?"; ininteligible → aclarar una vez y, si insiste, derivar. NUNCA inventar un dato ni responder como si pudiera hacer algo fuera de su alcance. Ver ERR-012, ERR-013.

### L29 — Los mocks ocultan bugs de integración: el cierre debe probarse contra la BD real
**Problema:** el cierre por Chatwoot no respondía nada. La suite (que mockea `db.create_request`) daba todo verde, pero el insert real violaba un CHECK constraint (`entry_channel="chatwoot"`) y lanzaba excepción, matando el turno. Los mocks probaban una "situación perfecta" que en producción no existía.
**Regla:** todo camino que ESCRIBE en la BD (sobre todo el cierre de orden) necesita al menos una prueba de integración contra la BD real (crear + verificar + borrar la fila), por cada canal (telegram y chatwoot). No declarar "funciona" un flujo end-to-end probado solo con mocks. Ante "no responde solo al final", sospechar primero de una excepción en el insert (constraints/columnas), no de la lógica conversacional.

### L28 — Red anti-bucle por estancamiento (corte duro universal)
**Problema:** distintas causas dejaban el bot dando vueltas (identificación, sedes); arreglar cada causa una por una no garantiza que no aparezca otra.
**Regla:** además de arreglar cada bucle, tener una red transversal: contar turnos consecutivos sin avanzar (`_offtrack_count` con señal `unclear`/`off_topic`) y derivar a una persona al 3º. Cualquier turno que encaja reinicia el contador. Es la garantía de "nunca se clava" independiente de la causa. Limitación actual: depende de la señal de la IA (ver ABIERTO-002).

### L30 — Verificar coherencia con el negocio y pedir OK ANTES de crear tests/flujos/cambios
**Problema:** al auditar, inventé un flujo de validación "cliente registrado sin motorizado" basándome solo en que el código lo contemplaba (ERR-003/L21), sin confirmar con el usuario si ese estado existe en su negocio. El usuario lo frenó: en su operación TODO cliente registrado tiene motorizado, así que ese caso no debe ocurrir y testearlo no tenía sentido. Corrección explícita del usuario: "verificá que tenga coherencia antes de hacer algo, o preguntame, o decime 'voy a hacer esto y esto por esta razón' y yo digo sí".
**Regla:** antes de crear flujos de prueba, tests o cambios que asuman una regla de negocio, validar que la regla sea real (preguntar o revisar datos), no deducirla de que el código "lo maneje". Que el código contemple un estado no significa que el negocio lo permita. Patrón obligatorio: enunciar "voy a hacer X, Y, Z por esta razón" y esperar el sí del usuario antes de ejecutar. El código que cubre un estado imposible según el negocio es deuda a revisar, no una feature a testear (ej. la rama "sin motorizado" si todo registrado tiene motorizado).

### L31 — Corregir un dato en la confirmación debe conservar la fase (caso Rocky, ERR-018)
**Problema:** al corregir un campo en `fase_4_confirmacion`, el handler usaba `_base_route_response`, que fija `phase=fase_2_recogida_datos`. Eso sacaba la conversación de la confirmación, y el "sí" posterior ya no cumplía `previous_phase == CONFIRMATION_PHASE`, así que el cierre determinístico no disparaba: re-mostraba el resumen y nunca registraba. Solo se vio con el modelo real (los tests mockeados no lo detectaban).
**Regla:** mientras el cliente edita el resumen sigue en la fase de confirmación. Todo handler que responda durante `fase_4` debe conservar `CONFIRMATION_PHASE` (no heredar la fase por defecto de un helper genérico), para que el "sí" cierre por el camino determinístico que ya existe. Más en general: un helper de respuesta con fase fija (`_base_route_response` → fase_2) no debe usarse tal cual dentro de un paso que requiere otra fase; sobreescribir la fase explícitamente. Ver ERR-018, emparentado con ERR-008 (cierre) y ERR-015 (entrada al resumen).

### L32 — El flujo MULTI-ORDEN debe aguantar turnos intermedios, herencia y "el mismo X" (ERR-023)
**Problema:** la primera orden funcionaba, pero la segunda en adelante fallaba: (1) el reset de la nueva orden solo se disparaba si la sesión estaba en fase terminal en ese turno EXACTO; un turno intermedio (charla) lo rompía y arrastraba los datos de la orden anterior; (2) el pago en línea heredado escalaba/registraba la orden de seguimiento VACÍA; (3) "el mismo propietario que el otro perro" (frase larga) caía al modelo y se confundía con el paciente; (4) la corrección no reconocía "la perra/se llama" como paciente → bucle.
**Regla:**
- El inicio de una orden de seguimiento NO debe depender de estar en fase terminal en ese turno: marcar que una orden ya se registró (`_order_registered` en `_finalize_request`) y detectar "otra orden" en cualquier turno posterior con un detector EXPLÍCITO (`_explicitly_wants_another_order`, no un "sí" suelto). Centralizar el inicio (`_begin_followup_order`) para que sea idéntico desde fase terminal o tras charla.
- Ninguna orden incompleta debe cerrarse/escalar: `_prevent_incomplete_route_closure` corre JUSTO antes de `_finalize_request`, después de TODOS los guardrails de cierre/handoff (incluido el escalado por `pago_linea` heredado).
- En la orden de seguimiento: datos del PACIENTE se piden de cero (no heredar, evita arrastre); los estables y el análisis se REOFRECEN para confirmar/cambiar (guardar el análisis en el snapshot).
- "El mismo X" debe priorizar el campo EXPLÍCITO (en `_SAME_AS_FIELD_KEYWORDS`, `owner_name` antes que `patient_name`, y sin keywords ambiguas como "perro/gato" en paciente) y resolver aunque la frase sea larga si hay campo explícito (no atarse al límite de 6 tokens). La corrección reconoce al animal ("perro/perra/gato…") como `patient_name`.
- Verificación: reproducir el multi-orden contra BD + modelo real (`diag_multiorden.py`), no solo la primera orden. Ver ERR-023.

### L33 — La comprensión del lenguaje es del LLM, no de detectores de tokens (ERR-024)
**Problema:** el agente "no entendía" sinónimos ("perra"=hembra canino), datos adelantados ni "el mismo X" porque short-circuits y ~40 detectores de tokens cortaban ANTES del LLM o reinterpretaban lo que el LLM ya entendía. Ej.: "el mismo, solo cambia el paciente" (al pedir propietario) → aplicado al paciente; "soy el Dr. X" en frase larga → médico no capturado.
**Regla:** el LLM interpreta QUÉ dijo el cliente (sinónimos, implícitos, intención, datos adelantados); el código SOLO hace cumplir reglas de negocio (cliente registrado, orden completa, escalar, corte horario). Principios concretos:
- Un short-circuit determinista NO debe cortar antes del LLM si la frase puede traer el dato: acotar "el de siempre / el mismo" a frases CORTAS (≤6 tokens); las largas siguen al LLM.
- Para "el mismo X" usar el campo PREGUNTADO (contexto) y recuperar su valor del snapshot, NO el campo mencionado en la frase. `_CHANGE_TOKENS` distingue "lo que cambia" de "el mismo".
- Reforzar la captura semántica en el prompt (R26 sinónimos/implícitos/datos en frases largas; R27 "el mismo X, cambia Y").
- Los detectores de tokens quedan como FALLBACK (rellenar huecos que el LLM dejó vacíos, p. ej. `_recover_doctor_from_text`, `_recover_enumerated_answer`), nunca pisan lo que el LLM ya capturó.
- Verificar con lenguaje NATURAL real (`diag_comprension.py`), no con las palabras exactas. El LLM no es 100% determinista: los fallbacks cubren los casos comunes. Ver ERR-024, L26.

### L34 — Preventa no es una orden: responder primero, identificar después
**Problema:** preguntas normales antes de comprar/probar el servicio (metodología, cobertura, si retiran muestras, casos post-mortem) se trataban como inicio de orden. El gate de identificación pisaba respuestas humanas con "dame NIT", y una explicación clínica corta podía capturarse como `clinic_name`.
**Regla:** antes de identificar cliente, distinguir preventa/metodología de una orden explícita. Si el usuario pregunta cómo funciona A3, responder breve y natural; solo pedir NIT cuando quiera programar. La extracción determinística de cliente debe aceptar nombres libres solo si el LLM marcó `provides_client_identifier`, hay marcador claro ("soy de X"), o parece un nombre corto real; nunca capturar motivos clínicos como clínica. Ver ERR-027.

### L35 — La señal de cliente no registrado gana antes del lookup
**Problema:** cuando el bot esperaba NIT/nombre, "No estoy registrado" se capturaba como `clinic_name` por ser una frase corta y terminaba en una búsqueda absurda contra la BD.
**Regla:** si la IA marca `new_or_unregistered_client` o el texto declara claramente que no está registrado, limpiar `clinic_name`/`tax_id` antes de consultar la BD y escalar directo a atención. Los fallbacks de nombre libre nunca deben pisar esa señal semántica. Ver ERR-030.

### L36 — Memoria multiorden no gana contra cambio explícito de cliente
**Problema:** después de cerrar una orden, frases como "otra veterinaria" u "otros clientes" podían quedar tratadas como otra orden del mismo cliente y heredar médico/dirección.
**Regla:** antes de reutilizar memoria o cerrar una confirmación, detectar cambio explícito de cliente en singular y plural (`otra veterinaria`, `otros clientes`) y reiniciar identificación. La memoria ayuda solo si el cliente sigue siendo el mismo. Ver ERR-031.

### L37 — Limpiar puentes del habla antes de buscar nombres de cliente
**Problema:** "Nombre de la clínica mía es Animal Pet" se buscaba como `Mía Es Animal Pet`, aunque `Animal Pet` sí existía.
**Regla:** al extraer nombre tras marcadores como veterinaria/clínica, quitar puentes conversacionales (`mía es`, `mi ... se llama`, `es`) antes del lookup. Si el nombre limpio matchea y la frase real no, el bug es extracción, no BD. Ver ERR-032.

### L38 — Post-cierre y memoria multiorden requieren señales explicitas y backstops
**Problema:** en retesteo real, un `sí` suelto o la palabra `orden` tras el cierre podia abrir una orden duplicada; frases compuestas como "el mismo médico y el mismo propietario" solo reutilizaban un campo; y pasos dependientes del LLM (especie ambigua, corrección con valor, perfil por etiqueta) podian repetir fallback o perder datos.
**Regla:** despues de cerrar una orden, solo iniciar seguimiento con señal explicita de nueva orden (`otra orden`, `quiero programar ruta`), no con afirmaciones ambiguas. Los datos compuestos y cierres criticos necesitan backstop deterministico que capture todos los campos del turno y retome el primer dato faltante. Ver ERR-033.

### L39 — Los guardrails de avance no deben pisar respuestas de lookup
**Problema:** un mensaje largo podia capturar datos de orden y tambien disparar lookup de cliente; si el lookup encontraba opciones, el guard de "primer faltante tras avance" reemplazaba esa respuesta por "dame NIT/nombre", ocultando las opciones.
**Regla:** cuando un paso deterministico ya produjo una respuesta especifica de identificacion (`_client_match_options` o `_client_not_found`), ningun guardrail generico de progreso debe sobrescribirla. Los extractores de cliente deben soportar marcadores naturales en frases largas (`la veterinaria ... es X`). Ver ERR-034.

### L40 — Toda frase real se procesa como paquete: datos + preguntas + BD
**Problema:** frases reales mezclan intencion, pregunta lateral, identificador de cliente y datos de orden. Si un guard de preventa corre antes del lookup, o si solo se escucha el campo que "tocaba", el bot responde humano un pedazo pero pierde datos utiles o se queda parado.
**Regla:** antes de devolver una respuesta lateral/preventa, verificar si la misma frase trae identificador (`NIT`, `soy de X`, `veterinaria ... es X`) y dejar que pase por lookup. Luego preservar la respuesta lateral y retomar con el primer dato faltante. Las conversaciones imperfectas deben vivir en `tools/scripts/diag_real_messy_flows.py`. Ver ERR-035.

### L41 — Catalogo generico no es analisis cerrado
**Problema:** `analisis de sangre` no existe como prueba unica con codigo/precio; guardarlo como `exam_type` cierra la orden con un texto libre y deja al cliente sin opciones reales. Preguntas como `que analisis hacen` tampoco deben caer en repregunta generica.
**Regla:** frases genericas de catalogo deben mostrar opciones concretas con codigo/precio y dejar `_test_menu_options` seleccionable. Si el usuario pregunta por especies/animales, responder esa duda antes de interpretar `analisis` como pedido de catalogo. Ver ERR-036.

### L42 — Una respuesta operativa fija solo aplica a PREGUNTAS, no a ordenes impacientes
**Problema:** la frase fija "Si, recogemos muestras con motorizado asignado..." se disparaba ante cualquier mencion de `recoger/recogida/motorizado`, sin distinguir una pregunta ("¿ustedes recogen?") de una orden impaciente ("programen la recogida ya", "recogela hoy"). Como la respuesta lateral no avanzaba el flujo, re-preguntaba el mismo campo → bucle; y antes de identificar, tapaba el escalado del cliente no registrado.
**Regla:** una respuesta operativa lateral solo debe dispararse si el mensaje es realmente una PREGUNTA por el servicio (signo `?`/`¿` o marcador interrogativo) y NO trae verbo imperativo de programar. Si el cliente ordena, no interceptar: dejar que el flujo capture/cierre o escale. Validar con el simulador adversarial `tools/scripts/sim_cliente.py`, no con respuestas del LLM hardcodeadas. Ver ERR-037.

### L45 — Agregar análisis a un perfil del catálogo no debe perder el precio base (ERR-039)
**Problema:** elegir un perfil del catálogo (504, $22k) y luego agregarle un análisis (1601, $16k) mostraba el total como $16k, ignorando el perfil base. La base se perdía porque el perfil quedaba en `exam_type` como texto (sin `_selected_profile_code/price`) y "agregar análisis" entraba al menú genérico de análisis sueltos, que reseteaba a "perfil a medida desde cero".
**Regla:** el total de una orden con perfil base + agregados se calcula con `calculate_profile_adjusted_total` (base + agregados − quitados), no con `calculate_custom_profile_total` (solo agregados). Si `exam_type` es un perfil del catálogo pero falta el `_selected_profile_code`, resolverlo (`_resolve_profile_base_if_missing`) ANTES de calcular el total, como backstop path-independent en `_order_summary_lines`. Excluir "Perfil personalizado…" (ese sí es desde cero). Ideal a futuro: agregar análisis a un perfil debe entrar a la personalización del base (`_profile_customizing`), no al menú de sueltos. Verificar el total reconstruyendo el estado real de la sesión, no solo el camino feliz. Ver ERR-039.

### L44 — "No sé qué pedir" necesita guard determinista; y distinguir cambio TOTAL vs PARCIAL del análisis (ERR-038)
**Problema:** el flujo "no sé / qué me recomiendas" lo resolvía el LLM: listaba perfiles amontonados en una línea, la selección quedaba sin código/precio (resumen sin valor), no respondía el precio al confirmar, y en multiorden arrastraba el perfil de otra especie. Además "no sé... perro" disparaba el detector de corrección ("no"=corregir, "perro"=paciente) y borraba el paciente.
**Regla:**
- Mostrar opciones (perfiles por especie) y capturar la selección debe ser DETERMINÍSTICO, con código y precio reales (`_store_selected_profile_fields`), para que el resumen muestre el valor. El LLM improvisa formato y pierde el código/precio.
- Un pedido de recomendación/"no sé" debe interceptarse ANTES de los detectores de corrección (que reaccionan a "no"/"perro") y ANTES de los otros guards de catálogo (que capturan el guess del modelo). Si no, el orden del pipeline gana y el guard real no dispara.
- Distinguir CAMBIO TOTAL ("otro análisis", "no sé recomiéndame" → limpiar y reofrecer desde cero por especie) de AJUSTE PARCIAL ("el mismo pero sin X", "igual más Y" → MANTENER el perfil base y solo agregar/quitar, preguntando lo que falte). Nunca limpiar todo ante un ajuste parcial: la gente dice "todo igual salvo esto". Nunca registrar un perfil de especie distinta a la del paciente.
- Validar con el modelo real reproduciendo la conversación del usuario (`diag_perfil_recomendacion.py`), no solo con tests mockeados. Ver ERR-038.

### L46 — Interpretar por contexto/intención, nunca por longitud del mensaje (ERR-040)
**Problema (corrección directa del usuario):** el cliente eligió una opción de la lista de coincidencias con una respuesta corta de confirmación ("exacto, es la primera" = opción 1) y el bot la tomó como cliente nuevo o como nombre de otra veterinaria. La causa: heurísticas que deciden por CANTIDAD de palabras (`_confirms_new_client` y `_looks_like_bare_client_name` usan "≤4 palabras"). El usuario fue explícito: "esa lógica de cuatro palabras es una mierda… mucha gente te dice cuatro palabras para decir sí; tenés que entender lo que dice, no por cuántas palabras tenga".
**Regla:**
- Nunca clasificar la intención por longitud (nº de palabras/letras). Una respuesta corta puede ser confirmación, selección, pregunta o dato — el largo no lo determina.
- Cuando hay un estado de respuesta pendiente (lista de opciones, pregunta concreta), interpretar el mensaje PRIMERO en ese contexto: si resuelve la pregunta abierta (p. ej. `_select_client_match` mapea "la primera"→opción 1), eso gana sobre reinterpretarlo como identificador/cliente nuevo. La IA interpreta el significado (`user_intent_signal`); el código hace cumplir la selección de forma determinista.
- Un "exacto/sí/dale" que acompaña una selección confirma esa selección; no es "soy cliente nuevo".
- Las heurísticas por longitud que quedan (corte de ≤4 palabras) son frágiles y deben migrarse a comprensión por contexto/señal del LLM, no parcharse con más frases. Ver ERR-040 y ERR-011.

### L43 — Testear con una IA-cliente adversarial, nunca con respuestas del LLM hardcodeadas
**Problema:** los tests que fijaban la salida del LLM (`_ai_reply(...)` con `confidence: 1.0`) siempre pasaban porque uno mismo escribia la respuesta "correcta"; afirmaban que el agente estaba bien cuando con datos reales se rompia (bucles, no escalar). Daban falsos positivos.
**Regla:** el agente conversacional se valida con modelo real respondiendo a inputs imperfectos. `tools/scripts/sim_cliente.py` pone una IA a actuar de cliente humano caotico (typos, datos en desorden, evasivo, impaciente, no registrado, particular) contra `process_turn` real, con un juez-IA que lee la transcripcion. Lo perfecto/mockeado del agente se elimino (ERR-037). Conservar solo tests de logica pura/infra (rules, db helpers, webhooks, dashboard).
