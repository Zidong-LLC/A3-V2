-- Ejecutar en el SQL Editor de Supabase
-- Etiquetas diagnosticas por prueba: permite sugerir las pruebas que conforman
-- un perfil clinico (CARDIACO, SENIOR CANINO, HEPATICO, PREQUIRURGICO, etc.)
-- El cliente escoge dentro de lo sugerido y puede agregar otras pruebas.

CREATE TABLE IF NOT EXISTS diagnostic_label_tests (
    id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    label     text NOT NULL,
    test_code text NOT NULL,
    UNIQUE (label, test_code)
);

CREATE INDEX IF NOT EXISTS idx_diag_label ON diagnostic_label_tests (label);
CREATE INDEX IF NOT EXISTS idx_diag_test  ON diagnostic_label_tests (test_code);

ALTER TABLE diagnostic_label_tests ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Service can manage diagnostic labels" ON diagnostic_label_tests
    FOR ALL USING (true) WITH CHECK (true);

COMMENT ON TABLE diagnostic_label_tests IS
    'Mapeo etiqueta diagnostica -> codigo de prueba (catalog_tests.code). Fuente: sheet de etiquetas A3.';
