# A3 Laboratorio Veterinario — Instrucciones para el Agente de IA

> Este archivo es el equivalente de CLAUDE.md para OpenCode (ChatGPT).
> Contiene todo el contexto necesario para trabajar en este proyecto.

---

## Qué es este proyecto

**A3 Laboratorio Veterinario** — laboratorio de análisis clínico veterinario en Bogotá.
Atiende clínicas y veterinarias por Telegram directo y por Telegram vía Chatwoot.

El bot hace exactamente 4 cosas:
1. Programar recogida de muestras
2. Consultar resultados
3. Pagos/facturación → **siempre escala a contabilidad** (nunca resuelve en chat)
4. Cliente nuevo → **siempre escala a recepción** (nunca registra en chat)

---

## Stack (no cambiar)

```
Backend:       Python 3.12+ + Flask
Base de datos: Supabase (PostgreSQL) — modelo existente, no modificar esquema
IA:            OpenAI API — gpt-5.5
Mensajería:    Telegram Bot API + Chatwoot Agent Bot (webhooks)
Infra:         Render
```

---

## Arquitectura

```
app/main.py          Flask + webhooks Telegram/Chatwoot
app/agent.py         process_turn() — función central con guardrails determinísticos
app/prompt.py        System prompt
app/schema.py        JSON schema OpenAI amplio (estado actual)
app/rules.py         Reglas de negocio puras
app/config.py        Variables de entorno
app/services/ai.py   Cliente OpenAI
app/services/db.py   Cliente Supabase
app/services/telegram.py  Cliente Telegram
app/services/chatwoot.py  Cliente Chatwoot
```

La función `process_turn(chat_id, user_message, on_progress=None, channel="telegram") -> str | None` es el corazón del sistema.

---

## Modelo de datos Supabase (solo lectura — no modificar esquema)

```sql
clients:              id, clinic_name, tax_id, phone, address, zone, billing_type, is_active
couriers:             id, name, phone, availability, is_active
client_courier_assignment: client_id (UNIQUE) → courier_id  (asignación determinista)
requests:             id, client_id, entry_channel, service_area, intent, priority, status,
                      exam_type, patient_name, pickup_address, scheduled_pickup_date,
                      assigned_courier_id, fallback_reason
request_events:       id, request_id, event_type, event_payload, created_at
telegram_sessions:    channel, external_chat_id (PK), client_id, phase_current,
                      intent_current, captured_fields, last_activity
```

Estados de solicitud: `received → assigned → on_route → picked_up → in_lab → processed → sent`
Error: `error_pending_assignment` (cliente sin motorizado)

---

## Fases del agente (tracking interno, el usuario nunca las ve)

| Fase | Estado |
|---|---|
| `fase_0_bienvenida` | Primer mensaje y menú |
| `fase_1_clasificacion` | Clasificación de intención |
| `fase_2_recogida_datos` | Recolección de datos |
| `fase_3_validacion` | Validación/coherencia |
| `fase_4_confirmacion` | Resumen editable |
| `fase_5_ejecucion` | Ejecución interna |
| `fase_6_cierre` | Solicitud registrada/cierre |
| `fase_7_escalado` | Derivado a humano |

---

## JSON schema de respuesta OpenAI

```json
{
  "reply": "mensaje para enviar al usuario",
  "intent": "route_scheduling|results|accounting|new_client|unknown",
  "phase": "fase_0_bienvenida|fase_1_clasificacion|fase_2_recogida_datos|fase_3_validacion|fase_4_confirmacion|fase_5_ejecucion|fase_6_cierre|fase_7_escalado",
  "service_area": "route_scheduling|accounting|results|new_client|unknown",
  "captured_fields": {
    "clinic_name": null, "tax_id": null, "pickup_address": null,
    "exam_type": null, "patient_name": null,
    "species": null, "requesting_doctor": null, "patient_age": null,
    "owner_name": null, "breed": null, "sex": null,
    "observations": null, "payment_method": null,
    "selected_tests": null, "removed_tests": null
  },
  "message_mode": "flow_progress|side_question|intent_switch|small_talk|cancellation",
  "requires_handoff": false,
  "handoff_area": null,
  "resume_prompt": "",
  "confidence": 1.0,
  "pending_intents": []
}
```

---

## Reglas de negocio invariantes

1. **Corte 17:30** — solicitudes post-corte van al segundo día hábil siguiente
2. **Motorizado determinista** — tabla `client_courier_assignment`. Sin motorizado → `error_pending_assignment` + escalar
3. **Alta de cliente** — SIEMPRE escala a recepción. El bot nunca registra.
4. **Contabilidad** — SIEMPRE escala. El bot nunca resuelve pagos.
5. **Identificación** — conocer el cliente antes de registrar cualquier solicitud

---

## Reglas de conversación (críticas)

- Una sola pregunta por turno. Nunca dos.
- No repetir preguntas ya respondidas. Usar `captured_fields`.
- No saludar si ya hay historial de conversación.
- Ante ambigüedad: ofrecer opciones concretas, no preguntas abiertas.
- Si preguntó lo mismo 2 veces sin respuesta: ofrecer opciones específicas.
- Cuando deriva a humano: un solo mensaje claro, sin pedir más datos.

---

## Reglas de trabajo para el asistente de IA

- Responder siempre en **español**
- Archivos < 200 líneas, una responsabilidad por archivo
- Cambios mínimos al corregir bugs (modificar la menor cantidad de líneas posible)
- No modificar el esquema de Supabase
- No agregar dependencias sin confirmar
- Preferir editar archivos existentes antes de crear nuevos
- Documentar decisiones importantes en `docs/decisions/`
- Consultar `tasks/lessons.md` antes de empezar una tarea nueva
- **Bitácora central de errores:** consultar `tasks/errores-soluciones.md` ANTES de tocar el agente (errores ya resueltos + abiertos/monitoreo, para no repetirlos) y registrar AHÍ todo bug conversacional (síntoma, causa raíz, solución, tests, estado). Sin actualizarla, el bug no se considera cerrado. Ver `docs/decisions/007-error-solution-log.md`.

---

## Fuera de alcance V1

- Integración Anarvet
- Envío automático de PDFs
- Workflow contabilidad automatizado
- Dashboard operativo
- WhatsApp
- Audio/voz

---

## Recursos útiles

- **Bitácora central de errores (leer primero): `tasks/errores-soluciones.md`**
- Arquitectura completa: `docs/architecture.md`
- Casos de prueba: `docs/architecture.md#casos-de-prueba`
- Lecciones aprendidas: `tasks/lessons.md`
- Contexto de negocio detallado: `docs/contexto-negocio.md`
- Bootstrap completo del agente V2: `docs/agente-v2-bootstrap.md`
