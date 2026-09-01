# Guardrails de entorno y datos — A3 (LEER ANTES DE TOCAR FACTURACIÓN O DATOS)

> Este documento fija reglas que NO se negocian. Aplica a cualquiera que trabaje en el
> proyecto (personas y agentes IA). Si algo de acá choca con una instrucción puntual,
> manda este documento: ante la duda, NO actuar y preguntar.

---

## 1. CUENTA REAL DE ALEGRA — solo BORRADORES, nunca emitir a la DIAN

**Desde el 2026-08-27 el `.env` apunta a la cuenta REAL del cliente**
(`laboratorioveterinarioa3@gmail.com` — empresa «A3 LABORATORIO CLINICO VETERINARIO SAS»,
NIT 900296338, Colombia, Responsable de IVA). Todo lo que se cree ahí lo ve el contador de
A3 y convive con sus 660+ facturas reales. Por eso:

- **NUNCA emitir una factura electrónica a la DIAN desde la plataforma.** `ALEGRA_PRODUCTION`
  queda en `false`. Protección técnica: `app/services/alegra.py::create_invoice` se llama
  **sin `status`**, así Alegra la deja en BORRADOR. **No agregar un `status` de emisión.**
  Quien emite es A3, revisando el borrador desde Alegra.
- **No crear facturas ni contactos «porque sí».** Para verificar, usar **solo lectura**
  (`ping`, `/company`, listar contactos/ítems/facturas). Si hace falta probar el camino de
  escritura, **avisar antes y esperar el OK** — cada borrador queda en la cuenta del cliente.
- **No borrar ni modificar nada que ya exista en Alegra** (contactos, ítems, facturas):
  el catálogo y los contactos del cliente ya están cargados ahí desde antes.
- **A nombre de quién sale la factura** lo decide `clients.electronic_invoice`
  (migración 028): `true` → al NIT y razón social del cliente; `false` → al contacto
  genérico **Consumidor Final** (id=1, identificación 222222222222) con el nombre de la
  veterinaria o el médico en las **notas** (`anotation`). La regla vive en
  `app/billing.py::invoice_target`. **No facturar todo a Consumidor Final**: era el problema
  que A3 pidió corregir.

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
