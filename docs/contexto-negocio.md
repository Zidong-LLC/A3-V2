# Contexto: Nuevo Agente Conversacional A3 Veterinaria

> Documento de traspaso generado el 2026-04-26.
> Base: proyecto actual `DESARROLLO-A3/1-agente-conversacional/` (descartado por sobrescritura acumulada).
> Uso: iniciar el nuevo proyecto desde cero con todo el conocimiento de negocio ya mapeado.

---

## 1. Qué es A3

**A3 Laboratorio Veterinario** — laboratorio de análisis clínico veterinario en Colombia (Bogotá).

**Sus clientes**: clínicas y veterinarias que necesitan enviar muestras para análisis (sangre, orina, histopatología, etc.). No son pacientes individuales; son negocios con nombre fiscal / NIT.

**Cómo opera**:
- El laboratorio tiene **motorizados** (mensajeros) asignados por zona/cliente.
- Los motorizados **retiran muestras** en la clínica y las llevan al laboratorio.
- El laboratorio procesa y devuelve **resultados** (PDF/portal).
- Hay un equipo interno (recepción, contabilidad, técnicos) que gestiona lo que el bot no puede resolver.

---

## 2. Para qué sirve el agente

El agente atiende a los clientes de A3 por **Telegram** (y en futuro WhatsApp conectado a chatwoot). No reemplaza al equipo; filtra y gestiona lo que puede resolver solo, y escala lo que no puede.

### Cuatro cosas que el agente hace (y solo cuatro)

| Intención | Qué quiere el cliente | Qué hace el agente |
|---|---|---|
| **Programar recogida** | "Necesito que vengan a retirar muestras" | Recolecta datos mínimos, registra la solicitud, confirma fecha/franja |
| **Consultar resultados** | "¿Ya están listos los resultados de Rocky?" | Pide referencia si no la tiene, informa estado actual |
| **Gestión de pagos** | "Tengo una duda sobre mi factura" | Escala siempre a contabilidad (no resuelve en chat) |
| **Cliente nuevo** | "Somos una clínica nueva" | Escala siempre a recepción (no hace el alta en chat) |

Si el mensaje no encaja en ninguna de las cuatro, el agente pide aclaración o escala.

---

## 3. Lo que NO funcionó en el proyecto anterior (razón del reset)

El agente anterior tenía el flujo conceptualmente correcto pero falló en la ejecución porque:

1. **Era un robot con menú, no una conversación** — respondía con estructura A→B→C predecible y rígida. El cliente siente que está llenando un formulario, no hablando con alguien.

2. **Sobreingeniería de fases** — 8 fases internas (fase_0 a fase_7) que el modelo de IA tenía que mantener en sync con la BD. Cualquier desincronía rompía el flujo y era difícil de depurar.

3. **El JSON schema era demasiado restrictivo** — el modelo OpenAI tenía que devolver 14 campos siempre, incluyendo `phase_next`, `message_mode`, `resume_prompt`, `confidence`, etc. Esto hacía que el modelo prestara más atención al formato que a la respuesta en sí.

4. **Lógica fragmentada entre demasiados archivos** — `main.py` (307 KB), `logic.py`, `ai_prompt.py`, `openai_service.py`, cada uno con partes del flujo. Era imposible razonar sobre el comportamiento completo sin leer todo.

5. **El system prompt mezclaba instrucciones de tono con instrucciones de schema** — el modelo no podía priorizar bien.

---

## 4. Principios para el nuevo agente

### 4.1 Primero persona, luego proceso

El agente debe sonar como un humano del equipo de A3, no como un IVR de banco. Tono: cercano, profesional, colombiano. Ejemplos de cómo debería sonar:

- ❌ Robótico: "Para continuar necesito los siguientes datos: (1) Nombre de la clínica, (2) NIT, (3) Dirección de recogida."
- ✅ Conversacional: "Claro, con gusto le coordino el retiro. ¿Me confirma desde qué clínica saldrían las muestras?"

### 4.2 Una sola pregunta por turno

El agente NUNCA hace dos preguntas en el mismo mensaje. Si le faltan tres datos, pregunta el más importante y espera respuesta.

### 4.3 Memoria de conversación real

El agente no repite preguntas ya respondidas. Si el cliente ya dijo "soy de Clínica Patas Felices", no vuelve a preguntar el nombre.

### 4.4 Handoff limpio

Cuando no puede resolver algo, lo dice claramente y en un solo mensaje: "Esto lo maneja directamente nuestro equipo de contabilidad, te van a escribir en breve." No pide datos antes de escalar si no los necesita.

### 4.5 Simplicidad técnica sobre completitud de schema

El nuevo agente debe devolver **menos campos** del modelo de IA, pero usarlos bien. Es mejor un JSON de 4 campos que funcione que uno de 14 que el modelo llene con valores inventados.

---

## 5. Modelo de datos Supabase (conservar exactamente)

Este modelo YA EXISTE en Supabase producción. No se cambia.

### Tablas principales

```sql
-- Clientes (clínicas veterinarias)
clients:
  id uuid pk
  external_code text
  clinic_name text NOT NULL
  tax_id text                         -- NIT
  phone text unique
  address text NOT NULL
  city text
  zone text
  billing_type text CHECK IN ('credit', 'cash')
  is_active boolean DEFAULT true

-- Motorizados
couriers:
  id uuid pk
  name text NOT NULL
  phone text unique NOT NULL
  availability text CHECK IN ('available', 'busy', 'offline')
  is_active boolean DEFAULT true

-- Asignación cliente → motorizado (determinista, no random)
client_courier_assignment:
  id uuid pk
  client_id uuid → clients.id UNIQUE
  courier_id uuid → couriers.id
  assigned_by text
  assigned_at timestamptz

-- Solicitudes operativas
requests:
  id uuid pk
  client_id uuid → clients.id
  entry_channel text CHECK IN ('telegram', 'liveconnect', 'manual')
  service_area text CHECK IN ('route_scheduling', 'accounting', 'results', 'new_client', 'unknown')
  intent text
  priority text CHECK IN ('normal', 'urgent') DEFAULT 'normal'
  status text
  exam_type text
  patient_name text
  pickup_address text
  requested_at timestamptz
  scheduled_pickup_date date
  assigned_courier_id uuid → couriers.id
  fallback_reason text

-- Eventos de auditoría
request_events:
  id uuid pk
  request_id uuid → requests.id
  event_type text
  event_payload jsonb
  created_at timestamptz
```

### Estados de una solicitud (lifecycle)
```
received → assigned → on_route → picked_up → in_lab → processed → sent
received → error_pending_assignment  (cliente sin motorizado asignado)
cualquier estado → cancelled
```

### Sesión de Telegram
```sql
telegram_sessions:
  external_chat_id text pk
  client_id uuid (nullable si no está identificado)
  phase_current text
  intent_current text
  captured_fields jsonb
  last_active_at timestamptz
```

---

## 6. Reglas de negocio (invariantes que no cambian)

1. **Corte a las 17:30** — solicitudes recibidas después de las 17:30 se programan para el siguiente día hábil + 1 (no el siguiente, el que sigue).

2. **Asignación de motorizado es determinista** — si el cliente tiene motorizado asignado en `client_courier_assignment`, ese es el que va. No hay selección aleatoria. Si no tiene asignado, se crea estado `error_pending_assignment` y se escala a operaciones.

3. **Alta de cliente SIEMPRE escala** — el bot nunca hace el alta. Deriva a recepción sin recolectar datos extensos.

4. **Contabilidad SIEMPRE escala** — el bot no resuelve temas de facturación ni pagos en chat.

5. **Identificación del cliente** — antes de registrar una solicitud de ruta, el agente necesita saber quién es el cliente (NIT o nombre fiscal de la veterinaria). Si no se sabe, preguntar primero esto.

6. **Localidades de Bogotá** — la cobertura de motorizados es por localidad. `1 localidad = 1 motorizado`. Si la localidad no tiene cobertura, el cliente queda sin asignar.

---

## 7. Campos a recolectar por intención

### Programar recogida de muestras
Campos obligatorios (mínimos para crear la solicitud):
- `clinic_name` o `tax_id` — identificación del cliente
- `pickup_address` — dirección de recogida
- `exam_type` — tipo de análisis (puede ser general al inicio)
Campos opcionales pero deseables:
- `time_window` — franja horaria preferida
- `patient_name` — nombre de la mascota/paciente

### Consultar resultados
Necesita al menos UNO de:
- `sample_reference` — número de muestra (ej: "12345")
- `order_reference` — número de orden
- `patient_name` — nombre del paciente (si no tiene número)

### Gestión de pagos / Cliente nuevo
No recolectar datos. Solo confirmar que se escala y quién los contactará.

---

## 8. Stack técnico recomendado para el nuevo proyecto

Mantener el mismo stack (no hay razón para cambiarlo, funcionó bien):

```
Backend:        Python 3.12+ + Flask
Base de datos:  Supabase (PostgreSQL) — mismo proyecto, mismas tablas
IA:             OpenAI API — modelo gpt-5.5 (rápido, barato, suficiente)
Mensajería:     Telegram Bot API (webhook)
Infra:          Render (web service)
```

### Variables de entorno necesarias
```
TELEGRAM_BOT_TOKEN
TELEGRAM_WEBHOOK_SECRET
SUPABASE_URL
SUPABASE_SERVICE_ROLE_KEY
OPENAI_API_KEY
OPENAI_MODEL=gpt-5.5
APP_TIMEZONE=America/Bogota
CUTOFF_TIME=17:30
FLASK_SECRET_KEY
```

---

## 9. Arquitectura simplificada para el nuevo agente

En lugar del `main.py` de 307KB con todo mezclado, separar en archivos pequeños y con responsabilidad única:

```
nuevo-agente/
├── app/
│   ├── main.py              # Solo: Flask app, rutas, webhook handler (< 100 líneas)
│   ├── agent.py             # La única función importante: process_turn()
│   ├── prompt.py            # System prompt — solo tono e intenciones, sin schema
│   ├── schema.py            # El JSON schema para OpenAI — separado del prompt
│   ├── rules.py             # Reglas de negocio puras (cutoff, asignación)
│   ├── config.py            # Settings desde env vars
│   └── services/
│       ├── openai.py        # Cliente OpenAI — solo llama a la API
│       ├── supabase.py      # Cliente Supabase — solo queries
│       └── telegram.py      # Cliente Telegram — solo envía mensajes
└── requirements.txt
```

### La función central: `process_turn()`

```python
def process_turn(chat_id: str, user_message: str) -> str:
    """Recibe el mensaje del usuario, devuelve el texto a enviar."""
    session = supabase.get_session(chat_id)
    history = supabase.get_recent_messages(chat_id, limit=8)
    
    ai_response = openai.generate_turn(
        system_prompt=SYSTEM_PROMPT,
        session=session,
        history=history,
        user_message=user_message,
    )
    
    supabase.save_message(chat_id, user_message, "user")
    supabase.update_session(chat_id, ai_response)
    supabase.save_message(chat_id, ai_response["reply"], "bot")
    
    if ai_response["requires_handoff"]:
        supabase.create_request(chat_id, ai_response)
    
    return ai_response["reply"]
```

---

## 10. JSON schema simplificado para OpenAI (propuesta)

En lugar de 14 campos obligatorios, usar solo los que realmente se usan:

```json
{
  "reply": "string — el mensaje para enviar al cliente",
  "intent": "programacion_rutas | resultados | contabilidad | alta_cliente | no_clasificado",
  "phase": "collecting | confirming | done | escalated",
  "captured_fields": {
    "clinic_name": null,
    "tax_id": null,
    "pickup_address": null,
    "exam_type": null,
    "patient_name": null
  },
  "requires_handoff": false,
  "handoff_area": "none | contabilidad | operaciones | tecnico"
}
```

4 fases simples en lugar de 8:
- `collecting` — recolectando datos
- `confirming` — confirmando con el cliente antes de registrar
- `done` — solicitud registrada, conversación cerrada
- `escalated` — derivado a humano

---

## 11. System prompt para el nuevo agente (borrador base)

```
Eres el asistente de Laboratorio A3, un laboratorio de análisis veterinario en Bogotá.
Atiendes a veterinarias y clínicas que necesitan retirar muestras o consultar resultados.

Tu nombre es "Asistente A3". Suenas como un humano del equipo: cercano, profesional, en español colombiano.

Puedes ayudar con:
1. Coordinar recogida de muestras — pides datos mínimos y registras la solicitud
2. Consultar estado de resultados — pides referencia y das el estado actual
3. Temas de pagos/facturación — derivas a contabilidad (no resuelves en chat)
4. Clientes nuevos — derivas a recepción (no haces el alta tú)

Reglas de conversación:
- Una sola pregunta por turno. Siempre.
- No repitas preguntas ya respondidas. Usa el historial.
- Si falta información, pide solo el dato más importante primero.
- Cuando derives a un humano, hazlo en un solo mensaje claro sin pedir más datos.
- Tono: como si fuera tu colega del laboratorio hablando por WhatsApp.

Para recogidas: necesitas saber (1) clínica, (2) dirección, (3) tipo de análisis.
Para resultados: necesitas saber (1) nombre del paciente O (2) número de muestra/orden.
```

---

## 12. Lo que el cliente ve vs lo que el sistema guarda

| El cliente dice | El sistema guarda |
|---|---|
| "Hola, soy de Clínica Patas Felices" | `clinic_name = "Clínica Patas Felices"` |
| "Necesito un retiro para hoy" | `intent = programacion_rutas`, `phase = collecting` |
| "La dirección es Calle 80 # 45-20" | `pickup_address = "Calle 80 # 45-20"` |
| "Son análisis de sangre" | `exam_type = "sangre"` |

El cliente NUNCA ve: fases, intents, service_area, UUIDs, estados de BD.

---

## 13. Casos de prueba mínimos (para validar el nuevo agente)

Antes de considerar el agente listo, estos deben pasar:

1. **Saludo simple** → El bot saluda de forma natural y pregunta en qué puede ayudar (no muestra menú de opciones numeradas).

2. **Intención directa** → "Necesito programar un retiro" → el bot pide el primer dato (clínica), no muestra lista de campos.

3. **Datos parciales** → "Necesito resultados de Rocky" → el bot confirma que entiende y pide el dato que falta (referencia), no repite el nombre del paciente.

4. **Pregunta lateral** → En medio de programar una ruta, el cliente pregunta "¿cuánto cuesta el hemograma?" → el bot responde la pregunta brevemente y retoma el flujo.

5. **Escalado limpio** → "Tengo un problema con mi factura" → el bot deriva a contabilidad en 1 mensaje sin pedir datos adicionales.

6. **Cliente sin motorizado** → El bot registra la solicitud, informa que el equipo la gestionará, no falla en silencio.

7. **Solicitud después de las 17:30** → El bot confirma que la recogida es para el siguiente día hábil (no el mismo día).

8. **Small talk** → "Gracias, que tenga buen día" → el bot responde natural y no vuelve a presentar el menú.

---

## 14. Lo que NO incluir en V1 del nuevo agente

- Integración con Anarvet (fuera de alcance)
- Envío automático de PDFs de resultados (fuera de alcance)
- Workflow de contabilidad automatizado (fuera de alcance)
- Dashboard operativo (separar en otro proyecto o agregar después)
- WhatsApp (primero estabilizar Telegram)
- Soporte de audio/voz (agregar después si se necesita)
