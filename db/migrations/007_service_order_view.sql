-- Vista de lectura para ordenes de servicio generadas por el agente.
-- No altera tablas existentes: extrae el contrato service_order desde request_events.event_payload.

CREATE OR REPLACE VIEW service_orders AS
SELECT
    re.request_id,
    re.id AS event_id,
    re.created_at,
    re.event_payload::jsonb #>> '{service_order,date}' AS service_order_date,
    re.event_payload::jsonb #>> '{service_order,requesting_doctor}' AS requesting_doctor,
    re.event_payload::jsonb #>> '{service_order,clinic_name}' AS clinic_name,
    re.event_payload::jsonb #>> '{service_order,clinic_phone}' AS clinic_phone,
    re.event_payload::jsonb #>> '{service_order,pickup_address}' AS pickup_address,
    re.event_payload::jsonb #>> '{service_order,patient,name}' AS patient_name,
    re.event_payload::jsonb #>> '{service_order,patient,species}' AS species,
    re.event_payload::jsonb #>> '{service_order,patient,breed}' AS breed,
    re.event_payload::jsonb #>> '{service_order,patient,sex}' AS sex,
    re.event_payload::jsonb #>> '{service_order,patient,age}' AS patient_age,
    re.event_payload::jsonb #>> '{service_order,patient,owner_name}' AS owner_name,
    re.event_payload::jsonb #>> '{service_order,exam_type}' AS exam_type,
    re.event_payload::jsonb #>> '{service_order,observations}' AS observations,
    re.event_payload::jsonb #>> '{service_order,payment_method}' AS payment_method
FROM request_events re
WHERE re.event_type = 'created'
  AND re.event_payload::jsonb ? 'service_order';

COMMENT ON VIEW service_orders IS
    'Ordenes de servicio conversacionales extraidas de request_events.event_payload.service_order.';
