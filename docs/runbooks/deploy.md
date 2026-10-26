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
- [ ] La rama a desplegar está publicada en GitHub (Render construye desde GitHub: lo que
      no está commiteado y pusheado NO se despliega)
- [ ] Las migraciones de `db/migrations/` están commiteadas Y aplicadas en Supabase (las
      tablas nuevas se crean a mano; el deploy no corre migraciones)
- [ ] El tag de la imagen del Dockerfile coincide con `playwright==` de requirements.txt
      (hoy: `v1.55.0-noble` ↔ `playwright==1.55.0`)
- [ ] Los valores fijos de `render.yaml` son los que se quieren en producción. Ojo con
      `FSM_ENFORCE` y `MESSAGE_DEBOUNCE_*`: el `.env` local puede tener otros valores
      (lo que se probó en local no es necesariamente lo que corre en Render)

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
curl -H "X-Platform-Token: $PLATFORM_API_TOKEN" https://<servicio>.onrender.com/health/detalle
```

`/health` es el liviano que mira Render (solo Supabase, ERR-182). El completo es
`/health/detalle` y desde el 2026-10-19 exige el token de la plataforma (o sesión del
panel): sin él responde 401. Esperado: `supabase: ok`, `openai: ok`, el resto `disabled`.

Todo el cableado de una vez (solo lectura; sirve después de CADA deploy):

```bash
python tools/scripts/verificar_produccion.py https://<servicio>.onrender.com
```

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

Verificar con `python tools/scripts/verificar_produccion.py https://<servicio>.onrender.com`
(comprueba `/health`, `/health/detalle`, la `outgoing_url` con su token, la asociación del
bot a los inboxes de Telegram y WhatsApp, y que el webhook de Telegram siga apuntando a
Chatwoot). `verify_chatwoot_telegram_agent.py` es el de la sesión LOCAL con ngrok: ese
REESCRIBE la URL del bot, no usarlo contra producción.

## 5. Programar el sync de Anarvet

Render → **New → Cron Job**, mismo repo y entorno:

```bash
curl -fsS -X POST https://<servicio>.onrender.com/api/platform/anarvet/sync \
     -H "X-Platform-Token: $PLATFORM_API_TOKEN"
```

Sugerido: cada hora en horario laboral (`0 7-19 * * 1-6`, hora de Bogotá).

Y un segundo Cron Job para los **pedidos abandonados** (anexo 2026-10-26 de la decisión
011): cierra los que llevan más de una hora sin actividad, limpia la sesión y le avisa al
cliente por su canal. Sin este cron solo corre cuando alguien escribe.

```bash
curl -fsS -X POST https://<servicio>.onrender.com/api/platform/pedidos/barrido      -H "X-Platform-Token: $PLATFORM_API_TOKEN"
```

Sugerido: cada 15 minutos (`*/15 * * * *`).

## 6. Prueba en vivo (la puerta final)

- [ ] Mandar un mensaje por Telegram y que el bot conteste
- [ ] Crear una orden completa de punta a punta y **borrarla después**
- [ ] Pedir un resultado por el chat y que llegue el PDF
- [ ] Entrar al dashboard y al portal desde la URL pública
- [ ] Confirmar que la orden de prueba aparece en Solicitudes y en la Agenda

## WhatsApp Business

El canal quedó conectado y probado el 04/09/2026 (ERR-181). Al cambiar el número o
recrear el inbox: asociar el A3 Bot, agregar los agentes como miembros y probar la
cadena completa antes de retirar el canal anterior. El payload de Chatwoot identifica
`Channel::Whatsapp` y la orden queda marcada `whatsapp` en `entry_channel`.

## Si algo sale mal

| Síntoma | Causa probable |
|---|---|
| El bot no contesta | La URL del Agent Bot no lleva `?token=` → 403 |
| `/health` da 503 | Supabase no responde: revisar `SUPABASE_URL` y la service role key |
| `/health` da 503 con HTML «Service Suspended» | El servicio está suspendido en Render (apagado a mano o por facturación): reanudarlo desde el panel |
| `/health/detalle` da 401 | Falta la cabecera `X-Platform-Token` (o la sesión del panel) |
| El check `anarvet` da error | IP de Render no autorizada por Anarvet |
| El PDF falla | El tag de la imagen no coincide con la versión de playwright |
| Build en verde pero revienta al usar el PDF | Runtime nativo en vez de Docker |

## Panel de sistema (`/sistema`)

Acceso **aparte de la plataforma**, solo para el responsable técnico: `https://<servicio>/sistema`
con `SISTEMA_USER` / `SISTEMA_PASSWORD` (variables propias; sin la clave el panel queda
cerrado). No aparece en el menú del CRM y los usuarios de A3 no lo ven. Muestra el estado en
vivo de cada servicio, errores por componente (todo lo que llega al Telegram de avisos, sin
anti-spam), conversaciones y turnos del bot, tokens del modelo y gasto del mes.
`OPENAI_ADMIN_KEY` (opcional, Admin key con permiso `api.usage.read`) habilita el gasto real
de OpenAI; los costos fijos (Render, VPS, Alegra…) se cargan a mano en el mismo panel.
El JSON está en `GET /api/sistema/estado` con la sesión del panel o con `X-Platform-Token`.

## Avisos de error a Telegram

Con `ADMIN_TELEGRAM_CHAT_ID` configurado, un error que deja a un cliente sin respuesta
—o un 500 en el dashboard/portal— llega como mensaje al chat del responsable técnico,
con el tipo de error y dónde ocurrió. Nunca viaja contenido de la conversación.

Anti-spam: cada tipo de error avisa una vez cada 15 minutos y el siguiente mensaje
informa cuántas veces se repitió mientras tanto. Sin esto, una caída de la base
mandaría cientos de mensajes y Telegram cortaría el bot.

**Para obtener el chat_id**: escribirle una vez al bot desde el Telegram personal y
buscar el `external_chat_id` de esa sesión en `telegram_sessions`.

## Dos clases de variables en el blueprint (no confundirlas)

**Guardrails con valor fijo en `render.yaml`** — `ALEGRA_PRODUCTION=false`,
`PORTAL_DEMO_MODE=false`. Van escritas a fuego a propósito: si alguien las cambia por
error en el panel, el próximo deploy las devuelve a lo seguro. Es la conducta deseada
para algo que nunca debe cambiar.

**Interruptores con `sync: false`** — `ALEGRA_ENABLED`, `ANARVET_ENABLED`, `PDF_ENABLED`.
Render los pregunta una vez y después respeta el panel. Si llevaran un valor acá, cada
deploy pisaría la configuración del operador: una integración apagada a mano para
contener un incidente volvería a encenderse sola en el deploy siguiente.

> Esto se descubrió en el despliegue del 01/09: un Manual Deploy devolvió las tres
> integraciones a `disabled` porque el blueprint las traía en `false`.
