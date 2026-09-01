# Runbook — Deploy a Render

> Actualizado 2026-08-31. La configuración del servicio vive en `render.yaml`
> (blueprint): no hay que recordar flags, Render los lee de ahí.

## Arquitectura del cableado (importante)

```
Telegram → Chatwoot (webhook fijo, no cambia nunca)
         → NUESTRO servicio /chatwoot/webhook?token=SECRETO   ← esto es lo único que se recablea
         → Chatwoot API → el cliente
```

Chatwoot administra el webhook de Telegram. **NO correr `set_webhook.py`**: apunta
Telegram directo a Flask y Chatwoot deja de ver las conversaciones.

Lo único que cambia al desplegar es la **URL saliente del Agent Bot** en Chatwoot:
pasa de la de ngrok a la de Render. Y desde ERR-177 esa URL **debe llevar el token**:

```
https://<servicio>.onrender.com/chatwoot/webhook?token=<CHATWOOT_WEBHOOK_SECRET>
```

Sin el `?token=`, el webhook responde 403 y el bot queda mudo.

## Antes de desplegar

- [ ] `python -m pytest` en verde
- [ ] La rama a desplegar está publicada en GitHub
- [ ] El tag de la imagen del Dockerfile coincide con `playwright==` de requirements.txt
      (hoy: `v1.55.0-noble` ↔ `playwright==1.55.0`)

## 1. Crear el servicio

Render → **New → Blueprint** → conectar el repo `Zidong-LLC/A3-V2` → elegir la rama.
Render lee `render.yaml` y arma el servicio: Docker, plan Standard (2 GB), health check
en `/health`, y **auto-deploy apagado** (producción no se actualiza sola).

Va a pedir las 27 credenciales marcadas `sync: false`. Salen del `.env` local, tal cual.
Dos las genera Render solo (`FLASK_SECRET_KEY`, `PLATFORM_API_TOKEN`) — mejor así.

### Por qué el plan Standard y no el Starter
Chromium usa 150-300 MB mientras arma un informe; el Starter tiene 512 MB en total. Un
pico no rompe el PDF: tumba la instancia entera, con el bot adentro.

### Por qué UN worker
El buffer anti-ráfagas del bot vive en memoria del proceso. Con 2 workers, dos mensajes
seguidos del mismo cliente caen en procesos distintos y se procesan por separado — el
debounce se parte (ERR-176). Los turnos del agente corren en threads propios, así que
los 8 threads quedan libres para la web.

## 2. Primer arranque (todo apagado)

El blueprint despliega con `PDF_ENABLED`, `ANARVET_ENABLED` y `ALEGRA_ENABLED` en
`false` a propósito: si algo falla, falla de a una integración por vez.

```bash
curl https://<servicio>.onrender.com/health
```

Esperado: `supabase: ok`, `openai: ok`, el resto `disabled`.

## 3. Encender las integraciones, de a una

Cada vez: cambiar la variable en Render → esperar el redeploy → mirar `/health`.

1. **`ALEGRA_ENABLED=true`** → el check `alegra` pasa a `ok`.
   `ALEGRA_PRODUCTION` se queda en `false` para siempre: solo borradores, nunca DIAN.
2. **`ANARVET_ENABLED=true`** → el check `anarvet` pasa a `ok`.
   ⚠ Si Anarvet filtra por IP, va a fallar: hay que pedirles autorizar las IPs de
   egreso de Render (Render → Settings → Outbound IPs).
3. **`PDF_ENABLED=true`** → el check `pdf` pasa de `disabled` a `ok`.

## 4. Recablear Chatwoot

`https://n3-chatwoot.1hqzy5.easypanel.host/app/accounts/2/settings/integrations`
→ Agent Bots → A3 Bot → editar la URL saliente:

```
https://<servicio>.onrender.com/chatwoot/webhook?token=<CHATWOOT_WEBHOOK_SECRET>
```

Verificar con `python tools/scripts/verify_chatwoot_telegram_agent.py` (comprueba
`/health`, la `outgoing_url`, la asociación del bot al inbox y que el webhook de
Telegram siga apuntando a Chatwoot).

## 5. Programar el sync de Anarvet

Render → **New → Cron Job**, mismo repo y entorno:

```bash
curl -fsS -X POST https://<servicio>.onrender.com/api/platform/anarvet/sync \
     -H "X-Platform-Token: $PLATFORM_API_TOKEN"
```

Sugerido: cada hora en horario laboral (`0 7-19 * * 1-6`, hora de Bogotá).

## 6. Prueba en vivo (la puerta final)

- [ ] Mandar un mensaje por Telegram y que el bot conteste
- [ ] Crear una orden completa de punta a punta y **borrarla después**
- [ ] Pedir un resultado por el chat y que llegue el PDF
- [ ] Entrar al dashboard y al portal desde la URL pública
- [ ] Confirmar que la orden de prueba aparece en Solicitudes y en la Agenda

## Cuando A3 entregue la cuenta de WhatsApp Business

El código ya está listo (migración 031, ERR-177). Falta solo:
1. Conectar el número como inbox de WhatsApp en Chatwoot
2. Asociar el A3 Bot a ese inbox nuevo
3. Probar la cadena completa **antes** de que A3 cancele LiveConnect

El canal se detecta solo: el payload de Chatwoot trae `Channel::Whatsapp` y la orden
queda marcada `whatsapp` en `entry_channel`.

## Si algo sale mal

| Síntoma | Causa probable |
|---|---|
| El bot no contesta | La URL del Agent Bot no lleva `?token=` → 403 |
| `/health` da 503 | Supabase no responde: revisar `SUPABASE_URL` y la service role key |
| El check `anarvet` da error | IP de Render no autorizada por Anarvet |
| El PDF falla | El tag de la imagen no coincide con la versión de playwright |
| Build en verde pero revienta al usar el PDF | Runtime nativo en vez de Docker |
