-- Ejecutar en el SQL Editor de Supabase
-- Secciones del catálogo que el seed original NUNCA cargó: Convenio SERVIPAT (pág. 9
-- del PDF "A3 - Catalogo 2025") y Convenio LMV (pág. 18). El seed 002 transcribió las
-- págs. 3-8 y se detuvo antes de los convenios — por eso el 1903 (Citología PAF) no
-- existía y el agente lo ignoró en silencio en el test en vivo del 2026-08-21.
--
-- Mascolab (págs. 19-27) queda PENDIENTE a propósito: tiene doble precio (Punto Final /
-- Tiempo Real) y A3 debe confirmar cuál rige. Ver docs/catalogo-mascolab-pendiente.md.
--
-- Precios especiales (decisión del usuario 2026-08-21): 2509 al precio base $85.000 con
-- nota de variabilidad en el nombre; 2226 a $1.200.000 con nota (varía por dólar);
-- 2507 es valor POR KILO.
--
-- ON CONFLICT DO NOTHING (no DO UPDATE): el catálogo es editable desde el dashboard
-- (migración 020/llamada de catálogo) — re-ejecutar esta migración no debe pisar
-- precios ajustados a mano después.

INSERT INTO catalog_tests (code, name, category, species, sample, price) VALUES

-- ── CONVENIO SERVIPAT (pág. 9 — entrega 8 días hábiles) ──────────────────────
('1903', 'Citología PAF',                                        'Convenio SERVIPAT', 'ambos', 'Enviar 3 láminas (entrega 8 días hábiles)', 52000),
('2501', 'Histopatológico Rutina',                               'Convenio SERVIPAT', 'ambos', 'Muestra en formol al 10%', 95000),
('2508', 'Histopatológico Coloraciones Especiales',              'Convenio SERVIPAT', 'ambos', 'Muestra en formol al 10%', 87000),
('2509', 'Inmunohistoquímicas (desde $85.000 según marcador)',   'Convenio SERVIPAT', 'ambos', 'Muestra en formol al 10%', 85000),
('2504', 'Necropsia < 500 g',                                    'Convenio SERVIPAT', 'ambos', 'Enviar refrigerado', 200000),
('2505', 'Necropsia 500 g a < 10 kg',                            'Convenio SERVIPAT', 'ambos', 'Enviar refrigerado', 250000),
('2506', 'Necropsia > 10 kg',                                    'Convenio SERVIPAT', 'ambos', 'Enviar refrigerado', 300000),
('2507', 'Disposición de cadáver (valor por kilo)',              'Convenio SERVIPAT', 'ambos', 'Junto al envío para necropsia', 12000),
('2226', 'Serología de Rabia (precio varía por dólar)',          'Convenio SERVIPAT', 'ambos', 'Comunicarse con el laboratorio', 1200000),

-- ── CONVENIO LMV (pág. 18 — inmunológicos IFA, montaje según día) ────────────
('2301', 'Brucella canis (2-Mercaptoetanol)',                    'Convenio LMV', 'canino', 'Tubo Rojo o Amarillo', 85000),
('2302', 'Brucella canis Anticuerpos IgG (IFA)',                 'Convenio LMV', 'canino', 'Tubo Rojo o Amarillo y Tapa Morada', 104000),
('2303', 'Ehrlichia canis Anticuerpos IgG (IFA)',                'Convenio LMV', 'canino', 'Tubo Rojo o Amarillo y Tapa Morada', 104000),
('2304', 'Leishmaniasis canina Anticuerpos IgG (IFA)',           'Convenio LMV', 'canino', 'Tubo Rojo o Amarillo y Tapa Morada', 119000),
('2305', 'Leptospira 6 serovariedades (IFA)',                    'Convenio LMV', 'ambos',  'Tubo Rojo o Amarillo', 95000),
('2306', 'Moquillo Canino (Distemper) Anticuerpos IgM (IFA)',    'Convenio LMV', 'canino', 'Tubo Rojo o Amarillo y Tapa Morada', 124000),
('2307', 'Neospora caninum Anticuerpos IgG (IFA)',               'Convenio LMV', 'canino', 'Tubo Rojo o Amarillo', 104000),
('2308', 'Babesia canis Anticuerpos IgG (IFA)',                  'Convenio LMV', 'canino', 'Tubo Rojo o Amarillo', 127000),
('2309', 'Peritonitis Infecciosa Felina Anticuerpos IgG (IFA)',  'Convenio LMV', 'felino', 'Tubo Rojo o Amarillo y Tapa Morada', 104000),
('2310', 'Toxoplasma gondii Anticuerpos IgG (IFA)',              'Convenio LMV', 'ambos',  'Tubo Rojo o Amarillo y Tapa Morada', 104000),
('2311', 'Calicivirus Felino (IFA)',                             'Convenio LMV', 'felino', 'Tubo Rojo o Amarillo y Tapa Morada', 104000),
('2312', 'Panleucopenia Felina (IFA)',                           'Convenio LMV', 'felino', 'Tubo Rojo o Amarillo y Tapa Morada', 119000),
('2314', 'Anaplasma Canino (IFA)',                               'Convenio LMV', 'canino', 'Tubo Rojo o Amarillo y Tapa Morada', 104000),
('2315', 'Herpes Felino (IFA)',                                  'Convenio LMV', 'felino', 'Tubo Rojo o Amarillo y Tapa Morada', 104000),
('2316', 'Bartonella Felino (IFA)',                              'Convenio LMV', 'felino', 'Tubo Rojo o Amarillo y Tapa Morada', 166000)

ON CONFLICT (code) DO NOTHING;
