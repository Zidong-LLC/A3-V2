# 009 — Integración de Alegra por fases

Fecha: 2026-06-19

**Supersede:** [008 — Allegra fuera de alcance por ahora](008-allegra-out-of-scope.md).

## Contexto

El caso "Pagos/facturación → siempre escala a contabilidad" es hoy una pared: el agente
captura `payment_method` y deriva a un humano que arma la factura y manda el link de pago
a mano (`PAYMENT_ONLINE_HANDOFF_MESSAGE` en `app/agent.py`). No se genera factura
electrónica en ningún sistema. La decisión 008 dejó Alegra fuera "hasta que exista una
especificación real". Esa especificación ya existe: el plan de integración por fases
acordado con el usuario.

Alegra es la plataforma de facturación electrónica + contabilidad con cumplimiento DIAN
Colombia. API REST con Basic auth `base64(email:api_token)` y base
`https://api.alegra.com/api/v1`.

## Decisión

Se reintroduce Alegra como módulo nuevo `app/services/alegra.py`, aislado (no importa
`agent.py` ni `rules.py`), siguiendo el patrón de `app/services/`. La integración avanza
por fases:

- **Fase 0** — Cuenta de pruebas, credenciales y feature flag `ALEGRA_ENABLED`.
- **Fase 1** — Cliente API base + sincronización de contactos por NIT (backend).
- **Fase 2** — Facturación electrónica DIAN automática al cerrar la orden (backend silencioso).
- **Fase 3** — Link de pago en el chat para `pago_linea` (depende de activar pagos
  electrónicos / Mercado Pago en Alegra). **Cambia el invariante de escalado** para ese caso.
- **Fase 4** — Consulta de facturas/saldo de autoservicio (read-only) dentro del intent
  `accounting`.

## Restricciones

- **Feature flag:** con `ALEGRA_ENABLED=false` el comportamiento del agente es idéntico al
  actual. Migrar de la cuenta de pruebas a la del cliente se hace cambiando solo
  `ALEGRA_EMAIL`/`ALEGRA_API_TOKEN` en `.env`, sin tocar código.
- **No se modifica el esquema de Supabase** (alineado con la decisión 006). Los IDs de
  Alegra (`alegra_contact_id`, `alegra_invoice_id`, `payment_url`) se guardan en el JSONB
  `request_events.event_payload`.
- Se reusa lo existente: `calculate_custom_profile_total` (`app/rules.py`) para totales y
  descuentos, y la normalización de NIT `_nit_candidates` (`app/services/db.py`).

## Consecuencia

- La suite `pytest` vuelve a incluir cobertura de Alegra, pero solo de lógica pura/mapeos;
  las llamadas reales a la API se validan con `scripts/alegra_smoke.py` contra la cuenta de
  pruebas, no en `pytest`.
- El plan vive en `tasks/todo.md`. Todo bug se registra en `tasks/errores-soluciones.md`.
