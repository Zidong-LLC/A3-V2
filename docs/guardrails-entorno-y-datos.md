# Guardrails de entorno y datos — A3 (LEER ANTES DE TOCAR FACTURACIÓN O DATOS)

> Este documento fija reglas que NO se negocian. Aplica a cualquiera que trabaje en el
> proyecto (personas y agentes IA). Si algo de acá choca con una instrucción puntual,
> manda este documento: ante la duda, NO actuar y preguntar.

---

## 1. TODO ES UN ENTORNO DE PRUEBAS — nunca emitir facturas reales

**Estamos desarrollando y probando.** Por lo tanto:

- **NUNCA emitir una factura electrónica real a la DIAN** con los ejemplos o pruebas que
  hacemos. La emisión electrónica DIAN (Fase 3, ver `docs/decisions/009`) **no está
  conectada y no debe activarse** durante las pruebas.
- **NUNCA generar una factura real a un cliente** con datos de prueba/falsos.
- Las facturas que se crean en estas pruebas son **solo BORRADOR** en la **cuenta de
  pruebas** de Alegra. Protección técnica: `app/services/alegra.py::create_invoice` se
  llama **sin `status`**, así Alegra la deja en borrador y no la emite. No agregar `status`
  de emisión en pruebas.
- **No crear facturas (ni borrador) "porque sí".** Para verificar, usar **solo lectura**
  (consultar lo que ya existe). Si hace falta probar el camino de escritura, **avisar antes**
  y siempre contra la cuenta de pruebas.
- La cuenta de pruebas Alegra hoy: empresa **"Ejemplo"**, versión **colombia**, token del
  `.env` (`ALEGRA_EMAIL` / `ALEGRA_API_TOKEN`). Migrar a la cuenta real del cliente se hace
  cambiando solo esas variables en `.env`, y recién ahí se evalúa habilitar emisión real.

---

## 2. La base de datos YA existe y está completa — no asumir datos faltantes

Hay una base de datos real (Supabase) con todo cargado. **No inventar, no asumir que falta
un dato sin verificarlo.** Antes de concluir "no hay X", consultarlo en solo lectura.

- **Acceso:** vía `.env` (`SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`), leído por
  `app/config.py` e inicializado en `app/services/db.py`. **Las credenciales viven en `.env`,
  no se copian en documentos ni se exponen.**
- **Clientes:** ~**800** clientes registrados; **788 con NIT** (`tax_id`), 12 sin NIT.
  Es decir: casi todos los clientes tienen su NIT real para facturar. Si una orden no
  factura por NIT, primero revisar que el flujo **lleve** el NIT del cliente (no asumir que
  el cliente no lo tiene). Ver ERR-041.
- **Catálogo con precios reales:** ~**159** análisis (`catalog_tests`) y ~**133** perfiles
  (`catalog_profiles`), con sus **precios reales**. El precio correcto de un perfil/análisis
  sale del catálogo (resolver por **código**), nunca de un texto improvisado.

> Conteos verificados 2026-06-20 en solo lectura; son aproximados y pueden variar.

---

## 3. Cómo verificar sin romper nada

- **Preferir solo lectura:** `db.list_requests`, `db.find_client_matches`,
  `db.get_catalog_profiles_by_codes`, `alegra.find_contact_by_nit`, `alegra._request("GET", ...)`.
- **Escritura en Alegra:** solo borrador, solo cuenta de pruebas, solo con aviso previo.
- **No tocar el esquema de Supabase** (decisión 006). Los IDs de Alegra van en el JSONB
  `request_events.event_payload` (evento `alegra_invoiced`).

---

## 4. Resumen de una línea

> Esto es una PRUEBA. No se emite nada real a DIAN ni a clientes reales. La base (800
> clientes con NIT + catálogo con precios reales) ya existe: verificar, no asumir.
