# Runbook — Deploy a Render

## Pre-deploy checklist

- [ ] Todos los tests pasan: `python -m pytest`
- [ ] No hay secretos hardcodeados en el código
- [ ] Variables de entorno actualizadas en el dashboard de Render
- [ ] El webhook de Telegram apunta al dominio correcto

## Variables de entorno requeridas en Render

```
TELEGRAM_BOT_TOKEN          token del bot de Telegram
TELEGRAM_WEBHOOK_SECRET     string aleatorio para validar el webhook
SUPABASE_URL                URL del proyecto Supabase
SUPABASE_SERVICE_ROLE_KEY   service role key (no la anon key)
OPENAI_API_KEY              API key de OpenAI
OPENAI_MODEL                gpt-5.5
APP_TIMEZONE                America/Bogota
CUTOFF_HOUR                 17
CUTOFF_MINUTE               30
FLASK_SECRET_KEY            string aleatorio
```

## Proceso de deploy

Render hace deploy automático al hacer push a `main`. Para forzar un deploy manual:

1. Ir al dashboard de Render → servicio A3
2. "Manual Deploy" → "Deploy latest commit"
3. Verificar logs: no debe haber errores de importación ni variables faltantes

## Configurar webhook de Telegram (primera vez o tras cambio de dominio)

```bash
python tools/scripts/set_webhook.py
```

O manualmente:
```
GET https://api.telegram.org/bot{TOKEN}/setWebhook?url=https://{RENDER_DOMAIN}/webhook&secret_token={SECRET}
```

## Verificar que el bot funciona

```
GET https://{RENDER_DOMAIN}/health
```

Respuesta esperada: `{"status": "ok"}`

## Rollback

Render mantiene historial de deploys. En caso de problema:
1. Dashboard → Deployments → seleccionar deploy anterior → "Rollback to this deploy"

## Troubleshooting común

| Síntoma | Causa probable | Solución |
|---|---|---|
| 403 en webhook | `TELEGRAM_WEBHOOK_SECRET` no coincide | Verificar variable en Render |
| Error de Supabase | `SUPABASE_SERVICE_ROLE_KEY` vencida | Rotar en dashboard de Supabase |
| Bot no responde | Webhook no configurado | Correr `set_webhook.py` |
| Timeout en OpenAI | Modelo saturado | Reintentar, gpt-5.5 tiene alta disponibilidad |
