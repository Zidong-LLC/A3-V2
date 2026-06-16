# Módulo: app/

## Responsabilidad

Contiene la lógica del agente conversacional A3. El estado actual prioriza estabilidad de flujos; el refactor debe hacerse por comportamiento probado.

## Mapa de archivos

| Archivo | Responsabilidad | Límite |
|---|---|---|
| `main.py` | Flask app, webhooks Telegram/Chatwoot, `/health` | ~120 líneas |
| `agent.py` | `process_turn()` — orquesta un turno completo y guardrails | grande; refactor pendiente |
| `prompt.py` | System prompt de OpenAI (tono, intenciones y reglas) | grande; mantener sincronizado con guardrails |
| `schema.py` | JSON schema amplio para structured output de OpenAI | ~95 líneas |
| `rules.py` | Lógica de negocio pura sin I/O (corte, motorizado) | < 100 líneas |
| `config.py` | Lee y valida variables de entorno | < 50 líneas |

## Invariantes

- `main.py` no importa `openai`, `supabase` ni lógica de negocio directamente
- `rules.py` no hace I/O — funciones puras, testeables sin mocks
- `schema.py` no debe ampliarse sin prueba de regresión; el schema actual ya es amplio
- `prompt.py` no incluye la definición del JSON schema (eso va en `schema.py`)

## Dependencias entre archivos

```
main.py → agent.py
agent.py → prompt.py, schema.py, rules.py, services/*
rules.py → config.py (solo constantes, no queries)
config.py → (solo os.environ)
```

## Convenciones

- Variables de dominio de negocio: nombres en español cuando es natural
  (`clinic_name`, `motorizado`, no `messenger`)
- Errores de servicios externos: loggear y propagar — nunca fallar silenciosamente
- Timezone: siempre `America/Bogota` (UTC-5). Nunca datetime naïve.
