# 017 — Emisión automática de los pedidos confirmados (construida, apagada)

**Fecha:** 2026-11-25 · **Decide:** el usuario («hagamos todos los cambios que ellos quieren»),
tras el informe de A3 sobre las pruebas.

## Por qué

A3 escribió: «Cada pedido genera su borrador de factura en Alegra… Quedó para manualmente, uno a
uno, generar la factura. A lo que en las dos propuestas está contemplado para ser automático».
La propuesta del 28/09 dice: *«Emisión final en Alegra: pasar de borrador a factura emitida según
confirmación del pedido y validar envío por correo»*. La decisión 016 había construido solo un
botón manual, apagado. La misma propuesta excluye la «automatización DIAN completa»: por eso se
emite solo lo que el cliente confirmó, no todo.

## Qué se emite solo

| Pedido | Cuándo se emite |
|---|---|
| Contraentrega | Apenas tiene borrador (el cliente eligió cómo paga al cerrar) |
| Pago en línea | Cuando Wompi aprueba el pago |
| Sin forma de pago (cerrado por inactividad) u otra | **No**: queda en borrador para revisar |
| Sin borrador (falló Alegra, cliente sin NIT) | **No** |

## Candados

- Dos interruptores, los dos en `false` en `render.yaml`: `ALEGRA_EMISSION_ENABLED` (la emisión,
  decisión 016) y `ALEGRA_AUTO_EMISSION` (que corra sola).
- Emite por la única puerta, `emision.emitir`: relee la factura en Alegra (tiene que ser borrador
  con total), candado contra doble emisión y `audit_log` de cada intento.
- Corre en segundo plano (`app/emision_automatica.py`): el portal y el aviso de Wompi no esperan.
- Si Alegra no emite, el pedido queda en borrador y llega el aviso técnico de error.
- Un test vigila que solo el botón y este módulo llamen a `emision.emitir`.

## Para encenderla (en este orden)

1. **Primera emisión acompañada:** `ALEGRA_EMISSION_ENABLED=true`, y una persona de A3 emite con el
   botón UNA factura real que quieran emitir. Se verifica en Alegra y que el correo llegue al cliente
   (la propuesta pide «validar envío por correo»).
2. Si salió bien: `ALEGRA_AUTO_EMISSION=true` y desplegar.
3. Para apagar: `ALEGRA_AUTO_EMISSION=false` y desplegar (el botón sigue).

Una factura emitida no se deshace: se corrige con nota crédito en Alegra.
