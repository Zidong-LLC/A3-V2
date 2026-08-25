"""Fase 1 — Tests del resolvedor puro `app/catalog.resolve_tests`.

Función sin I/O: se prueba directamente con el catálogo de referencia, sin mocks.
Verifica el principio del eje dinero: se agrega solo con match inequívoco; un término
genérico/de área se OFRECE, nunca se agrega a ciegas.
"""
from app import catalog
from app.catalog import EXACT, AMBIGUOUS, NONE

from tests.test_catalog_resolution import CATALOG


def _codes(res):
    return [t["code"] for t in res.tests]


# ── EXACT: match inequívoco → agrega ─────────────────────────────────────────────

def test_exact_by_code():
    res = catalog.resolve_tests("1101", CATALOG)
    assert res.status == EXACT and _codes(res) == ["1101"]


def test_exact_by_full_name():
    res = catalog.resolve_tests("Coprológico", CATALOG)
    assert res.status == EXACT and _codes(res) == ["1701"]


def test_exact_by_initial_distinctive_token():
    # "cuadro hematico" cubre el token inicial de "Cuadro Hemático Completo".
    res = catalog.resolve_tests("cuadro hematico", CATALOG)
    assert res.status == EXACT and _codes(res) == ["1101"]


def test_exact_multiple_items():
    res = catalog.resolve_tests("cuadro hematico y creatinina", CATALOG)
    assert res.status == EXACT and set(_codes(res)) == {"1101", "1309"}


# ── El RESIDUAL ERR-053: término genérico NO agrega, ofrece ──────────────────────

def test_generic_area_word_does_not_resolve_to_a_test():
    # "sanguíneos" es una palabra de área vaga: NO resuelve a un test concreto (jamás debe
    # agregar 'Gases sanguíneos Plus' $90k por un adjetivo). Se pregunta o se ofrece por área.
    assert catalog.resolve_tests("sanguíneos", CATALOG).status == NONE
    assert catalog.resolve_tests("análisis de sangre", CATALOG).status == NONE


def test_lone_digit_resolves_to_nothing():
    res = catalog.resolve_tests("3", CATALOG)
    assert res.status == NONE
    assert res.tests == []


def test_action_words_resolve_to_nothing():
    res = catalog.resolve_tests("quiero agregar otro análisis", CATALOG)
    assert res.status == NONE


# ── Área: por categoría/muestra → ofrece las opciones del área ───────────────────

def test_area_by_category_offers_options():
    res = catalog.resolve_tests("algo de química", CATALOG)
    assert res.status == AMBIGUOUS
    assert set(_codes(res)) >= {"1309"}   # Creatinina es de Química


def test_structural_words_never_match_an_area():
    """ERR-063 (prueba real 2026-07-16): el 'con' de 'vamos CON el 152...' matcheaba la
    muestra 'Tubo Tapa Azul CON 3/4 de sangre' y ofrecía el menú de Coagulación. Una
    palabra estructural (preposición, verbo de pedido) jamás identifica un área."""
    coag = [
        {"code": "1201", "name": "PT (Tiempo de Protrombina)", "price": 18000,
         "category": "Coagulación", "sample": "Tubo Tapa Azul con 3/4 de sangre"},
        {"code": "1202", "name": "PTT (Tiempo parcial de Tromboplastina)", "price": 18000,
         "category": "Coagulación", "sample": "Tubo Tapa Azul con 3/4 de sangre"},
    ]
    res = catalog.resolve_tests("necesito una prueba con urgencia", CATALOG + coag)
    assert res.status == NONE                       # 'con'/'urgencia' no eligen Coagulación
    # Y el pedido compuesto real resuelve EXACT a lo nombrado, sin ruido del área:
    res2 = catalog.resolve_tests("vamos con el 152 y le quiero agregar potasio y sodio si?",
                                 CATALOG + coag + [
        {"code": "1404", "name": "Potasio", "price": 12000, "category": "Química"},
        {"code": "1405", "name": "Sodio", "price": 12000, "category": "Química"},
    ])
    assert res2.status == EXACT and set(_codes(res2)) == {"1404", "1405"}


def test_generic_spanish_word_alone_never_names_a_test():
    """ERR-064 (auditoría de trampas léxicas): 'cálculo' suelto auto-agregaba 'Estudio de
    Cálculo' ($83k); 'básico', 'panel', 'cuadro', 'lectura' igual. Un descriptor genérico
    del español SOLO no nombra un test — el nombre completo con su palabra distintiva sí."""
    trampas = [
        {"code": "1603", "name": "Estudio de Cálculo", "price": 83000, "category": "Uroanálisis"},
        {"code": "1910", "name": "Espermograma Básico", "price": 44000, "category": "Reproducción"},
        {"code": "1204", "name": "Panel Test de Coagulación (PT, PTT, APTT, Fibrinógeno)",
         "price": 74000, "category": "Coagulación"},
        {"code": "1602", "name": "Lectura Sedimento Urinario", "price": 7000, "category": "Uroanálisis"},
    ]
    rows = CATALOG + trampas
    # Palabras genéricas sueltas (o en frases de plata) → jamás EXACT:
    for frase in ("calculo", "hazme el calculo del total", "algo basico",
                  "panel", "te paso el cuadro", "lectura"):
        assert catalog.resolve_tests(frase, rows).status != EXACT, frase
        for t in trampas:
            assert not catalog.names_test(frase, t), (frase, t["name"])
    # El nombre real (con su palabra distintiva) sigue funcionando:
    assert catalog.resolve_tests("espermograma basico", rows).status == EXACT
    assert catalog.resolve_tests("panel de coagulacion", rows).status == EXACT
    assert catalog.resolve_tests("lectura de sedimento", rows).status == EXACT
    assert catalog.resolve_tests("cuadro hematico", rows).status == EXACT


# ── Invariante de plata: los tests devueltos traen el precio del catálogo ─────────

def test_resolved_tests_have_catalog_price():
    res = catalog.resolve_tests("Coprológico, Creatinina", CATALOG)
    assert res.status == EXACT
    assert {t["code"]: t["price"] for t in res.tests} == {"1701": 12000, "1309": 12000}


def test_area_label_is_most_common_category():
    """ERR-066b (chat real): 'orina' mostraba 'Para HORMONAS...' porque la etiqueta salía
    del primer hit (Cortisol en Orina, categoría Hormonas). La etiqueta es la categoría
    más común entre los hits del área."""
    rows = [
        {"code": "1507", "name": "Cortisol en Orina", "price": 33000,
         "category": "Hormonas", "sample": "Orina"},
        {"code": "1601", "name": "Parcial de Orina (14 parámetros)", "price": 16000,
         "category": "Uroanálisis", "sample": "Orina Fresca"},
        {"code": "1602", "name": "Lectura Sedimento Urinario", "price": 7000,
         "category": "Uroanálisis", "sample": "Orina Fresca"},
    ]
    res = catalog.resolve_tests("si orina tambien", rows)
    assert res.status == AMBIGUOUS
    assert res.area == "Uroanálisis"          # la más común, no la del primer hit


# ── Auditoría de cobertura 2026-08-25 (catálogo completo re-verificado) ───────────

def test_request_filler_words_do_not_hide_a_full_name():
    """'ME HACES un Estudio de Cálculo porfa' perdía el 1603: 'me'/'haces' no eran
    muletillas conocidas y el atajo de nombre completo no aplicaba. El nombre entero
    del test, rodeado solo de palabras de pedido, SIEMPRE resuelve."""
    rows = CATALOG + [
        {"code": "1603", "name": "Estudio de Cálculo", "price": 83000, "category": "Uroanálisis"},
    ]
    res = catalog.resolve_tests("me haces un estudio de calculo porfa", rows)
    assert res.status == EXACT and _codes(res) == ["1603"]
    # La protección ERR-064 sigue intacta: el genérico suelto jamás agrega.
    assert catalog.resolve_tests("me haces el calculo", rows).status != EXACT


def test_convenio_test_appears_when_named_by_group_word():
    """El 1903 (Citología PAF, Convenio SERVIPAT) vive fuera de la categoría 'Citología':
    pedir 'citología' a secas debe OFRECERLO junto a las citologías comunes — es el
    'está en la siguiente página' del cliente (llamada 9, 21/08)."""
    rows = CATALOG + [
        {"code": "1901", "name": "Citología Vaginal", "price": 15000, "category": "Citología"},
        {"code": "1909", "name": "Citología Piel", "price": 15000, "category": "Citología"},
        {"code": "1903", "name": "Citología PAF", "price": 52000, "category": "Convenio SERVIPAT"},
    ]
    res = catalog.resolve_tests("citología", rows)
    assert res.status == AMBIGUOUS
    assert "1903" in _codes(res)
    # Y con el nombre completo resuelve directo:
    exacto = catalog.resolve_tests("citologia paf", rows)
    assert exacto.status == EXACT and _codes(exacto) == ["1903"]


# ── Cómo pide el veterinario: siglas y jerga (auditoría 2026-08-25) ──────────────

BUN = {"code": "1321", "name": "Nitrógeno Ureico (BUN)", "price": 12000, "category": "Química"}
CK_MB = {"code": "1310", "name": "Creatina Quinasa Fracción MB (CK)", "price": 16000,
         "category": "Química"}
CK_NAC = {"code": "1311", "name": "Creatina Quinasa NAC (CK)", "price": 14000,
          "category": "Química"}


def test_la_sigla_del_nombre_nombra_el_analisis():
    """'BUN' cubría 1 de 3 palabras de 'Nitrógeno Ureico (BUN)' y no llegaba al umbral de
    cobertura: el análisis era irresoluble por el nombre con que lo pide todo el mundo."""
    res = catalog.resolve_tests("un BUN", CATALOG + [BUN])
    assert res.status == EXACT and _codes(res) == ["1321"]


def test_sigla_compartida_ofrece_en_vez_de_elegir():
    """'CK' son dos pruebas distintas con precios distintos: se ofrecen, no se adivina."""
    res = catalog.resolve_tests("CK", CATALOG + [CK_MB, CK_NAC])
    assert res.status == AMBIGUOUS and set(_codes(res)) == {"1310", "1311"}


def test_jerga_del_gremio_encuentra_el_nombre_del_catalogo():
    """'hemograma' es el sinónimo más usado de Cuadro Hemático y no figura en el portafolio."""
    res = catalog.resolve_tests("necesito un hemograma", CATALOG)
    assert res.status == EXACT and _codes(res) == ["1101"]


def test_la_jerga_sustituye_y_no_duplica_el_pedido():
    """Sumar el término traducido (en vez de sustituirlo) hacía que 'leishmaniasis' se
    leyera como DOS análisis en una frase — $189.000 en vez de $70.000."""
    rows = CATALOG + [
        {"code": "2014", "name": "Leishmania (Anticuerpo)", "price": 70000, "category": "Inmunología"},
        {"code": "2304", "name": "Leishmaniasis canina Anticuerpos IgG (IFA)", "price": 119000,
         "category": "Convenio LMV"},
    ]
    # 'leishmaniasis' ES el nombre del 2304, así que la jerga no sustituye; pero el 2304 es
    # de convenio y el 2014 tiene la misma raíz, así que se ofrecen los dos en vez de cobrar
    # el caro en silencio. Lo que nunca puede pasar es que se agreguen AMBOS.
    res = catalog.resolve_tests("leishmaniasis", rows)
    assert res.status == AMBIGUOUS and set(_codes(res)) == {"2014", "2304"}
    # Con la palabra que NO está en el catálogo, la jerga sí traduce y resuelve a lo propio:
    solo_convenio = catalog.resolve_tests("lehismania", rows)
    assert solo_convenio.status == EXACT and _codes(solo_convenio) == ["2014"]


def test_un_nombre_real_del_catalogo_manda_sobre_la_jerga():
    """Si A3 carga un análisis llamado 'Hemograma', esa palabra es un nombre, no jerga."""
    hemograma = {"code": "0301", "name": "Hemograma", "price": 25000, "category": "Hematología"}
    res = catalog.resolve_tests("quiero un hemograma", CATALOG + [hemograma])
    assert res.status == EXACT and _codes(res) == ["0301"]


def test_palabra_de_muestra_no_agrega_un_test_suelto():
    """'materia fecal' es la MUESTRA: resolvía EXACT a 'Tripsina en Materia Fecal'
    ($13.000) sin que el cliente nombrara ninguna prueba."""
    rows = CATALOG + [
        {"code": "1703", "name": "Tripsina en Materia Fecal", "price": 13000,
         "category": "Parasitología", "sample": "Materia Fecal"},
    ]
    assert catalog.resolve_tests("materia fecal", rows).status != EXACT
    assert catalog.resolve_tests("una muestra de heces", rows).status != EXACT
    # El nombre real sigue resolviendo:
    assert catalog.resolve_tests("tripsina", rows).status == EXACT


def test_el_convenio_no_gana_en_silencio_sobre_la_prueba_propia():
    """El convenio cuesta 2-3x lo propio. Cuando el término nombra a los dos, se ofrecen:
    el precio lo decide el cliente, nunca el orden de las palabras del nombre."""
    rows = CATALOG + [
        # El nombre del PDF trae el sinónimo: "Distemper Canino O MOQUILLO CANINO".
        {"code": "2004", "name": "Distemper Canino o Moquillo Canino (Antígeno)",
         "price": 45000, "category": "Inmunología"},
        {"code": "2306", "name": "Moquillo Canino (Distemper) Anticuerpos IgM (IFA)",
         "price": 124000, "category": "Convenio LMV"},
    ]
    res = catalog.resolve_tests("moquillo", rows)
    assert res.status == AMBIGUOUS
    assert set(_codes(res)) >= {"2004", "2306"}
