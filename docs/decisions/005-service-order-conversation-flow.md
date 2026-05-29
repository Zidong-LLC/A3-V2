# 005 — Orden de servicio dentro del flujo conversacional

## Estado

Aprobada (2026-05-24)

## Contexto

El formulario oficial `Orden de servicio 2025.pdf` pide datos administrativos,
datos de veterinaria, datos del paciente, analisis solicitados, observaciones y
datos internos del laboratorio.

El agente conversacional debe completar la informacion necesaria para registrar
una orden sin convertir la conversacion en un formulario pesado y sin pedir datos
antes de saber si la veterinaria esta registrada.

## Decision

La orden de servicio se genera despues de identificar al cliente y confirmar la
direccion de retiro.

Flujo aprobado:

1. Detectar intencion de programar ruta.
2. Identificar veterinaria por NIT o nombre.
3. Confirmar direccion de retiro.
4. Iniciar la orden de servicio conversacional.
5. Preguntar un dato por turno hasta completar la orden.
6. Preguntar forma de pago.
7. Mostrar resumen final y crear la solicitud.
8. Notificar motorizado si existe asignacion.

Campos que el agente captura para la orden:

- Medico solicitante
- Telefono de contacto
- Analisis o perfil
- Nombre del paciente
- Especie
- Raza
- Sexo
- Edad
- Propietario
- Observaciones
- Forma de pago

Campos del PDF de uso interno del laboratorio no se preguntan al cliente:

- Valor cancelado
- R C No.
- Enviado por
- C x C No.
- Annar
- Factusol

## Persistencia en Supabase

La orden completa queda guardada en `request_events.event_payload.service_order`
cuando se crea la solicitud.

Para consulta operativa se agrega la migracion aditiva
`db/migrations/007_service_order_view.sql`, que crea la vista `service_orders`
leyendo ese JSON. No se alteran tablas existentes.

## Consecuencias

- El cliente no pierde tiempo completando una orden si no esta registrado.
- El bot mantiene una sola pregunta por turno.
- La plataforma puede consultar ordenes completas desde Supabase usando la vista
  `service_orders` cuando la migracion este aplicada.
- Los datos internos del laboratorio quedan fuera del chat y se manejan en la
  plataforma/operacion.

## Referencias

- Formulario fuente: `docs/forms/orden-de-servicio-2025.pdf`
- Prompt del agente: `app/prompt.py`
- Persistencia del evento: `app/services/db.py`
