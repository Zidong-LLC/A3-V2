# Runbook — Deploy a Render

## Pre-deploy checklist

- [ ] Todos los tests pasan: `python -m pytest`
- [ ] No hay secretos hardcodeados en el código
- [ ] Variables de entorno actualizadas en el dashboard de Render
- [ ] El webhook de Telegram apunta al dominio correcto

## Runtime: Docker (desde 2026-08-25)

El servicio corre con el `Dockerfile` de la raíz, **no** con el runtime nativo de Python.

El motivo es el PDF del informe de Anarvet: publicarlo al portal necesita Chromium, y en el
runtime nativo no se es root, así que no hay `apt-get`. Ahí `playwright install chromium`
deja el build **en verde** y el proceso revienta en el **primer request real** por una
librería del sistema faltante (`libnss3.so`). La imagen de Playwright ya trae Chromium con
todas sus dependencias.

Al cambiar el servicio en el panel de Render:

1. Runtime → **Docker** (Render toma el `Dockerfile` de la raíz).
2. El start command sale del `CMD`: gunicorn con **`--timeout 60`**. No bajarlo: el default
   de 30 s mata al worker a mitad de un render de PDF y deja Chromium huérfano.
3. El tag de la imagen y `playwright==` en `requirements.txt` **tienen que coincidir**.
4. Primer deploy con `PDF_ENABLED=false`. Verificar `GET /health` (el check `pdf` debe decir
   `disabled`), encenderlo, y volver a mirar que diga `ok`.

Memoria: Chromium usa 150-300 MB mientras renderiza y el plan Starter tiene 512. El servicio
genera **un informe a la vez por proceso** justamente por eso; dos en paralelo no tumban el
PDF sino la instancia entera, con el bot adentro.

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

### Opcionales por integración (lista completa en `.env.example`)

```
ALEGRA_ENABLED / ALEGRA_EMAIL / ALEGRA_API_TOKEN / ALEGRA_BASE_URL / ALEGRA_PRODUCTION
ANARVET_ENABLED / ANARVET_DB_HOST / ANARVET_DB_PORT / ANARVET_DB_NAME /
ANARVET_DB_USER / ANARVET_DB_PASSWORD / ANARVET_SSLMODE
```

⚠️ Anarvet (decisión 013): desplegar primero con `ANARVET_ENABLED=false`. Al
encenderlo, verificar `/health` (check `anarvet`) y correr un sync corto DESDE
Render: si el servidor de Anarvet filtra por IP, pedirles whitelistar las IPs de
egreso de Render.

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
