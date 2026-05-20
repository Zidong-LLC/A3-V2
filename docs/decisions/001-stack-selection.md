# ADR 001 — Selección de stack tecnológico

**Fecha:** 2026-04-27  
**Estado:** Aceptado

## Contexto

El agente V1 usó Python + Flask + Supabase + OpenAI. El proyecto se reinició por problemas
de diseño (sobreingeniería, schema excesivo, lógica fragmentada), no por problemas del stack.

## Decisión

Mantener exactamente el mismo stack:

| Componente | Elección | Alternativa descartada |
|---|---|---|
| Backend | Python 3.12 + Flask | FastAPI — overhead innecesario para un webhook simple |
| Base de datos | Supabase (PostgreSQL) | Otro — el esquema ya existe en producción |
| IA | OpenAI gpt-5.5 | gpt-4o — más caro sin mejora observable para este caso |
| Mensajería | Telegram Bot API | WhatsApp — alcance V1 |
| Hosting | Render | Railway — ya configurado, funciona |

## Consecuencias

- El esquema de Supabase NO se modifica. Nuevas columnas solo con ADR aprobado.
- Flask es suficiente: un solo endpoint de webhook + `/health`. No justifica FastAPI.
- gpt-5.5: rápido y estable para respuestas conversacionales cortas.
- WhatsApp queda para V2 cuando Telegram esté estabilizado.
