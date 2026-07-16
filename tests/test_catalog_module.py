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


# ── Invariante de plata: los tests devueltos traen el precio del catálogo ─────────

def test_resolved_tests_have_catalog_price():
    res = catalog.resolve_tests("Coprológico, Creatinina", CATALOG)
    assert res.status == EXACT
    assert {t["code"]: t["price"] for t in res.tests} == {"1701": 12000, "1309": 12000}
