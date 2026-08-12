-- Ejecutar en el SQL Editor de Supabase
-- Perfiles favoritos por clinica: contar USOS para poder ofrecer "los que mas pide".
--
-- A3 lo pidio el 06/05 (llamada 3, punto 12): que el agente reofrezca los perfiles que cada
-- veterinaria ya armo. La tabla client_custom_profiles existe desde la migracion 009 pero
-- solo guarda created_at, asi que hoy no hay forma de ordenar por frecuencia de uso.
--
-- Aditiva: solo agrega columnas a una tabla existente. Las filas que ya estan quedan con
-- usage_count = 1, que es exactamente lo que significan (se guardaron una vez desde el
-- dashboard).

ALTER TABLE client_custom_profiles
    ADD COLUMN IF NOT EXISTS usage_count int NOT NULL DEFAULT 1;

ALTER TABLE client_custom_profiles
    ADD COLUMN IF NOT EXISTS last_used_at timestamptz;

-- Firma del conjunto de items: permite reconocer que la clinica volvio a pedir LO MISMO y
-- sumar al contador, en vez de crear un favorito nuevo cada vez (save_custom_profile es un
-- INSERT puro). Se calcula en la aplicacion; aca solo se indexa.
ALTER TABLE client_custom_profiles
    ADD COLUMN IF NOT EXISTS items_signature text;

-- Orden natural de la consulta del agente: los mas pedidos de esta clinica, primero.
CREATE INDEX IF NOT EXISTS idx_custom_profiles_client_usage
    ON client_custom_profiles (client_id, usage_count DESC, last_used_at DESC);

-- Evita duplicados por firma dentro de la misma clinica. Parcial porque client_id es
-- nullable y items_signature solo lo llenan las filas que crea el agente.
CREATE UNIQUE INDEX IF NOT EXISTS uniq_custom_profiles_client_signature
    ON client_custom_profiles (client_id, items_signature)
    WHERE client_id IS NOT NULL AND items_signature IS NOT NULL;

COMMENT ON COLUMN client_custom_profiles.usage_count IS
    'Cuantas veces esta clinica pidio este mismo conjunto. Ordena los favoritos que ofrece el agente.';
COMMENT ON COLUMN client_custom_profiles.items_signature IS
    'Huella del conjunto de items, para sumar al contador en vez de duplicar la fila.';
