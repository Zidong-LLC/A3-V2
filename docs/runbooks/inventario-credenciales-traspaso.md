# Inventario de cuentas y credenciales — qué es de quién y qué falta cambiar

> Objetivo (27/10): que TODO lo que usa el proyecto quede en cuentas del cliente (A3). Esta
> tabla es la lista de control: cada fila se marca cuando queda del lado del cliente.
> Los valores viven solo en el `.env` local y en las variables de Render; acá nunca.

## Estado por credencial

| Variable / cosa | Qué es | Hoy es de | Tiene que ser de | Cómo se cambia | Estado |
|---|---|---|---|---|---|
| `OPENAI_API_KEY`, `OPENAI_ADMIN_KEY`, `OPENAI_MODEL` | La IA del bot y la lectura del gasto | **Cliente** (desde 27/10) | Cliente | Ya cargadas en el `.env`; en Render van al crear el servicio | ✅ Hecho. Falta: el desarrollador borra su key vieja en su OpenAI |
| `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` | Base de datos y PDFs (proyecto `a3veterinaria`) | Org LABERIT (desarrollador, plan Free) | Org del cliente (plan Pro) | *Transfer project* en el panel de Supabase; la URL y las claves **no cambian** | ⏳ Falta ver la org del cliente (invitación o token de su cuenta) |
| `SUPABASE_ACCESS_TOKEN` | Token de gestión (migraciones, panel de sistema) | Desarrollador | Cuenta del cliente (o la del desarrollador como miembro de la org del cliente) | Generar en *Account → Access Tokens* de la cuenta que quede como dueña | ⏳ |
| Servicio de Render `a3-plataforma` | Plataforma, portal, bot, crons | Workspace del desarrollador (suspendido) | Workspace del cliente, proyecto «A3 Laboratorio» | *New → Blueprint* en el workspace del cliente; cargar variables; borrar el viejo cuando el nuevo funcione | ⏳ Falta `RENDER_API_KEY` con acceso al workspace del cliente |
| `RENDER_API_KEY`, `RENDER_SERVICE_ID` | Lectura de estado y plan en el panel de sistema | — (vacías) | Cuenta con acceso al workspace del cliente | Crear en *Account Settings → API Keys*; el `srv-…` sale de la URL del servicio nuevo | ⏳ |
| `FLASK_SECRET_KEY`, `PLATFORM_API_TOKEN` | Secretos internos de la app | Generados | Generados de nuevo por Render en el servicio del cliente | Los genera el blueprint (`generateValue`) | 🔁 Automático con el deploy |
| `DASHBOARD_ADMIN_USER/PASSWORD` | Admin de respaldo de la plataforma | Generado por el desarrollador | A3 (clave nueva) | Cargar una clave nueva en el Render del cliente y dársela a A3 | ⏳ Con el deploy |
| `SISTEMA_USER/PASSWORD` | Panel de sistema `/sistema` | Desarrollador | Desarrollador (es su acceso) | Se carga en el Render del cliente | 🔁 Con el deploy; no cambia de dueño |
| `CHATWOOT_URL`, `_ACCOUNT_ID`, `_API_TOKEN`, `_AGENT_BOT_TOKEN`, `_INBOX_ID`, `_TEAM_CONTABILIDAD`, `_TEAM_OPERACIONES`, `_WEBHOOK_SECRET` | La bandeja de mensajes | VPS/EasyPanel del desarrollador | Chatwoot nuevo en el Render del cliente (lo crea el blueprint) | Instalar, crear cuenta, equipos, agentes, bot e inboxes; las 8 variables cambian | ⏳ Después del deploy de la plataforma |
| SMTP de Chatwoot (`SMTP_*`, `MAILER_SENDER_EMAIL`) | Correo de invitaciones y recuperación de clave | — (no existía) | Correo de A3 (Google Workspace o Brevo) | Pedir contraseña de aplicación o cuenta Brevo | ⏳ Pedir al cliente |
| Adjuntos de Chatwoot (`STORAGE_*`) | Fotos y PDFs del chat | — (disco del VPS) | Storage de Supabase del cliente (modo S3) | Supabase → *Settings → Storage → S3 access keys*, bucket `chatwoot` | ⏳ Con Chatwoot |
| `TELEGRAM_BOT_TOKEN` | Bot de clientes (@A3veterinariabot) | Creado por el desarrollador | Persona de A3 | BotFather → *Transfer Ownership*; el token no cambia | ⏳ Falta el usuario de Telegram de A3 |
| `TELEGRAM_WEBHOOK_SECRET`, `TELEGRAM_WEBHOOK_URL` | Secreto y URL del webhook (Chatwoot administra el webhook real) | Generados | Generados de nuevo | Cambian con el Chatwoot nuevo | 🔁 Con Chatwoot |
| `WHATSAPP_*` (número, IDs, token de Meta) | El número +57 316 109 2742 (lo usa el inbox de Chatwoot, no el código) | WABA de A3; el token actual salió del acceso del desarrollador | Token de un *usuario del sistema* del Business Manager de A3 | Al crear el inbox de WhatsApp en el Chatwoot nuevo, con acceso al Business Manager de A3 | ⏳ Con Chatwoot |
| `ALEGRA_EMAIL`, `ALEGRA_API_TOKEN`, `ALEGRA_BASE_URL`, `ALEGRA_COUNTRY` | Facturación (cuenta real de A3) | Cuenta de A3 (el usuario es un correo @gmail: **confirmar que es de A3**) | Cliente | Si el usuario fuera del desarrollador: crear un usuario de A3 en Alegra y generar su token | ✅ / confirmar |
| `ANARVET_DB_*` | Base externa de Anarvet (solo lectura) | Anarvet, usuario dado a A3 | Cliente | Nada. Si Anarvet filtra por IP: autorizar las IPs del Render nuevo | ✅ |
| `ALERT_TELEGRAM_BOT_TOKEN`, `ADMIN_TELEGRAM_CHAT_ID` | Bot de avisos de error al responsable técnico | Desarrollador | Desarrollador (es para él) | Nada | ✅ Se queda a propósito |
| Repositorio GitHub `Zidong-LLC/A3-V2` | Código; Render construye desde acá | Organización del desarrollador | Según contrato: transferir o dar acceso al Render del cliente | GitHub → *Settings → Transfer*, o instalar la app de Render con acceso al repo | ⏳ Decisión |
| Dominio | Dirección pública de la plataforma, el portal y Chatwoot | No hay (`onrender.com`) | Dominio de A3 | Registros DNS + *Custom Domains* en Render | ⏳ Pedir acceso al DNS |
| `SSL_CERT_FILE`, `.claude/settings.local.json`, ngrok, TestSprite | Herramientas de desarrollo en la PC del desarrollador | Desarrollador | Desarrollador | No van a producción. TestSprite ya se quitó del `.env` | ✅ |

## Orden en que se van cambiando

1. ✅ OpenAI.
2. Supabase (transferir el proyecto) — necesita ver la org del cliente.
3. Render (blueprint en el workspace del cliente) — necesita `RENDER_API_KEY` o que el desarrollador lo cree en el panel.
4. Chatwoot nuevo (en Render) + SMTP + adjuntos + WhatsApp + Telegram transferido.
5. Dominio, GitHub, y borrar lo viejo (Render viejo, Chatwoot del VPS) una semana después.
