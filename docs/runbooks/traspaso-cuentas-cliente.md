# Runbook — Traspaso de las cuentas al cliente (A3 / Laberit)

> Objetivo (decisión del usuario, 2026-10-26): que **cada servicio pago quede en una cuenta
> del cliente y lo pague él**. El código y la base no cambian; cambian las cuentas que los
> alojan. Se hace servicio por servicio, en el orden de abajo, y la plataforma sigue
> funcionando en las cuentas actuales hasta que cada pieza nueva esté probada.

## Qué cuenta tiene hoy cada servicio

| Servicio | Hoy | Mañana | Cómo se pasa |
|---|---|---|---|
| Supabase (base + PDFs) | Org «LABERIT» (del desarrollador) | Org del cliente, plan Pro | **Transferir el proyecto** entre organizaciones (sin copiar datos) |
| Render (servidor) | Cuenta del desarrollador | Workspace del cliente, plan Standard | **Crear el servicio de nuevo** con `render.yaml` (Render no traspasa servicios) |
| OpenAI (IA del bot) | Cuenta del desarrollador | Org del cliente con facturación | Nueva API key en la cuenta del cliente; se cambia la variable en Render |
| Chatwoot (bandeja, Telegram, WhatsApp) | EasyPanel/VPS del desarrollador | VPS + EasyPanel del cliente | **Instalación nueva**; se recrean inboxes, equipos, agentes y el bot |
| WhatsApp Business (Meta) | Número de A3, nombre verificado | Igual (ya es de A3) | Reconectar el número al Chatwoot nuevo |
| Telegram, bot de clientes | Creado por el desarrollador | Transferido al cliente | BotFather → Transfer Ownership (el token sigue sirviendo) |
| Telegram, bot de avisos | Del desarrollador | Se queda (avisa al desarrollador) | Nada |
| Alegra | Cuenta real de A3 | Igual | Nada |
| Anarvet | Base de Anarvet, usuario de A3 | Igual | Si filtra por IP: autorizar las IPs del Render nuevo |
| GitHub (código) | `Zidong-LLC/A3-V2` | Según contrato: se transfiere o se da acceso | El Render del cliente necesita leer el repo |
| Dominio | No hay (`onrender.com`) | `plataforma.<dominio de A3>` y `portal.<dominio>` | Recomendado: así la URL no cambia nunca más |

## Qué tiene que hacer el cliente (checklist para enviarle)

1. **Supabase:** crear cuenta en supabase.com, crear una organización (plan **Pro**) e invitar
   como *Owner* al correo del desarrollador. No crear ningún proyecto.
2. **Render:** crear cuenta en render.com, crear un workspace e invitar como *Admin* al
   desarrollador. Cargar la tarjeta (plan Standard, ~USD 25/mes).
3. **OpenAI:** crear cuenta en platform.openai.com, cargar método de pago (o crédito prepago;
   las cuentas nuevas tienen límites bajos hasta acumular gasto) y crear un **proyecto**.
   Generar dos claves y pasarlas por un canal seguro (no por WhatsApp ni correo abierto):
   una **API key** del proyecto y una **Admin key** con permiso `api.usage.read` (para que el
   panel de sistema muestre el gasto).
4. **VPS para Chatwoot:** contratar un servidor (2 vCPU, 4 GB RAM, 40 GB) e instalar EasyPanel,
   o darle acceso al desarrollador para que lo haga. Un subdominio para Chatwoot
   (`chat.<dominio>`).
5. **Meta (WhatsApp):** confirmar que el número y la cuenta de WhatsApp Business están en el
   **Business Manager de A3** y dar acceso de administrador al desarrollador para reconectar el
   número al Chatwoot nuevo.
6. **Telegram:** la persona de A3 que será dueña del bot pasa su usuario de Telegram.
7. **Dominio:** acceso al DNS del dominio de A3 (o que creen ellos los registros que se les pidan).

## Orden de ejecución (cada paso se prueba antes de seguir)

### 1. Supabase — transferir el proyecto (sin corte)
Con el desarrollador dentro de las dos organizaciones: proyecto `a3veterinaria` →
*Project Settings → General → Transfer project* → organización del cliente. La URL del
proyecto y las claves **no cambian**: no hay que tocar nada en Render. Verificar
`/health` después. Si Supabase no permitiera la transferencia (por plan o región), plan B:
crear proyecto nuevo en la org del cliente, correr `db/migrations/` en orden, copiar la base
con `pg_dump`/`pg_restore` y los PDFs del bucket `lab-results`; exige un corte de unas horas
y cambiar `SUPABASE_URL` y `SUPABASE_SERVICE_ROLE_KEY` en Render.

### 2. OpenAI — cambiar la clave (reinicio de 2 minutos)
En Render → Environment → `OPENAI_API_KEY` = la clave del cliente. Probar un turno del bot.
Guardar la Admin key como `OPENAI_ADMIN_KEY` (la usa el panel de sistema).

### 3. Render — servicio nuevo en el workspace del cliente (corte de segundos)
1. Dar acceso al repo desde el workspace del cliente (GitHub app de Render).
2. *New → Blueprint* → `render.yaml` → cargar las variables `sync: false` desde el `.env`
   (ver `docs/runbooks/deploy.md`). `FLASK_SECRET_KEY` y `PLATFORM_API_TOKEN` los genera
   Render: **anotar el token nuevo** (lo usan los crons y el script de verificación).
3. Esperar el deploy; `python tools/scripts/verificar_produccion.py https://<nuevo>.onrender.com`
   va a marcar que el bot de Chatwoot todavía apunta al viejo: es lo esperado.
4. Apuntar el Agent Bot de Chatwoot a `https://<nuevo>/chatwoot/webhook?token=<secreto>`.
   Desde ese momento el tráfico entra al nuevo. Crear los dos Cron Jobs (Anarvet y pedidos).
5. Suspender el servicio viejo (no borrarlo hasta una semana después).
6. Dominio propio: *Settings → Custom Domains* en Render + registros DNS en el dominio de A3.
   Después, cambiar la URL del Agent Bot al dominio para que no dependa de Render.

### 4. Chatwoot — instalación nueva (el paso más largo; corte de minutos por inbox)
1. En el EasyPanel del cliente: plantilla Chatwoot (Postgres + Redis + Sidekiq), subdominio con
   HTTPS, cuenta de administrador para A3.
2. Recrear: la cuenta, los **equipos** Contabilidad y Operaciones, los **agentes** (personal de
   A3), el **Agent Bot** «A3» (webhook) apuntando a Render con `?token=`, y el **token de API**.
3. Inbox de **Telegram** con el token del bot: Chatwoot registra solo el webhook de Telegram
   (desde ahí el Chatwoot viejo deja de recibir). Asociar el bot al inbox.
4. Inbox de **WhatsApp Cloud** con las credenciales del Business Manager de A3; configurar en
   la app de Meta el webhook del Chatwoot nuevo y el verify token. Asociar el bot al inbox.
5. Actualizar en Render: `CHATWOOT_URL`, `CHATWOOT_ACCOUNT_ID`, `CHATWOOT_API_TOKEN`,
   `CHATWOOT_AGENT_BOT_TOKEN`, `CHATWOOT_INBOX_ID`, `CHATWOOT_TEAM_CONTABILIDAD`,
   `CHATWOOT_TEAM_OPERACIONES`, `CHATWOOT_WEBHOOK_SECRET` (uno nuevo).
6. **Motorizados:** sus avisos van a una conversación de Chatwoot guardada en
   `couriers.chatwoot_conversation_id` (migración 032). En el Chatwoot nuevo hay que volver a
   vincular a cada motorizado (que escriban al bot una vez y guardar el id nuevo).
7. El historial de conversaciones del Chatwoot viejo **no se migra** (queda consultable ahí
   mientras exista el servidor). Si A3 lo quiere, exportar antes de apagarlo.

### 5. Telegram — transferir el bot
BotFather → `/mybots` → el bot → *Transfer Ownership* → usuario de A3. El token no cambia.

### 6. GitHub
Según el contrato: transferir el repositorio a una organización del cliente (GitHub lo
permite desde *Settings → Transfer*) o mantenerlo y dar acceso de lectura al workspace de
Render del cliente. En cualquier caso, **repositorio privado**.

## Después del traspaso
- `verificar_produccion.py` contra la URL definitiva: todo OK.
- Actualizar `.env.example`, `docs/runbooks/deploy.md` y `sesion-local.md` con las URLs nuevas.
- El panel de sistema muestra el gasto por servicio: confirmar que lee la cuenta del cliente.
- Dar de baja lo viejo recién cuando una semana de operación en lo nuevo no muestre fallas.
