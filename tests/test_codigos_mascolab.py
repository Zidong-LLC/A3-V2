"""Códigos con guion de Mascolab (ERR-197). Decisión del usuario, 2026-11-09: son análisis
distintos con precio propio y se quedan así: «2457» es Punto Final y «2457-1», Tiempo Real.
Antes, escribir «2457-1» cargaba el 2457, con el precio equivocado."""
import pytest

from app import catalog, imports
from app import imports_archivo as archivo
from app.detectors import _profile_codes_from_text
from app.imports_contenido import separar_codigo

CATALOGO = [
    {"code": "2457", "name": "Chlamydophila psittaci (Punto Final)", "price": 157000, "species": "canino", "category": "Mascolab - Punto Final"},
    {"code": "2457-1", "name": "Chlamydophila psittaci (Tiempo Real)", "price": 224000, "species": "canino", "category": "Mascolab - Tiempo Real"},
    {"code": "2461", "name": "Chlamydophila psittaci (Punto Final)", "price": 157000, "species": "ambos", "category": "Mascolab - Punto Final"},
    {"code": "2461-1", "name": "Chlamydophila psittaci (Tiempo Real)", "price": 224000, "species": "ambos", "category": "Mascolab - Tiempo Real"},
    {"code": "2459", "name": "Dirofilaria repens (Punto Final)", "price": 168000, "species": "canino", "category": "Mascolab - Punto Final"},
    {"code": "2459-1", "name": "Dirofilaria repens (Tiempo Real)", "price": 238000, "species": "canino", "category": "Mascolab - Tiempo Real"},
    {"code": "1701", "name": "Coprológico", "price": 12000, "species": "ambos", "category": "Parasitología"},
]


def _codigos(texto):
    r = catalog.resolve_tests(texto, CATALOGO, "Canino")
    return r.status, sorted(t["code"] for t in r.tests)


@pytest.mark.parametrize("texto,codigo,precio", [("2457-1", "2457-1", 224000), ("el 2459-1", "2459-1", 238000),
                                                 ("2457", "2457", 157000), ("2459", "2459", 168000)])
def test_cada_codigo_trae_su_analisis_y_su_precio(texto, codigo, precio):
    r = catalog.resolve_tests(texto, CATALOGO, "Canino")
    assert r.status == catalog.EXACT and [(t["code"], t["price"]) for t in r.tests] == [(codigo, precio)]


def test_varios_codigos_juntos_no_se_pisan():
    assert _codigos("2457-1 y 1701") == (catalog.EXACT, ["1701", "2457-1"])
    assert _codigos("2457, 2457-1") == (catalog.EXACT, ["2457", "2457-1"])


def test_por_nombre_sin_tecnica_se_ofrecen_las_dos_con_su_precio():
    status, codigos = _codigos("chlamydophila psittaci")
    assert status == catalog.AMBIGUOUS and {"2457", "2457-1"} <= set(codigos)


def test_nombrando_la_tecnica_se_elige_esa():
    assert _codigos("dirofilaria repens tiempo real") == (catalog.EXACT, ["2459-1"])


@pytest.mark.parametrize("texto,esperado", [
    ("2457-1", ["2457-1"]), ("1101-1102", ["1101", "1102"]), ("1701-Coprológico", ["1701"]),
    ("el 2459-1 y 1701", ["2459-1", "1701"]), ("900123456-1", []),
])
def test_codigos_en_el_texto(texto, esperado):
    assert _profile_codes_from_text(texto) == esperado


def test_la_carga_de_precios_no_confunde_un_codigo_con_guion():
    assert separar_codigo("2457-1 Chlamydophila Tiempo Real") == ("2457-1", "Chlamydophila Tiempo Real")
    assert separar_codigo("2457 - Chlamydophila") == ("2457", "Chlamydophila")
    enc, filas = archivo.leer_tabla(b"2457;157000\n2457-1;224000\n1701;12000\n", "lista.csv")
    assert enc == ["codigo", "precio"] and ["2457-1", "224000"] in filas
    plan = imports.plan_precios(archivo.filas_con_mapa(filas, archivo.mapa_automatico(enc, "precios")), CATALOGO, [])
    assert plan["errores"] == [] and plan["iguales"] == 3, "cada precio se compara con su propio código"
