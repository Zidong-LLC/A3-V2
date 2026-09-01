# Arquitectura — A3 Laboratorio Veterinario

## Visión general

Bot conversacional de Telegram/Chatwoot para A3 Laboratorio Veterinario. Procesa mensajes entrantes,
mantiene estado de conversación en Supabase, llama a OpenAI con un JSON schema fijo,
y registra solicitudes operativas en la base de datos.

```
Telegram directo → Flask /webhooks/telegram → process_turn(channel="telegram") → Supabase/OpenAI → Telegram
Telegram vía Chatwoot → Flask /chatwoot/webhook → process_turn(channel="chatwoot") → Supabase/OpenAI → Chatwoot
```

---

## Componentes principales

### API (`app/main.py`)
- Responsabilidad: recibir webhooks de Telegram y Chatwoot, validar secret donde aplica, llamar `process_turn()`
- Estado actual: ~120 líneas por incluir webhook Chatwoot, callbacks de progreso y registro de blueprints
- No contiene lógica de negocio del agente; solo I/O HTTP y envío de respuestas

### API de plataforma (`app/platform_api.py`)
- Responsabilidad: exponer datos operativos para dashboard/plataforma interna
- Endpoints: overview de operación, clientes, solicitudes, eventos y actualización de estado
- Seguridad opcional por header `X-Platform-Token` cuando `PLATFORM_API_TOKEN` está configurado

### Agente (`app/agent.py`)
- Responsabilidad: orquestar un turno de conversación completo
- Función central: `process_turn(chat_id: str, user_message: str, on_progress=None, channel="telegram") -> str | None`
- Leer/crear sesión con canal → leer historial → aplicar guardrails determinísticos → llamar OpenAI si hace falta → guardar → devolver reply
- Estado actual: archivo grande con guardrails, catálogo/perfiles, identificación, handoff y persistencia. Refactor pendiente debe hacerse por comportamiento probado, no por tamaño ideal.

### Prompt (`app/prompt.py`)
- Responsabilidad: system prompt para OpenAI
- Solo tono, intenciones y reglas de conversación — separado del schema

### Schema (`app/schema.py`)
- Responsabilidad: JSON schema para OpenAI structured output
- Estado actual: schema amplio con fases `fase_0_bienvenida` a `fase_7_escalado`, `message_mode`, `confidence`, `pending_intents` y campos completos de orden de servicio.
- No ampliarlo sin prueba de regresión: cada campo requerido aumenta el riesgo de que el modelo priorice formato sobre conversación.

### Reglas (`app/rules.py`)
- Responsabilidad: lógica de negocio pura, sin I/O
- Calcular fecha de recogida respetando corte 17:30
- Determinar si una solicitud necesita escalado

### Config (`app/config.py`)
- Responsabilidad: leer variables de entorno, validarlas al inicio
- Falla rápido si falta alguna variable crítica

---

## Servicios (`app/services/`)

### `ai.py` — Cliente OpenAI
- Llama a `openai.chat.completions.create()` con el JSON schema
- Maneja errores de la API (rate limit, timeout)

### `db.py` — Cliente Supabase
- `get_or_create_session(chat_id, channel="telegram")` — leer/crear estado actual de conversación y persistir canal
- `get_recent_messages(chat_id, limit=8)` — últimos N mensajes
- `save_message(chat_id, text, role)` — persistir mensaje
- `update_session(chat_id, ai_response)` — actualizar fase y campos capturados
- `create_request(chat_id, session, ai_response)` — registrar solicitud operativa con `entry_channel` y `request_events.event_payload.source` según canal

### `telegram.py` — Cliente Telegram
- `send_message(chat_id, text)` — enviar respuesta al usuario
- `set_webhook(url)` — configurar webhook

### `chatwoot.py` — Cliente Chatwoot
- `send_message(conversation_id, text)` — responder en la conversación
- `assign_team(conversation_id, area)` — asignar equipo humano cuando hay handoff
- `send_typing(conversation_id)` — activar indicador de escritura

---

## Modelo de datos Supabase (producción — no modificar)

### Tablas de operación

**`clients`** — clínicas veterinarias registradas
```
id uuid PK | clinic_name text | tax_id text | phone text UNIQUE
address text | city text | zone text | billing_type (credit|cash) | is_active bool
```

**`couriers`** — motorizados
```
id uuid PK | name text | phone text UNIQUE | availability (available|busy|offline) | is_active bool
```

**`client_courier_assignment`** — asignación determinista cliente → motorizado
```
client_id uuid UNIQUE → clients | courier_id uuid → couriers | assigned_by text
```

**`requests`** — solicitudes operativas
```
id uuid PK | client_id → clients | entry_channel (telegram|chatwoot|liveconnect|manual)
service_area (route_scheduling|accounting|results|new_client|unknown)
priority text DEFAULT 'normal' | status text | exam_type text | patient_name text
pickup_address text | scheduled_pickup_date date | assigned_courier_id → couriers
fallback_reason text
```

**`request_events`** — auditoría inmutable
```
id uuid PK | request_id → requests | event_type text | event_payload jsonb | created_at timestamptz
```

### Tabla de sesión

**`telegram_sessions`** — estado activo de conversación por chat
```
channel text | external_chat_id text PK | client_id uuid → clients (nullable)
phase_current text | intent_current text | captured_fields jsonb | last_activity timestamptz
```

### Ciclo de estados de solicitud

```
received → assigned → on_route → picked_up → in_lab → processed → sent
         ↓ (sin motorizado asignado)
         error_pending_assignment
any → cancelled
```

---

## Flujo de datos por intención

### Programación de ruta (happy path)
1. Usuario: "necesito un retiro"
2. Agent identifica `route_scheduling`, fase `fase_2_recogida_datos`
3. Identifica veterinaria por `clinic_name` o `tax_id`
4. Confirma `pickup_address`
5. Genera la orden de servicio conversacional, un dato por turno
6. Pregunta forma de pago
7. Fase `fase_4_confirmacion`: muestra resumen editable y espera confirmación
8. Fase `fase_6_cierre`: crea registro en `requests`, registra `service_order` en `request_events` y asigna motorizado de `client_courier_assignment`
9. Muestra resumen final y confirma disponibilidad del bot para nuevas consultas

### Consulta de resultados
1. Usuario elige la opción 2 o pide resultados/estado de muestra.
2. la consulta de resultados busca el informe publicado del cliente y ENVÍA el PDF por el chat (app/results_lookup.py + app/results_delivery.py); si la búsqueda falla, cae al mensaje fijo por este medio.
3. No pide NIT, dirección ni datos del paciente para este flujo hasta que exista integración de resultados.

### Escalado (pagos / cliente nuevo)
1. Agent detecta intención → fase `fase_7_escalado` inmediatamente
2. Un solo mensaje claro al usuario
3. Crea registro en `requests` con `service_area = accounting|new_client`
4. `requires_handoff = true`
5. Cliente nuevo no se registra ni se captura en chat; el alta queda para recepción/plataforma.

---

## Reglas de negocio

### Hora de corte
- Corte: **17:30 hora Colombia (UTC-5)**
- Solicitud antes del corte → siguiente día hábil
- Solicitud después del corte → segundo día hábil siguiente
- Días hábiles V1: lunes a viernes (festivos no gestionados automáticamente)

### Asignación de motorizado
- Fuente de verdad: `client_courier_assignment`
- Si existe → usar ese courier → estado `assigned`
- Si no existe → estado `error_pending_assignment` + evento en `request_events` + escalar

### Identificación del cliente
- Antes de registrar cualquier solicitud, el agente debe tener `client_id`
- Si no está identificado: pedir `clinic_name` o `tax_id` primero
- Buscar en `clients` por nombre o NIT — nunca crear cliente nuevo en chat

---

## Casos de prueba obligatorios

| # | Escenario | Resultado esperado |
|---|---|---|
| 1 | Saludo simple | Bienvenida con menú 1-4 |
| 2 | Cliente con motorizado asignado | Solicitud creada, estado `assigned` |
| 3 | Cliente sin motorizado | Estado `error_pending_assignment`, evento en `request_events` |
| 4 | Cliente nuevo | `fase_7_escalado` inmediato, sin pedir datos |
| 5 | Solicitud post-17:30 | `scheduled_pickup_date` = segundo día hábil |
| 6 | Múltiples intenciones en un mensaje | Ambas procesadas en orden |
| 7 | Usuario repite sin dar dato | Agente ofrece opciones concretas |
| 8 | Gestión de pagos | Derivación inmediata a contabilidad |
| 9 | Small talk | Respuesta breve, retoma flujo |
| 10 | Conversación retomada | Sin saludo, continúa desde donde estaba |
| 11 | Webhook Chatwoot crea solicitud | `telegram_sessions.channel`, `requests.entry_channel` y evento `source` quedan en `chatwoot` |

---

## Decisiones de arquitectura

Ver [decisions/](decisions/) para el registro completo.

- [001 — Selección de stack](decisions/001-stack-selection.md)
- [002 — Forma de pago dentro del flujo conversacional](decisions/002-payment-method-in-flow.md)
- [003 — API interna para integración de plataforma](decisions/003-platform-integration-api.md)
- [005 — Orden de servicio dentro del flujo conversacional](decisions/005-service-order-conversation-flow.md)
