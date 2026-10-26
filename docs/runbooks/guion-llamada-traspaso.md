# Guion de la llamada con el cliente — cuentas para producción

> Una sola llamada de ~45 minutos, con pantalla compartida. Todo se crea **en vivo**, con la
> persona de A3 que tenga la **tarjeta de la empresa** y acceso al **correo de A3** que van a
> usar. Si falta alguna de las dos cosas, reprogramar: sin tarjeta no se puede avanzar.

## Antes de la llamada (5 minutos, vos solo)

- Tener a mano: tu correo (para las invitaciones), tu usuario de Telegram, y este guion.
- Pedirle al cliente por mensaje que entre a la llamada con: la tarjeta de la empresa, acceso
  al correo de A3 que usarán para las cuentas, y el nombre de dominio de A3.

## En la llamada: 6 bloques, en este orden

### 1. Supabase (base de datos) — 8 min · USD 25/mes
Decile: *«Acá vive la base de datos y los PDF de resultados. Yo tengo el proyecto en mi
cuenta y se lo transfiero a la de ustedes; no se pierde nada.»*
1. Entra a **supabase.com** → *Start your project* → crea cuenta con el correo de A3.
2. *New organization*: nombre «A3 Laboratorio», plan **Pro**, carga la tarjeta.
3. *Organization settings → Team → Invite*: tu correo, rol **Owner**.
4. **No crear ningún proyecto.**
- Anotá: ☐ nombre de la organización · ☐ invitación recibida en tu correo.

### 2. Render (servidor) — 7 min · ~USD 25/mes
Decile: *«Este es el servidor donde corre la plataforma, el portal y el bot.»*
1. **render.com** → *Get started* → cuenta con el correo de A3.
2. *Workspace settings → Billing*: carga la tarjeta.
3. *Members → Invite*: tu correo, rol **Admin**.
- Anotá: ☐ invitación recibida.

### 3. OpenAI (la inteligencia artificial del bot) — 10 min · según uso
Decile: *«Es lo que hace que el bot entienda y responda. Se paga por uso; arrancamos con un
crédito de 50 dólares y el panel les muestra cuánto se consume.»*
1. **platform.openai.com** → cuenta con el correo de A3 (verifica el correo y el teléfono).
2. *Settings → Billing → Add payment details*: tarjeta y **crédito inicial de USD 50**.
3. *Settings → Organization → Projects → Create project*: «A3 plataforma».
4. *API keys → Create new secret key* (del proyecto A3 plataforma) → **la clave empieza con
   `sk-`**: que la copie en el gestor de contraseñas o te la pase por un mensaje seguro.
   **Se muestra una sola vez.**
5. *Settings → Organization → Admin keys → Create admin key* → permiso de lectura de uso
   (`api.usage.read`) → igual: que la guarde y te la pase por canal seguro.
- Anotá: ☐ API key recibida · ☐ Admin key recibida.

### 4. Servidor para Chatwoot (bandeja de mensajes) — 7 min · ~USD 12–24/mes
Decile: *«Es la bandeja donde el personal ve los chats de Telegram y WhatsApp y donde entra
una persona cuando el bot deriva. Va en un servidor chico aparte.»*
1. Opción simple: **digitalocean.com** → cuenta con el correo de A3 → tarjeta → *Team → Invite*
   tu correo como **Owner**. (Alternativa: hetzner.com, más barato; mismo procedimiento.)
2. **No crear ningún servidor**: lo creo yo desde su cuenta, para que la factura sea de ellos.
- Anotá: ☐ proveedor elegido · ☐ invitación recibida.

### 5. WhatsApp y dominio — 8 min · sin costo nuevo
1. **business.facebook.com** → *Configuración del negocio → Usuarios → Personas → Agregar*:
   tu correo, acceso **administrador**. Confirmá en pantalla que el número +57 316 109 2742
   aparece en *Cuentas de WhatsApp*.
2. **Dominio:** ¿quién administra el dominio de A3? Pedí acceso al panel de DNS **o** que
   la persona que lo administre esté disponible para crear 2 registros cuando se los pases
   (`plataforma.<dominio>` y `portal.<dominio>`).
- Anotá: ☐ acceso a Meta · ☐ contacto o acceso del DNS.

### 6. Telegram y cierre — 5 min
1. ¿Qué persona de A3 será la dueña del bot? Que te pase su **usuario de Telegram** (@…).
2. Repasá en voz alta la lista de abajo y decile cuándo lanzás: *«Con lo de hoy, mañana la
   plataforma queda en producción en sus cuentas. Chatwoot nuevo y el dominio van en los
   días siguientes, sin cortar el servicio.»*

## La llamada termina cuando tenés

- ☐ Invitación Owner en la organización de Supabase (plan Pro)
- ☐ Invitación Admin en el workspace de Render (con tarjeta cargada)
- ☐ API key y Admin key de OpenAI (con crédito cargado)
- ☐ Invitación en DigitalOcean/Hetzner (con tarjeta)
- ☐ Acceso administrador al Business Manager de A3 (WhatsApp)
- ☐ Acceso al DNS o la persona que lo maneja
- ☐ Usuario de Telegram del futuro dueño del bot

## Después de la llamada (vos)

1. Aceptá las invitaciones (Supabase, Render, el VPS).
2. Guardá las dos claves de OpenAI en el `.env` como `OPENAI_API_KEY` y `OPENAI_ADMIN_KEY`.
3. Avisame y seguimos con el paso 1 del runbook `traspaso-cuentas-cliente.md`
   (transferir el proyecto de Supabase); el deploy en el Render del cliente va ese mismo día.
