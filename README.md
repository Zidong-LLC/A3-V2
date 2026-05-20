# A3 Laboratorio Veterinario — Agente Conversacional

Bot conversacional de Telegram para A3 Laboratorio Veterinario (Bogotá, Colombia).
Gestiona recogidas de muestras, consulta de resultados, y derivación a equipo humano.

## Stack

- Python 3.12+ + Flask
- Supabase (PostgreSQL) — modelo de datos existente, no modificar
- OpenAI API (gpt-5.5)
- Telegram Bot API (webhook)
- Render (hosting)

## Instalación

```bash
pip install -r requirements.txt
cp .env.example .env   # completar con las variables reales
python -m app.main
```

## Estructura del proyecto

Ver [docs/architecture.md](docs/architecture.md) para la arquitectura completa.

```
app/
├── main.py          Flask + webhook (< 100 líneas)
├── agent.py         process_turn() — función central
├── prompt.py        System prompt
├── schema.py        JSON schema para OpenAI
├── rules.py         Reglas de negocio puras
├── config.py        Variables de entorno
└── services/
    ├── ai.py        Cliente OpenAI
    ├── db.py        Cliente Supabase
    └── telegram.py  Cliente Telegram
```

## Trabajo con IA

Este proyecto está diseñado para trabajar con dos modelos de IA en paralelo:

| Herramienta | Archivo de contexto | Uso |
|---|---|---|
| Claude Code | `CLAUDE.md` | Instrucciones, reglas, arquitectura |
| OpenCode (ChatGPT) | `AGENTS.md` | Instrucciones, reglas, arquitectura |

Ambos archivos contienen el mismo contexto adaptado al formato de cada herramienta.

### Skills disponibles (Claude Code)

- `/code-review` — Revisión de código con checklist
- `/deploy` — Proceso de deploy a Render

### Estado del trabajo

- Tareas actuales: `tasks/todo.md`
- Lecciones aprendidas: `tasks/lessons.md`

## Variables de entorno

```
TELEGRAM_BOT_TOKEN
TELEGRAM_WEBHOOK_SECRET
SUPABASE_URL
SUPABASE_SERVICE_ROLE_KEY
OPENAI_API_KEY
OPENAI_MODEL=gpt-5.5
APP_TIMEZONE=America/Bogota
CUTOFF_HOUR=17
CUTOFF_MINUTE=30
FLASK_SECRET_KEY
PLATFORM_API_TOKEN=opcional-token-interno
DASHBOARD_ADMIN_USER=admin
DASHBOARD_ADMIN_PASSWORD=definir-en-produccion
```

## Dashboard operativo

La plataforma visual vive dentro del mismo Flask app del agente:

- `GET /login` → acceso privado
- `GET /dashboard` → panel operativo
- `GET /clientes` → clientes y motorizado asignado
- `GET|POST /clientes/nuevo` → alta manual de cliente en revisión documental
- `GET /muestras` → muestras registradas si la tabla operativa existe
- `GET /analisis` → catálogo de análisis individuales
- `GET /flujo` → fases conversacionales
- `GET /aprobaciones` → revisión de clientes nuevos capturados por el agente
- `POST /aprobaciones/decision` → aprobar/rechazar alta manual pendiente
- `GET /afiliaciones` → vista de afiliaciones clínica-profesional si existen datos
- `GET /api/dashboard/overview` → contexto JSON del dashboard

Credenciales por variables de entorno:

- `DASHBOARD_ADMIN_USER`
- `DASHBOARD_ADMIN_PASSWORD`

## API de integración con plataforma

Para conectar este agente con una plataforma interna (dashboard/ops), se expone una API REST de lectura y actualización operativa usando la misma base de datos de Supabase.

Endpoints:

- `GET /api/platform/overview` → resumen operativo (clientes, solicitudes, flujo conversacional)
- `GET /api/platform/clients` → listado de clientes y motorizado asignado
- `GET /api/platform/requests` → listado de solicitudes (filtro opcional por `status`)
- `GET /api/platform/requests/unassigned` → solicitudes de ruta sin asignación de motorizado
- `GET /api/platform/requests/<request_id>/events` → historial de eventos de una solicitud
- `PATCH /api/platform/requests/<request_id>/status` → actualizar estado operativo de solicitud (registra `status_updated` en `request_events`)

Autenticación:

- Si `PLATFORM_API_TOKEN` está configurado, todas las rutas `/api/platform/*` exigen header `X-Platform-Token`.
- Si no está configurado, las rutas quedan disponibles para desarrollo interno.
