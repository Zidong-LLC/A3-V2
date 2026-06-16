# Decision 002 - Forma de pago en el flujo conversacional

## Fecha
2026-05-01

## Contexto
El flujo de programacion de ruta necesitaba registrar la forma de pago para integrar
mas adelante con la plataforma operativa (seguimiento por pedido y metodo de pago).

No se debe modificar el esquema de Supabase en esta etapa.

## Decision
1. Se agrega `payment_method` al `captured_fields` del schema del agente.
2. Antes de cerrar una solicitud de `route_scheduling`, el agente pregunta
   obligatoriamente por forma de pago:
   - `pago_linea`
   - `contraentrega`
3. Si el cliente elige `pago_linea`, el bot registra la ruta, conserva la recogida
   programada y deriva a contabilidad para enviar/validar el link de pago.
4. Si elige `contraentrega`, el flujo cierra sin derivacion.
5. El metodo de pago se persiste en `request_events.event_payload.payment_method`
   al crear el request.

## Consecuencias
- Se obtiene trazabilidad de pago por solicitud sin cambiar tablas de negocio.
- La integracion futura con plataforma puede leer el metodo de pago desde eventos.
- Se mantiene la regla de negocio de escalar pagos en linea a contabilidad.
