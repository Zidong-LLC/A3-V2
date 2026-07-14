# 010 — Portal Web de clientes + módulo Resultados en el dashboard

**Fecha:** 2026-07-06 (revisada el mismo día: el portal queda SOLO para clientes)
**Estado:** Implementado (pendiente de aplicar migración 015 y configurar SUPABASE_ANON_KEY)

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
