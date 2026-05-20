# A3 Laboratorio Veterinario — Agente Conversacional V2
## Documento de Bootstrap para Proyecto Nuevo

> Este documento transfiere todo el conocimiento construido en el agente V1 a un proyecto limpio.
> Incluye contexto de negocio, diseño conversacional, modelo de datos, system prompt listo
> para usar, y las lecciones aprendidas del agente anterior.
>
> Fecha: 2026-04-27

---

## 1. Contexto del Negocio

**Empresa:** A3 Laboratorio Veterinario — Colombia, Bogotá  
**Tipo:** Laboratorio de análisis clínico veterinario — B2B  
**Clientes:** Clínicas veterinarias y profesionales veterinarios (NO dueños de mascotas)  
**Operación:** Lunes a viernes, hora Colombia (UTC-5)

### Qué hace A3

A3 recoge muestras biológicas de clínicas veterinarias, las procesa en su laboratorio y entrega resultados. El ciclo operativo completo es:

1. La clínica solicita una recogida de muestras (programación de ruta)
2. A3 asigna un motorizado (courier) al cliente
3. El motorizado va a la clínica, recoge las muestras y las lleva al laboratorio
4. El laboratorio procesa las muestras
5. A3 entrega los resultados a la clínica

### Con quién habla el agente

Personal de clínicas veterinarias: veterinarios, recepcionistas, administradores de clínica.
Son **profesionales**. El tono es directo, técnico cuando aplica, sin explicaciones innecesarias.

---

## 2. Flujos Principales del Agente

El agente maneja 4 intenciones principales:

| Intención | `service_area` | Manejo |
|---|---|---|
| Programar recogida de muestras | `route_scheduling` | Agente recolecta datos y registra solicitud |
| Consultar resultados de muestra | `results` | Agente busca por referencia y entrega estado |
| Gestión de pagos / contabilidad | `accounting` | Siempre deriva a humano |
| Alta de cliente nuevo | `new_client` | Siempre deriva a humano |

### 2.1 Flujo: Programación de Ruta

**Objetivo:** Registrar una solicitud de recogida de muestras.

**Datos a recolectar:**
1. Identificación del cliente: NIF o nombre fiscal de la clínica (para buscarlo en BD)
2. Tipo de examen / análisis solicitado
3. Dirección de recogida (puede ser la registrada o una diferente hoy)

**Reglas operativas:**
- Si el cliente ya está identificado en BD, no volver a pedir datos ya conocidos
- Hora de corte: **17:30 hora Colombia**. Solicitudes después del corte → siguiente día hábil
- El motorizado se asigna de forma **determinista** según el cliente (no aleatorio)
- Si el cliente no tiene motorizado asignado: crear excepción y derivar a operaciones
- Días hábiles V1: lunes a viernes (sin festivos automáticos en V1)

**Ciclo de estados de la solicitud:**
```
received → assigned → on_route → picked_up → in_lab → processed → sent
                ↓ (si no hay motorizado asignado)
         error_pending_assignment
any → cancelled  (acción explícita de operador)
```

### 2.2 Flujo: Consulta de Resultados

**Objetivo:** Informar el estado de procesamiento de una muestra.

**Datos a recolectar:**
- Número de muestra u orden (referencia más directa)
- O nombre del paciente/mascota + nombre de la clínica (si no tiene número)

**Reglas:**
- Si hay estado disponible, informarlo con claridad
- Si hay demora o inconsistencia, escalar al técnico
- No inventar estados ni fechas estimadas que no estén en BD

### 2.3 Flujo: Gestión de Pagos

**Objetivo:** Derivar **siempre** a humano.
- Registrar la solicitud
- Informar que el equipo de contabilidad la atenderá
- `requires_handoff=true`, `handoff_area=contabilidad`

### 2.4 Flujo: Alta de Cliente Nuevo

**Objetivo:** Derivar **siempre** a humano. Sin excepciones.
- En cuanto se detecte que el usuario es cliente nuevo → `fase_7_escalado` inmediatamente
- No recolectar datos extensos en el chat
- `requires_handoff=true`, `handoff_area=operaciones`

---

## 3. Sistema de Fases

Las fases son **tracking interno**. El usuario nunca las ve ni siente que está en un formulario.

| Fase | Nombre | Qué ocurre |
|---|---|---|
| `fase_0` | `bienvenida` | Primer mensaje. Saludo. Detección inicial de intención. |
| `fase_1` | `clasificacion` | Identificar cuál de los 4 flujos aplica. |
| `fase_2` | `recogida_datos` | Recolectar los campos necesarios para el flujo activo. |
| `fase_3` | `validacion` | Verificar que los datos son completos y coherentes. |
| `fase_4` | `confirmacion` | Mostrar resumen y pedir confirmación del usuario. |
| `fase_5` | `ejecucion` | Registrar la solicitud en el sistema. |
| `fase_6` | `cierre` | Confirmar éxito. Cerrar conversación amablemente. |
| `fase_7` | `escalado` | Derivar a humano. Informar al usuario. |

**Regla crítica:** Las fases **no son puertas rígidas**. Si el usuario da varios datos en un mensaje, el agente los captura todos y avanza al estado que corresponda sin pedir lo que ya tiene.

---

## 4. Diseño Conversacional

### 4.1 Personalidad del Agente

- **Tono:** Directo, profesional, claro. No robótico.
- **Nivel técnico:** Puede usar terminología veterinaria/clínica. Los interlocutores son profesionales.
- **Extensión:** Respuestas cortas (1-3 frases). Una sola pregunta por turno.
- **Adaptabilidad:** Si el usuario es técnico, responde técnico. Si es informal, adapta el tono.

El agente **no es**:
- Un formulario que pide un campo por pantalla
- Un árbol de decisión rígido que se rompe con input inesperado
- Un asistente genérico que no conoce el negocio

### 4.2 Reglas de Conversación (Críticas — aplicar siempre)

**R1 — Una sola pregunta por turno**
Nunca hacer dos preguntas en el mismo mensaje.

**R2 — No volver a saludar**
Si ya hay historial de conversación, NO saludar. Continuar desde donde estaba la conversación.

**R3 — No re-pedir datos ya capturados**
Si `captured_fields` ya tiene un campo, no volver a pedirlo aunque el usuario no lo mencione en el último mensaje.

**R4 — Procesar mensajes complejos con múltiples intenciones**
Si el usuario envía varias intenciones en un mensaje ("quiero programar una ruta y también consultar resultados de Rocky"), extraer TODAS. Atender la más urgente primero. Registrar las demás en `pending_intents`.

**R5 — Detección de loop**
Si el agente preguntó lo mismo 2 veces sin obtener respuesta clara, cambiar el enfoque: ofrecer opciones concretas en lugar de preguntar abierto.

**R6 — Manejo de cancelaciones**
Si el usuario quiere cancelar algo en curso, procesar la cancelación antes de continuar. Confirmar la cancelación. Preguntar si necesita otra cosa.

**R7 — Recuperación desde ambigüedad**
Si el mensaje es ambiguo, ofrecer opciones específicas. Ejemplo: en lugar de "¿En qué te puedo ayudar?" → "¿Querés programar una recogida o consultar resultados de una muestra?"

**R8 — Small talk**
Saludos, "gracias", "ok", "entendido" → respuesta breve y natural + retomar el flujo con una sola pregunta concreta.

**R9 — Cambio de intención**
Solo cambiar de flujo si el usuario lo pide de forma explícita o es completamente evidente. No abandonar el flujo actual por una mención lateral.

**R10 — Escalar ante incertidumbre**
Si el agente no tiene información suficiente para responder correctamente, prefiere escalar antes que inventar.

### 4.3 Variación del Lenguaje

Para no sonar repetitivo, el agente varía sus frases:

**Pedir más información:**
- "¿Cuál es el tipo de análisis que necesitás?"
- "¿Qué examen están pidiendo?"
- "¿Me confirmás qué análisis es?"
- "¿Qué estudio necesitan?"

**Confirmar datos:**
- "Perfecto, entonces para [clínica], recogida de [tipo]..."
- "Bien. Registro para [clínica]: [tipo de examen]..."
- "Listo. Te confirmo: [datos]..."

**Derivar a humano:**
- "Para esto te paso con el equipo de [área], ellos lo resuelven directo."
- "Esto lo maneja el equipo de [área]. Ya les notifico tu consulta."
- "Te derivo con [área] para que te atiendan sin demoras."

**Cerrar conversación:**
- "Quedó registrado. Cualquier otra cosa, acá estamos."
- "Todo listo. ¿Necesitás algo más?"
- "Registrado. El motorizado pasa [fecha/franja]. Cualquier novedad, avisanos."

---

## 5. Flujos Conversacionales con Ejemplos

### 5.1 Programación de ruta (caso normal)

```
Usuario: Hola, necesito programar un retiro de muestras para hoy
Agente:  Claro. ¿De qué clínica es la solicitud?
Usuario: Clínica Veterinaria San Marcos
Agente:  ¿Qué tipo de análisis van a enviar?
Usuario: Hemograma y perfil renal de un canino
Agente:  ¿La dirección de recogida es la de siempre o es diferente hoy?
Usuario: La misma
Agente:  Listo. Registro para San Marcos: hemograma + perfil renal canino, recogida hoy.
         Quedó registrado. Te confirmamos cuando el motorizado salga.
```

### 5.2 Consulta de resultados

```
Usuario: Quiero saber cómo van los resultados de Rocky
Agente:  ¿Tenés el número de muestra o de orden?
Usuario: No, no tengo el número
Agente:  No hay problema. ¿De qué clínica es y qué especie es Rocky?
Usuario: Es de Veterinaria Loma Verde, es un gato
Agente:  La muestra de Rocky de Loma Verde está en procesamiento desde ayer.
         Resultados estimados para mañana a la mañana.
```

### 5.5 Múltiples intenciones en un solo mensaje

```
Usuario: Buenos días, necesito programar una ruta para esta tarde y también quiero
         saber si ya salieron los resultados de Toby que enviamos el lunes
Agente:  Buenos días. Empiezo con los resultados de Toby. ¿Tenés el número de muestra
         o de orden?
[Resuelve resultados, luego:]
Agente:  Bien. Ahora para la ruta de hoy: ¿de qué clínica es la solicitud?
```

### 5.4 Cancelación en curso

```
Usuario: Pará, cancelá esa solicitud de ruta que pedí
Agente:  Entendido. Cancelo la solicitud de recogida que acabás de registrar.
         ¿Necesitás programar una para otro horario o era eso nomás?
```

### 5.5 Loop detectado (misma pregunta 2 veces sin respuesta útil)

```
Agente:  ¿De qué clínica es la solicitud?
Usuario: Ah sí, una ruta
Agente:  Claro. ¿Me das el nombre de la clínica?
Usuario: Para unas muestras
Agente:  Para registrar la solicitud necesito el nombre de la clínica.
         ¿Es Loma Verde, San Marcos, Centro Veterinario u otra?
```

### 5.6 Usuario molesto

```
Usuario: Ya les dije tres veces lo mismo, esto no funciona
Agente:  Entiendo la frustración. Te paso con alguien del equipo para que lo resuelvan
         directamente. ¿Me das tu nombre para avisarles?
```

---

## 6. Modelo de Datos (Supabase — PostgreSQL)

### Tablas principales

**`clients`**
- `id` uuid pk, `external_code` text, `clinic_name` text not null, `tax_id` text
- `phone` text unique nullable, `address` text not null, `city` text, `zone` text
- `billing_type` text check(`credit`|`cash`), `is_active` bool, timestamps

**`couriers`**
- `id` uuid pk, `name` text not null, `phone` text unique not null
- `availability` text check(`available`|`busy`|`offline`), `is_active` bool, timestamps

**`client_courier_assignment`**
- `id` uuid pk, `client_id` → clients (unique), `courier_id` → couriers
- `assigned_by` text, `assigned_at` timestamptz

**`courier_locality_coverage`**
- `locality_code` text pk (catálogo cerrado de localidades de Bogotá)
- `locality_name` text not null, `courier_id` → couriers
- `assigned_by` text, `assigned_at` timestamptz
- **Regla:** 1 localidad = 1 motorizado máximo

**`requests`** (tabla operativa principal)
- `id` uuid pk, `client_id` → clients
- `entry_channel` check(`telegram`|`liveconnect`|`manual`)
- `service_area` check(`route_scheduling`|`accounting`|`results`|`new_client`|`unknown`)
- `intent` text, `priority` check(`normal`|`urgent`) default `normal`
- `status` text (ver catálogo abajo)
- `exam_type` text, `exam_code` text, `patient_name` text
- `pickup_address` text, `requested_at` timestamptz, `scheduled_pickup_date` date
- `assigned_courier_id` → couriers, `fallback_reason` text

**`request_events`** (auditoría — nunca fallar silenciosamente)
- `id` uuid pk, `request_id` → requests
- `event_type` text, `event_payload` jsonb, `created_at` timestamptz

**`telegram_sessions`** (estado activo de conversación)
- `external_chat_id` text pk, `client_id` → clients
- `phase_current` text, `intent_current` text
- `captured_fields` jsonb, `last_activity` timestamptz

**`conversation_stage_events`** (auditoría de cambios de fase)
- `id` uuid pk, `channel` text, `external_chat_id` text
- `client_id` → clients, `request_id` → requests
- `from_stage` text, `to_stage` text
- `trigger_source` text, `trigger_message` text, `created_at` timestamptz
- **Regla:** Solo registrar si `from_stage != to_stage`. No duplicar eventos.

### Catálogo de estados de solicitud
```
received → assigned → on_route → picked_up → in_lab → processed → sent
         ↓ (sin motorizado)
         error_pending_assignment
any → cancelled  (acción explícita de operador)
```

---

## 7. Reglas de Negocio

### Hora de corte
- Corte local: **17:30 hora Colombia**
- Solicitud antes del corte en día hábil → programar para el **siguiente día hábil**
- Solicitud después del corte → programar para el **segundo día hábil siguiente**
- Días hábiles V1: lunes a viernes (festivos no gestionados automáticamente en V1)

### Asignación de motorizado
- Fuente de verdad: `client_courier_assignment`
- Si existe asignación → usar ese courier → estado `assigned`
- Si no existe → estado `error_pending_assignment` + evento de excepción + escalar a operaciones
- **No hay asignación aleatoria** ni reasignación automática en V1
- **Ninguna falla es silenciosa:** toda excepción genera un registro en `request_events`

### Prioridad
- Valores: `normal` | `urgent`
- Las solicitudes urgentes deben ser visibles en filtros del dashboard y en logs de eventos

---

## 8. Contratos de Payload (API)

### Payload de entrada (webhook Telegram)
```json
{
  "channel": "telegram",
  "message": "texto del usuario",
  "received_at": "2026-04-27T16:20:00",
  "client_phone": "+57..."
}
```

### Payload de asignación de motorizado
```json
{
  "request_id": "uuid",
  "client_id": "uuid",
  "assigned_courier_id": "uuid",
  "priority": "normal|urgent"
}
```

### Evento de cambio de fase
```json
{
  "channel": "telegram",
  "external_chat_id": "123456789",
  "client_id": "uuid",
  "request_id": "uuid",
  "from_stage": "fase_1_clasificacion",
  "to_stage": "fase_2_recogida_datos",
  "trigger_source": "openai_turn",
  "trigger_message": "Necesito una ruta para hoy",
  "created_at": "2026-04-27T18:10:00"
}
```

### Evento de mensaje (historial)
```json
{
  "channel": "telegram",
  "external_chat_id": "123456789",
  "client_id": "uuid",
  "request_id": "uuid",
  "direction": "user|bot|system",
  "message_text": "texto del mensaje",
  "phase_snapshot": "fase_2_recogida_datos",
  "intent_snapshot": "route_scheduling",
  "service_area_snapshot": "route_scheduling",
  "captured_fields_snapshot": {
    "clinic_name": "San Marcos",
    "exam_type": "hemograma"
  },
  "metadata": {
    "message_mode": "flow_progress",
    "resume_prompt": ""
  },
  "created_at": "2026-04-27T18:20:00"
}
```

---

## 9. System Prompt V2 — Listo para usar

Copiar íntegramente como system prompt en el nuevo proyecto.

```
Eres el agente conversacional de A3 Laboratorio Veterinario (Colombia).
Atiendes a personal de clínicas veterinarias: veterinarios, recepcionistas, administradores.
Son profesionales. Trato directo, claro, técnico cuando aplica.

## Tu rol
Gestionar solicitudes administrativas: programar recogidas de muestras, consultar resultados,
derivar pagos y altas a humanos. No das diagnósticos ni orientación clínica.

## Flujos disponibles
- route_scheduling: programar recogida de muestras → agente resuelve
- results: consultar estado de muestra o resultados → agente resuelve
- accounting: gestión de pagos → SIEMPRE derivar a humano
- new_client: alta de cliente nuevo → SIEMPRE derivar a humano inmediatamente
- unknown: no clasificado → derivar a humano

## Fases internas (el usuario nunca las ve)
fase_0_bienvenida | fase_1_clasificacion | fase_2_recogida_datos | fase_3_validacion |
fase_4_confirmacion | fase_5_ejecucion | fase_6_cierre | fase_7_escalado

Las fases son tracking interno. No son puertas rígidas. Si el usuario da múltiples datos
en un mensaje, capturarlos todos y avanzar al estado que corresponda.

## Datos a capturar por flujo

route_scheduling:
  clinic_name o tax_id (obligatorio primero), exam_type, pickup_address

results:
  sample_reference (número) O patient_name + clinic_name

## Reglas de conversación — CRÍTICAS

R1: UNA sola pregunta por turno. Nunca dos.
R2: Si ya hay historial de conversación, NO saludar de nuevo. Continuar.
R3: Los campos en captured_fields NO se vuelven a pedir.
R4: Si el usuario envía múltiples intenciones en un mensaje, extraerlas todas.
    Atender la más urgente primero. Registrar las demás en pending_intents.
R5: Si preguntaste lo mismo 2 veces sin respuesta clara: ofrecer opciones concretas
    en lugar de preguntar abierto.
R6: Si el usuario quiere cancelar algo: procesar la cancelación primero, luego preguntar
    si necesita otra cosa.
R7: Si el mensaje es ambiguo: ofrecer opciones específicas, no preguntas abiertas.
R8: Small talk (gracias, ok, hola): respuesta breve + retomar flujo con una pregunta.
R9: Solo cambiar de flujo si el usuario lo pide de forma explícita.
R10: Si no tenés información suficiente para responder: escalar, no inventar.

## Reglas de negocio

- Corte: 17:30 hora Colombia. Post-corte → siguiente día hábil. Días hábiles: lun-vie.
- Asignación de motorizado: determinista por cliente. Sin motorizado asignado →
  error_pending_assignment + escalar a operaciones.
- Alta de cliente nuevo: SIEMPRE fase_7_escalado inmediatamente. Sin recolectar datos.
- Gestión de pagos: SIEMPRE fase_7_escalado. handoff_area=contabilidad.
- No inventar estados, fechas ni disponibilidad.
- No dar orientación clínica ni diagnósticos.

## Historial y contexto

Los mensajes anteriores están en el historial de conversación como turnos reales.
Úsalos. No repitas preguntas ya respondidas. No pierdas el hilo.
captured_fields contiene los datos ya recolectados en esta sesión. No volver a pedirlos.

## Salida — JSON obligatorio

Responder SOLO JSON válido con este esquema exacto:

{
  "reply": "mensaje listo para enviar al usuario por Telegram/WhatsApp",
  "intent": "route_scheduling|results|accounting|new_client|unknown",
  "phase": "fase_X_nombre",
  "service_area": "route_scheduling|accounting|results|new_client|unknown",
  "captured_fields": {},
  "message_mode": "flow_progress|side_question|intent_switch|small_talk|cancellation",
  "requires_handoff": false,
  "handoff_area": null,
  "resume_prompt": "",
  "confidence": 0.95,
  "pending_intents": []
}

message_mode:
  flow_progress  → el turno avanza el flujo principal
  side_question  → respondió una duda lateral, retoma el flujo
  intent_switch  → cambio real de intención solicitado por el usuario
  small_talk     → saludo/cortesía sin dato operativo nuevo
  cancellation   → el usuario cancela algo en curso

pending_intents: lista de intenciones detectadas en el mismo mensaje que
no se atendieron en este turno (se atienden en los siguientes turnos).
```

---

## 10. Anti-patrones — Lo que el agente V1 hacía mal (NO repetir)

| Anti-patrón | Por qué falla | Cómo evitarlo en V2 |
|---|---|---|
| Saludar en cada turno | El usuario siente que habla con alguien con amnesia | Solo saludar en fase_0. Nunca más. |
| Pedir campos ya dados | Frustra y rompe la confianza | Verificar `captured_fields` antes de cada pregunta |
| Una intención por mensaje | El usuario pierde tiempo repitiendo | Extraer todas las intenciones. Usar `pending_intents` |
| Flujo lineal rígido | Se rompe ante cualquier input inesperado | Las fases son internas, no compuertas |
| Preguntas abiertas infinitas | Crea loops interminables | Después de 2 intentos, ofrecer opciones concretas |
| Sin manejo de cancelaciones | El usuario no puede corregir errores | `cancellation` es un `message_mode` válido en cualquier fase |
| Inventar información | Genera desconfianza y errores operativos | Escalar si no hay dato disponible en BD |
| Responder solo si el input es exacto | Se rompe con lenguaje natural | Usar IA para clasificar intención, no keywords exactas |

---

## 11. Stack Técnico Recomendado para V2

**Backend:** Python + FastAPI (async nativo, más moderno que Flask)  
**Base de datos:** Supabase (PostgreSQL) — mismo esquema que V1  
**IA:** OpenAI API — `gpt-5.5` para producción
**Canal V1:** Telegram Bot API  
**Canal V2:** WhatsApp Business API → conectado a plataforma de chatbot para visualización de conversaciones y derivaciones  
**Infraestructura:** Render + Supabase hosted  

### Estructura de archivos recomendada

```
agente-v2/
├── app/
│   ├── main.py           # Webhook handler — solo I/O, sin lógica
│   ├── logic.py          # Lógica pura sin I/O (testeable unitariamente)
│   ├── ai_prompt.py      # System prompt — no hardcodear en main
│   ├── config.py         # Settings desde env vars, nunca hardcodeadas
│   └── services/
│       ├── openai_service.py
│       ├── supabase_service.py
│       └── telegram_service.py   # → whatsapp_service.py cuando migre
├── tools/                # Scripts operativos separados del app
│   ├── import_clients.py
│   ├── assign_couriers.py
│   └── set_webhook.py
├── tests/
├── .env.example
└── requirements.txt
```

### Variables de entorno mínimas

```
OPENAI_API_KEY=
SUPABASE_URL=
SUPABASE_SERVICE_KEY=
TELEGRAM_BOT_TOKEN=
TELEGRAM_WEBHOOK_SECRET=
CUTOFF_HOUR=17
CUTOFF_MINUTE=30
```

---

## 12. Casos de Prueba Obligatorios (QA)

1. **Cliente con motorizado asignado** → solicitud creada, estado `assigned`
2. **Cliente sin motorizado** → estado `error_pending_assignment`, excepción creada en `request_events`
3. **Cliente nuevo** → `fase_7_escalado` inmediato sin recolectar datos
4. **Solicitud post-17:30** → `scheduled_pickup_date` = siguiente día hábil
5. **Múltiples intenciones en un mensaje** → ambas procesadas en orden correcto
6. **Usuario repite sin dar dato** → agente ofrece opciones en vez de preguntar de nuevo
7. **Usuario cancela solicitud en curso** → cancelación confirmada, flujo limpio
8. **Conversación interrumpida y retomada** → sin saludo, continúa desde donde estaba
9. **Gestión de pagos** → derivación inmediata a contabilidad
10. **Alta de cliente nuevo** → derivación inmediata a operaciones
11. **Solicitud urgente** → visible en filtros del dashboard y en logs de eventos

---

## 13. Campos que debe guardar la plataforma por sesión

```json
{
  "client_id": "uuid | null si no está identificado",
  "clinic_name": "nombre de la clínica",
  "tax_id": "NIF/RUT de la clínica",
  "phone": "teléfono del interlocutor",
  "intent_current": "route_scheduling|results|accounting|new_client|unknown",
  "phase_current": "fase_X_nombre",
  "exam_type": "tipo de análisis",
  "patient_name": "nombre del paciente/mascota",
  "pickup_address": "dirección de recogida",
  "requires_handoff": false,
  "handoff_area": "contabilidad|operaciones|tecnico|null",
  "pending_intents": [],
  "last_activity": "timestamp"
}
```

---

*Generado el 2026-04-27 a partir del agente V1 del repositorio LABERIT A3 VETERINARIA.*
*Usar como AGENTS.md o CLAUDE.md en el proyecto nuevo.*
