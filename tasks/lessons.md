# Lecciones aprendidas — A3 Laboratorio Veterinario

> Actualizar después de cada corrección del usuario.
> El objetivo es no repetir el mismo error.

---

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

### Formato de entrada

```
### L[N] — [Título del patrón]
**Problema:** [qué pasó]
**Regla:** [cómo evitarlo en el futuro]
```
