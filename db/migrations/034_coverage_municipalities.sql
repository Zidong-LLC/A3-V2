-- 034: Municipios cercanos en la cobertura (cierre de la versión 1, 2026-10-19).
-- A3 atiende clínicas de Soacha, Chía, Sibaté y otros municipios que estaban en la base
-- desde el comienzo, pero la cobertura y el mapa solo tenían las 20 localidades de Bogotá.
-- Cada municipio funciona como una localidad más: su motorizado se guarda en
-- courier_locality_coverage con locality_code = code (prefijo «mun_»).
-- Solo agrega una tabla: no modifica ninguna existente.

CREATE TABLE IF NOT EXISTS coverage_municipalities (
    code       text PRIMARY KEY,               -- mun_soacha
    name       text NOT NULL,
    lat        double precision,
    lng        double precision,
    is_active  boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE coverage_municipalities IS
    'Municipios cercanos a Bogotá que A3 atiende; se administran desde Motorizados → Cobertura';

-- Los que A3 nombró en sus preguntas (16/09) y en la última reunión.
INSERT INTO coverage_municipalities (code, name, lat, lng) VALUES
    ('mun_soacha',   'Soacha',   4.5794, -74.2168),
    ('mun_chia',     'Chía',     4.8633, -74.0303),
    ('mun_sibate',   'Sibaté',   4.4919, -74.2594),
    ('mun_mosquera', 'Mosquera', 4.7078, -74.2328),
    ('mun_funza',    'Funza',    4.7163, -74.2116),
    ('mun_madrid',   'Madrid',   4.7322, -74.2643),
    ('mun_cota',     'Cota',     4.8093, -74.0985)
ON CONFLICT (code) DO NOTHING;

ALTER TABLE coverage_municipalities ENABLE ROW LEVEL SECURITY;
