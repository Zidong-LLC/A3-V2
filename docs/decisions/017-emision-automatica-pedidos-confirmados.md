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

## Quién elige: A3, desde Facturación

Pedido del usuario (mismo día): que A3 lo maneje sin depender de soporte. En Facturación hay un
recuadro «Emisión a la DIAN» con tres modos (tabla `emision_ajustes`, migración 042):

- **Manual** (como nace): nada se emite solo; una persona usa el botón «Emitir» de cada pedido.
- **Automática solo para algunos clientes**: para probar con uno o pocos clientes elegidos.
- **Automática para todos**.

Lo cambian solo los perfiles que gestionan Facturación (Administrador y Auxiliar administrativa);
cada cambio queda en `audit_log`. Si la tabla no se puede leer, el modo es manual.

## Candados

- Interruptor general `ALEGRA_EMISSION_ENABLED` en Render (decisión 016), en `false` en
  `render.yaml`: apagado, no se emite nada, ni con el botón ni solo. La pantalla lo avisa.
- Emite por la única puerta, `emision.emitir`: relee la factura en Alegra (tiene que ser borrador
  con total), candado contra doble emisión y `audit_log` de cada intento.
- Corre en segundo plano (`app/emision_automatica.py`): el portal y el aviso de Wompi no esperan.
- Si Alegra no emite, el pedido queda en borrador y llega el aviso técnico de error.
- Un test vigila que solo el botón y este módulo llamen a `emision.emitir`.

## Para encenderla (en este orden)

1. Aplicar la migración 042 y encender `ALEGRA_EMISSION_ENABLED=true` (OK explícito del usuario).
   El modo queda en Manual: solo emite el botón.
2. **Primera emisión acompañada:** una persona de A3 emite con el botón UNA factura real que quieran
   emitir. Se verifica en Alegra y que el correo llegue al cliente («validar envío por correo»).
3. A3 pasa a «solo algunos clientes» para probar, y después a «todos» cuando quiera.
4. Para frenar todo: modo Manual en la pantalla; en una emergencia, `ALEGRA_EMISSION_ENABLED=false`.

Una factura emitida no se deshace: se corrige con nota crédito en Alegra.
