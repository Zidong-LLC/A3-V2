-- Ejecutar en el SQL Editor de Supabase
-- Correo de contacto del cliente, necesario para FACTURACION ELECTRONICA.
--
-- Por que en `clients` y no en `clients_a3_knowledge` (que ya tiene un campo email):
-- knowledge se indexa por nombre normalizado (clinic_key), no por NIT ni client_id, y el
-- agente NUNCA la lee. `clients` es la unica tabla que el flujo consulta al identificar al
-- cliente, asi que es el unico lugar desde donde el correo puede llegar a Alegra al facturar.
-- Rompe deliberadamente la convencion de no tocar `clients` (decisiones 006 y 009); es
-- aditivo y nullable, ningun codigo existente asume un set fijo de columnas.

ALTER TABLE clients
    ADD COLUMN IF NOT EXISTS email text;

COMMENT ON COLUMN clients.email IS
    'Correo de contacto para facturacion electronica (se envia a Alegra al crear el contacto). Fuente: Excel "Alegra - Terceros".';
