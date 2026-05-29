# Orden de servicio conversacional

## Archivo fuente

El PDF oficial esta versionado en:

```text
docs/forms/orden-de-servicio-2025.pdf
```

## Flujo aprobado

La orden de servicio se gestiona despues de identificar la veterinaria y confirmar
la direccion de retiro.

Secuencia:

1. Detectar solicitud de ruta.
2. Identificar cliente por NIT o nombre.
3. Confirmar direccion registrada o capturar direccion corregida.
4. Capturar los datos de la orden, uno por turno.
5. Preguntar forma de pago.
6. Mostrar resumen final.
7. Crear `requests` y registrar evento `created` con `service_order`.
8. Preguntar si necesita crear otra orden de servicio para otro paciente o animal.

Si el cliente responde que si necesita otra orden, el agente conserva cliente,
direccion y telefono de contacto, limpia los datos de la orden anterior y empieza
una nueva orden por `requesting_doctor`. Si responde que no, cierra la
conversacion con despedida sin reiniciar el flujo.

## Datos capturados por el agente

- `requesting_doctor`: medico solicitante
- `clinic_phone`: telefono de contacto
- `exam_type`: analisis o perfil
- `patient_name`: paciente
- `species`: especie
- `breed`: raza
- `sex`: sexo
- `patient_age`: edad
- `owner_name`: propietario
- `observations`: observaciones
- `payment_method`: forma de pago

## Persistencia

La tabla principal `requests` conserva los campos operativos existentes.
La orden completa se guarda en:

```text
request_events.event_payload.service_order
```

## Visibilidad en plataforma

Cuando el agente crea una orden de servicio, la plataforma la muestra desde los
eventos de la solicitud, sin depender de tablas nuevas:

- `/operacion`: aparece en `Ordenes del dia`, en `Agenda por motorizado` y en
  `Rutas para gestionar` con paciente y analisis.
- `/muestras`: aparece en `Ordenes de servicio agendadas` con formato visual
  similar al PDF y tambien se suma al tablero de proceso como orden pendiente de
  retiro.
- Cada ficha tiene enlace `Imprimir PDF`, que abre
  `/ordenes-servicio/<request_id>/imprimir` con una version lista para imprimir o
  guardar como PDF desde el navegador.

La fuente de verdad para el detalle visual es
`request_events.event_payload.service_order`.

Ejemplo de consulta directa:

```sql
SELECT
    request_id,
    event_payload::jsonb #>> '{service_order,requesting_doctor}' AS requesting_doctor,
    event_payload::jsonb #>> '{service_order,patient,name}' AS patient_name,
    event_payload::jsonb #>> '{service_order,exam_type}' AS exam_type
FROM request_events
WHERE event_type = 'created'
  AND event_payload::jsonb ? 'service_order';
```

## Vista Supabase

La migracion aditiva `db/migrations/007_service_order_view.sql` crea la vista
`service_orders` para consultar las ordenes sin parsear JSON manualmente.

Aplicacion manual:

```bash
python tools/scripts/apply_supabase_migration.py --migration db/migrations/007_service_order_view.sql
```

Requiere `SUPABASE_ACCESS_TOKEN` o aplicar el SQL manualmente desde el SQL Editor

## Verificacion

Ejecutar:

```bash
python -m pytest
```
