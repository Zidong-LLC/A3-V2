# 016 — Emisión ante la DIAN desde la plataforma: construida, apagada y solo con botón

**Fecha:** 2026-11-16 · **Decide:** el usuario («lo de emisión de Alegra hagámoslo también»).

## Qué cambia

Hasta hoy la regla era absoluta: la plataforma solo deja borradores y A3 emite desde Alegra. La
propuesta del 28/09 incluía la emisión final (3 h) y el usuario pidió construirla.

La regla nueva tiene dos mitades:

1. **Nada emite solo.** Ni el bot, ni el portal, ni «Nueva Orden», ni un cron. Todos siguen creando
   **borradores** (`ALEGRA_PRODUCTION=false`, `status: draft`). Eso no cambió.
2. **Una persona puede emitir un borrador ya revisado**, con el botón «Emitir a la DIAN» del pedido,
   y solo si `ALEGRA_EMISSION_ENABLED=true`. La variable nace en `false` en `render.yaml`.

## Candados (`app/emision.py`)

- Sin la variable, el botón no aparece y la ruta contesta 403.
- Solo perfiles que **gestionan Facturación** (Administrador y Auxiliar administrativa). Recepción
  arma borradores (decisión 015) pero no emite.
- El pedido tiene que estar «Facturado», es decir, con borrador en Alegra.
- Antes de emitir se lee la factura en Alegra: tiene que ser `draft` y tener total mayor a cero.
- Doble confirmación en pantalla y candado contra el doble clic.
- Queda en `audit_log` quién emitió qué, y también cada intento que Alegra rechazó.
- Un test recorre `app/` y falla si algo fuera de `emision.py` llama a `alegra.stamp_invoice`.

Se usa `POST /invoices/stamp` con `{"ids": ["<id>"]}`, que según la documentación de Alegra acepta
facturas en borrador o abiertas y contesta el resultado por factura.

## Lo que NO está verificado

No se emitió ninguna factura para probar: emitir es real e irreversible, y no hay cuenta de pruebas
conectada. Los tests usan la respuesta documentada por Alegra. Dos puntos de esa documentación son
ambiguos (si un borrador se timbra directo o hay que abrirlo antes, y el error 905 «no se puede
abrir»). **La primera emisión se hace con A3 mirando, sobre una factura que de verdad quieran emitir.**

## Para encenderla

1. A3 confirma quiénes emiten (hoy: Administrador y Auxiliar administrativa).
2. OK explícito del usuario para poner `ALEGRA_EMISSION_ENABLED=true` en Render y desplegar.
3. Primera emisión acompañada; si Alegra la rechaza, el motivo queda en el historial y en el log.

Una factura emitida no se deshace: se corrige con nota crédito en Alegra. Para apagar: la misma
variable en `false` y desplegar.
