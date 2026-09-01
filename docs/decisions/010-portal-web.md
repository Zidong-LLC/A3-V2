# 010 — Portal Web de clientes + módulo Resultados en el dashboard

**Fecha:** 2026-07-06 (revisada el mismo día: el portal queda SOLO para clientes)
**Estado:** Implementado y en uso. (Nota 2026-08-31: `SUPABASE_ANON_KEY` quedó obsoleta — el login del portal es por nombre de clínica + NIT, sin GoTrue; `PORTAL_RESULTS_BUCKET` tiene default sano en código.)

## Contexto

Se necesita un canal web para que cada veterinaria vea SOLO su información: solicitudes
de retiro, resultados publicados en PDF, notificaciones y perfil. El personal del
laboratorio NO usa el portal: ya tiene su plataforma (el dashboard administrativo
existente), así que la carga/publicación de resultados vive ahí. El flujo conversacional
no se toca.

## Decisión

- **Blueprint nuevo `portal`** (`app/portal/`, url_prefix `/portal`), **solo clientes**,
  server-rendered Jinja2 + JS vanilla, misma identidad visual (`app.css` + `portal.css`).
  Registrado en `app/main.py`; hereda CSRF y security headers globales.
- **Módulo Resultados del personal: `app/dashboard_results.py`** — blueprint separado
  montado en `/resultados` que usa la sesión y el login del dashboard existente
  (`session["dashboard_authenticated"]`). Se eligió blueprint aparte para NO modificar
  `app/dashboard.py` (solo se agregó el enlace «Resultados» al menú de `dashboard.html`,
  con OK explícito del usuario). Permite: buscar/filtrar, subir PDF (orden o NIT),
  compartir (publicar + notificación + Telegram) y descargar por signed URL.
- **Autenticación del portal: Supabase Auth (GoTrue)**, no tabla de credenciales propia.
  El login usa el password grant REST con `SUPABASE_ANON_KEY`; solo entran cuentas con
  `app_metadata.portal_role == "client"` y `client_id` (editable solo con service role).
  Alta de usuarios únicamente por CLI: `tools/scripts/create_portal_user.py`.
- **Aislamiento:** las vistas cliente usan exclusivamente `session["portal_client_id"]`;
  nunca aceptan client_id por query/form. Detalle/PDF verifican pertenencia y
  `published=true`.
- **Resultados PDF:** el personal los sube desde el dashboard (`/resultados`) → bucket
  privado `lab-results` (Supabase Storage) + tabla `lab_results` (migración 015).
  Descarga solo por signed URL de 5 minutos. Compartir = `published=true`, notificación
  en el portal y aviso Telegram si hay chat en `telegram_sessions` (un fallo del aviso
  no revierte la publicación).
- **Notificaciones:** tabla `portal_notifications` (migración 015), generadas por el
  backend (solicitud creada, resultado publicado), con leído/no leído.
- **Solicitud de retiro:** reutiliza `db.create_request` intacto (corte 17:30, motorizado
  determinista, order_number). `entry_channel` cae al fallback `"telegram"` por el CHECK
  de la tabla núcleo; el origen real queda en `event_payload.source = "portal"`.
- **Perfil del cliente: solo lectura** — `phone` es clave de identificación del agente y
  `address/zone` gobiernan la asignación territorial; editar rompería el determinismo.

## Consecuencias

- Dos nuevas env vars: `SUPABASE_ANON_KEY`, `PORTAL_RESULTS_BUCKET` (default lab-results).
- La migración `db/migrations/015_portal_results_notifications.sql` requiere
  `SUPABASE_ACCESS_TOKEN` (o el SQL Editor) — la service role no puede crear tablas.
- Tests: `tests/test_portal_auth.py`, `tests/test_portal_client.py`,
  `tests/test_dashboard_results.py` (aislamiento por client_id, sesiones separadas
  portal/dashboard, validación de PDF, publicación resistente a fallos de Telegram).

## Actualización 2026-08-27 — el portal sale del modo demostración

`PORTAL_DEMO_MODE` pasa a `false`: cada veterinaria entra con **el nombre de su clínica y su
NIT** y ve solo lo suyo. El código de la demo se conserva (apagado) para poder mostrar el
portal en una reunión; en producción va siempre en `false`.

Qué se ajustó al destaparlo:

- La sesión guarda `portal_clinic_name`. Con la demo, el menú lateral y el perfil mostraban
  `portal_email` (`demo@a3test.com`), que con login real se borra a propósito y dejaba esos
  dos lugares vacíos. Ahora el menú muestra la sede y el perfil, el correo real de `clients`.
- El perfil dice explícitamente cómo se accede («Nombre de la veterinaria + NIT»), en vez de
  hablar de un «correo de acceso» que ya no existe.

**Quiénes quedan fuera:** los **161 clientes activos sin NIT** (19% de 842) no pueden entrar,
porque el NIT es la llave. Se exportan con `tools/scripts/export_clientes_sin_nit.py` para que
A3 complete el dato — el mismo que hace falta para facturarles. Mientras tanto siguen pidiendo
por Telegram, que no cambió.

**Sobre el NIT como contraseña:** no es un secreto (está en las facturas y en el RUT). Es la
decisión de acceso de A3, y el portal la protege con lo razonable: 10 intentos por IP cada 5
minutos y un error único que no revela si un NIT existe. Si más adelante quieren cerrarlo, el
camino natural es una clave que el laboratorio entregue al dar de alta la clínica.

Verificado de punta a punta el 27/08 contra clientes reales: login correcto, nombre que no
corresponde al NIT, NIT inexistente, NIT con dos sedes (aparece el selector y re-valida), y
aislamiento comprobado contra la base — «Ama Tu Mascota» ve sus 6 facturas y «Zoomascotas
Veraguas» sus 19, ninguna de la otra.
