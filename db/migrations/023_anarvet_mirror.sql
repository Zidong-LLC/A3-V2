-- Ejecutar en el SQL Editor de Supabase
-- Espejo de solo lectura de fn_reporte_examenes (Anarvet), Fase 1 — ver decisión 013.
-- NO modifica tablas existentes (alineado con decisiones 006 y 009): son dos tablas
-- nuevas, igual que invoices_cache. La fuente de verdad sigue siendo Anarvet; el espejo
-- existe para consultar rápido sin depender de su servidor y para el mapeo de clientes.
-- Tipos confirmados con datos reales (smoke 2026-08-25): todas las fechas llegan como
-- date (fec_val incluida, NO timestamp).

-- Un registro por analito con resultado. dedup_key la calcula Python:
-- sha1("codigo|fechasolicitud|examenes|analito_cod") — excluye resultado/fec_val para
-- que una re-validación del mismo analito haga UPDATE (upsert) y no duplique.
CREATE TABLE IF NOT EXISTS anarvet_results (
    dedup_key text PRIMARY KEY,
    fecha_solicitud date,
    codigo text,                 -- código del paciente en Anarvet
    cod_cliente text,
    nombre_cliente text,
    nombre_propietario text,
    mascota text,                -- columna "nombre" del reporte
    especie text,
    raza text,
    nacio date,
    genero text,
    usu_validador text,
    examen_cod text,             -- columna "examenes" del reporte
    analito_cod text,
    analito text,
    resultado text,              -- siempre texto: mezcla números y cualitativos
    fec_val date,
    raw jsonb NOT NULL DEFAULT '{}'::jsonb,
    synced_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_anarvet_results_cliente ON anarvet_results (cod_cliente);
CREATE INDEX IF NOT EXISTS idx_anarvet_results_fecha ON anarvet_results (fecha_solicitud DESC);
CREATE INDEX IF NOT EXISTS idx_anarvet_results_paciente ON anarvet_results (codigo);

-- Mapeo cod_cliente de Anarvet -> clients. NO se reutiliza clients.external_code:
-- ese campo ya significa "código cliente interno" del legacy y es editable en el
-- dashboard — una edición manual rompería el vínculo Anarvet en silencio.
CREATE TABLE IF NOT EXISTS anarvet_client_map (
    cod_cliente text PRIMARY KEY,
    nombre_cliente text,                          -- último nombre visto (para revisión)
    client_id uuid REFERENCES clients(id),
    match_source text NOT NULL DEFAULT 'pending', -- pending | auto | manual | none
    matched_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_anarvet_client_map_status ON anarvet_client_map (match_source);

ALTER TABLE anarvet_results ENABLE ROW LEVEL SECURITY;
ALTER TABLE anarvet_client_map ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Dashboard can manage anarvet results" ON anarvet_results
    FOR ALL USING (true) WITH CHECK (true);

CREATE POLICY "Dashboard can manage anarvet client map" ON anarvet_client_map
    FOR ALL USING (true) WITH CHECK (true);
