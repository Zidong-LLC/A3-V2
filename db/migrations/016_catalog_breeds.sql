-- Ejecutar en el SQL Editor de Supabase
-- Catalogo de RAZAS por especie. Permite al agente normalizar la grafia de la raza
-- que dice el cliente e inferir la especie cuando la raza es inequivoca.
-- Una raza ambigua (Criollo, Mestizo) ocupa VARIAS filas, una por especie: de ahi
-- se deriva la ambiguedad al cargar, sin columna que marcarla.

CREATE TABLE IF NOT EXISTS catalog_breeds (
    breed_key text NOT NULL,   -- catalog_item_key(name): 'pastor_aleman'
    name      text NOT NULL,   -- grafia canonica: 'Pastor Aleman'
    species   text NOT NULL,   -- canonico de app/species.py
    is_active boolean DEFAULT true,
    PRIMARY KEY (breed_key, species)
);

CREATE INDEX IF NOT EXISTS idx_catalog_breeds_species ON catalog_breeds (species);

ALTER TABLE catalog_breeds ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Service can manage catalog breeds" ON catalog_breeds
    FOR ALL USING (true) WITH CHECK (true);

COMMENT ON TABLE catalog_breeds IS
    'Raza -> especie (323 razas / 14 especies). Fuente: Excel "Lista de Especies con Raza" del cliente.';
