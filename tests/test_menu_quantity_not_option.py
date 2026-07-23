"""
Regresión ERR-079 (hallazgo al revisar ERR-077 con el usuario, 2026-07-21): si el cliente
pide CANTIDADES sobre un menú ("5 del 1 y 6 del 3"), los números de cantidad se leían como
números de opción y la orden terminaba con análisis que nadie pidió — y cobrados.

Con un menú de 6 opciones:
    "5 del 1 y 6 del 3"  ->  opciones 5, 1, 6, 3   (2 análisis intrusos)
    "quiero 3 del 2"     ->  opciones 3, 2         (el 3 era la cantidad)

Decisión del usuario (2026-07-21): manejar la cantidad por análisis (registrar N veces uno)
es lógica compleja que por ahora NO se hace. Se ignora el cuantificador y se absorben solo
las opciones ("5 del 1 y 6 del 3" -> opciones 1 y 3). Lo único innegociable es no cobrar
análisis que el cliente no pidió, y no confundir una selección con una cantidad.
"""
from app.menus import _select_tests_from_menu

MENU = [{"code": f"16{i:02d}", "name": f"Análisis {i}", "price": 10000} for i in range(1, 7)]


def test_cantidad_en_digitos_no_se_lee_como_opcion():
    picks = _select_tests_from_menu("5 del 1 y 6 del 3", MENU)
    assert [p["code"] for p in picks] == ["1601", "1603"]


def test_cantidad_suelta_no_agrega_analisis_intruso():
    picks = _select_tests_from_menu("quiero 3 del 2", MENU)
    assert [p["code"] for p in picks] == ["1602"]


def test_cantidad_en_letras_sigue_funcionando():
    picks = _select_tests_from_menu("cinco del primero, seis del tercero", MENU)
    assert [p["code"] for p in picks] == ["1601", "1603"]


def test_seleccion_multiple_normal_no_se_rompe():
    """Control: sin cantidades, la selección múltiple sigue igual (ERR-077)."""
    assert [p["code"] for p in _select_tests_from_menu("1, 2 y 4", MENU)] == ["1601", "1602", "1604"]
    assert [p["code"] for p in _select_tests_from_menu("el 1 y el 3", MENU)] == ["1601", "1603"]


def test_codigos_de_catalogo_no_se_rompen():
    assert [p["code"] for p in _select_tests_from_menu("1602 y 1604", MENU)] == ["1602", "1604"]


def test_ordinales_no_se_confunden_con_cantidad():
    """Preocupación del usuario (2026-07-21): 'el primero, el segundo, el tercero' es una
    SELECCIÓN, no una cantidad. La red solo dispara con el conector ('5 del 1'), así que
    los ordinales se absorben como opciones normales."""
    picks = _select_tests_from_menu("el primero, el segundo y el tercero", MENU)
    assert [p["code"] for p in picks] == ["1601", "1602", "1603"]
