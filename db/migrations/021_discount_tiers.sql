-- Ejecutar en el SQL Editor de Supabase
-- Tramos del descuento por volumen, editables desde la plataforma.
--
-- Hasta ahora los tramos vivian hardcodeados en app/config.py (DISCOUNT_TIERS) y cambiarlos
-- exigia un deploy. A3 pidio editarlos desde la plataforma en la llamada 6 (27/05). El codigo
-- mantiene la constante como FALLBACK: si esta tabla esta vacia o Supabase no responde, el
-- agente cotiza con los tramos de config.py — nunca cotiza sin descuento por un fallo de infra.
--
-- La auditoria de cambios reusa catalog_audit con source_table='discount_tiers'.
--
-- Tabla NUEVA, no toca nada existente (mismo patron que 009, 013, 014, 018, 019 y 020).

CREATE TABLE IF NOT EXISTS discount_tiers (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    -- Minimo de pruebas descontables para alcanzar el tramo.
    min_tests  int  NOT NULL UNIQUE CHECK (min_tests >= 2),
    -- Porcentaje como fraccion (0.12 = 12%).
    pct        numeric(5, 4) NOT NULL CHECK (pct >= 0 AND pct < 1),
    updated_by text,
    updated_at timestamptz NOT NULL DEFAULT now()
);

-- Seed: los 14 tramos vigentes de app/config.py, para que la tabla nunca arranque vacia.
INSERT INTO discount_tiers (min_tests, pct) VALUES
    (2, 0.12), (3, 0.13), (4, 0.14), (5, 0.16), (6, 0.18),
    (7, 0.19), (8, 0.20), (9, 0.21), (10, 0.22), (11, 0.23),
    (12, 0.24), (13, 0.25), (14, 0.26), (15, 0.27)
ON CONFLICT (min_tests) DO NOTHING;

COMMENT ON TABLE discount_tiers IS
    'Tramos del descuento por volumen editables desde la plataforma. Fallback: DISCOUNT_TIERS de config.py.';
