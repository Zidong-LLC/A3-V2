# Runbook — Levantar sesión local de desarrollo

> Hacer esto CADA VEZ que se abre una sesión nueva de desarrollo/pruebas.
> El agente de IA debe recordar esto al inicio de cada sesión de trabajo.

## Arquitectura del flujo

```
Telegram → Chatwoot (webhook fijo en n3-chatwoot) → Flask /chatwoot/webhook (ngrok) → Chatwoot API → Telegram
```

Chatwoot administra el webhook de Telegram (URL fija, no cambia entre sesiones).
Lo único que cambia cada sesión es la URL del Agent Bot en Chatwoot (paso 3).

**IMPORTANTE: NO ejecutar `set_webhook.py` — ese script apunta el webhook a Flask
directamente, lo que hace que Chatwoot deje de ver las conversaciones.**

## Pasos obligatorios al iniciar sesión

### 1. Levantar Flask (Terminal 1)
```bash
cd "c:\Users\Artel\Downloads\A3 V2"
python -m flask --app app.main run --port 5000 --host 0.0.0.0
```

### 2. Levantar ngrok (Terminal 2)
```bash
ngrok http 5000
```
Copiá la URL que aparece: `https://XXXX.ngrok-free.app`

### 3. Actualizar webhook del Agent Bot en Chatwoot
- Ir a: `https://n3-chatwoot.1hqzy5.easypanel.host/app/accounts/2/settings/integrations`
- Settings → Integrations → Agent Bots → A3 Bot → editar
- Cambiar la URL a: `https://XXXX.ngrok-free.app/chatwoot/webhook`
- Guardar

## Verificar que todo funciona
```bash
curl https://XXXX.ngrok-free.app/health
```
Debe responder: `{"status": "ok"}`

Después mandá un mensaje de prueba por Telegram y verificá que aparece en Chatwoot.

También se puede validar y reparar la asociación del Agent Bot con:
```bash
python tools/scripts/verify_chatwoot_telegram_agent.py
```
Este script verifica ngrok, `/health`, `outgoing_url`, asociación del Agent Bot al inbox y webhook de Telegram apuntando a Chatwoot. No ejecuta `set_webhook.py`.

## Si el webhook de Telegram queda apuntando a Flask (resetear)
Ocurre si alguien ejecutó `set_webhook.py` por error. Para restaurar:
```bash
python tools/scripts/restore_chatwoot_webhook.py
```

---

## Datos de la infraestructura

| Servicio | URL / Dato |
|----------|-----------|
| Chatwoot | https://n3-chatwoot.1hqzy5.easypanel.host |
| Account ID | 2 |
| Inbox ID | 1 (A3 Veterinaria - Telegram) |
| Team Contabilidad | ID 1 |
| Team Operaciones | ID 2 |

## Para producción (Render)

Cuando se haga el deploy definitivo en Render, los pasos 2-5 desaparecen.
Solo se configura la URL de Render una sola vez y no cambia más.
Ver `docs/runbooks/deploy.md`.
