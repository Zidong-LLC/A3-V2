# 015 — Recepción: contramuestras, recolección efectiva y borrado de órdenes

**Fecha:** 2026-11-09 · **Decide:** el usuario, sobre un pedido escrito de A3.

A3 pidió cuatro cosas para la plataforma. Quedaron así:

## Contramuestra (no se factura)

Una contramuestra es una segunda muestra para confirmar el resultado de un examen. Se carga en
«Nueva Orden» eligiendo **Cobro → Contramuestra**. Se recoge como cualquier orden (motorizado, fecha,
aviso) pero **no abre pedido**, y como la factura se arma por pedido, nada la factura. Tampoco guarda
precios: lo elegido queda solo como texto.

No se agregó ninguna columna. La marca es el texto del análisis, que empieza con `Contramuestra`, y la
nota `CONTRAMUESTRA: no se factura.` en las observaciones (`app/orden_manual.py`). La pantalla de
Pedidos la muestra con el rótulo «No se factura» dentro de «Órdenes sin pedido».

## Recolección efectiva

Hay clientes que no programan ruta porque el motorizado pasa siempre y recoge lo que haya. Recepción
la registra después en «Nueva Orden» con **Recogida → Ya recolectada**, la fecha y quién la trajo. La
orden nace en estado «Recogida», no le avisa al motorizado y se factura como cualquier otra.

## Recepción arma el borrador

Recepción puede usar «Facturar» en Pedidos (`permissions.puede_facturar_pedido`). Sigue sin entrar al
módulo de Facturación. Es un borrador en Alegra: la emisión no cambia, la hace A3 desde Alegra.

## Eliminar una orden o quitarle un análisis

El pedido de A3 («eliminar registros puntuales de los clientes») no era borrar clientes: era poder
sacar una orden o un análisis que se cargó mal o de más. Se hace desde Pedidos, con estas reglas
(`app/dashboard_ordenes.py`):

- Antes de tocar se guarda la foto completa en `audit_log` (entidad `request`). Sin respaldo no se borra.
- No se toca una orden con muestras o resultados en el laboratorio, un pedido que sigue abierto en el
  chat, un pedido ya pagado en línea, ni un pedido cuya factura ya fue emitida.
- La plataforma **no modifica Alegra**. Si el pedido ya tiene borrador, avisa que hay que corregirlo allá.
- Al quitar un análisis se conservan los precios con los que se cotizó y se recalcula el total con la
  misma cuenta que usa la factura.

La regla de borrado de **clientes** no cambió: sin movimientos se elimina, con historia se desactiva.

## Nombres en la carga masiva

Con la casilla «actualizar también los nombres» la carga renombra al cliente cuando el NIT lo
identifica sin dudas: un solo cliente con ese NIT y una sola fila con ese NIT en el archivo. Las sedes
que comparten NIT no se renombran por archivo. El contacto en Alegra no se toca.
