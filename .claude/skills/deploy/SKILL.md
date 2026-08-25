---
name: Deploy
description: Proceso de deploy a Render para el agente A3 Veterinaria
---

# Deploy — A3 Veterinaria

Proceso para hacer deploy del agente a Render.

## Pre-deploy

1. Verificar que no hay cambios sin commitear: `git status`
2. Correr tests si existen: `python -m pytest`
3. Confirmar que las variables de entorno en Render están actualizadas

## Variables de entorno requeridas

```
TELEGRAM_BOT_TOKEN, TELEGRAM_WEBHOOK_SECRET,
SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY,
OPENAI_API_KEY, OPENAI_MODEL=gpt-5.5,
APP_TIMEZONE=America/Bogota, CUTOFF_HOUR=17, CUTOFF_MINUTE=30,
FLASK_SECRET_KEY
```

Opcionales por integración (lista completa y documentada en `.env.example`):

```
ALEGRA_ENABLED, ALEGRA_EMAIL, ALEGRA_API_TOKEN, ALEGRA_BASE_URL, ALEGRA_PRODUCTION
ANARVET_ENABLED, ANARVET_DB_HOST, ANARVET_DB_PORT, ANARVET_DB_NAME,
ANARVET_DB_USER, ANARVET_DB_PASSWORD, ANARVET_SSLMODE
```

⚠️ Anarvet: desplegar primero con `ANARVET_ENABLED=false` (inocuo); al encenderlo,
verificar `/health` y correr un sync corto DESDE Render — si su servidor filtra por
IP, pedir a Anarvet whitelistar las IPs de egreso de Render (decisión 013).

## Deploy

Render hace deploy automático al push a `main`.

Para deploy manual: dashboard Render → "Manual Deploy" → "Deploy latest commit"

## Post-deploy

1. Verificar health: `GET https://{dominio}/health` → debe devolver `{"status": "ok"}`
2. Verificar logs en Render — no debe haber errores de importación
3. Si se cambió el dominio: reconfigurar webhook de Telegram
   ```bash
   python tools/scripts/set_webhook.py
   ```
4. Enviar un mensaje de prueba al bot en Telegram

## Rollback

Dashboard Render → Deployments → deploy anterior → "Rollback to this deploy"

## Troubleshooting

Ver [docs/runbooks/deploy.md](../../../docs/runbooks/deploy.md) para troubleshooting detallado.
