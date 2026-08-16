"""Regresión del QA de cobertura de datos (2026-08-15): el nombre COMPLETO de una fila del
catálogo debe devolver ESA fila, siempre.

Dos agujeros encontrados recorriendo la base entera (tools/scripts/qa_cobertura_datos.py):

1. `find_catalog_profile` por nombre devolvía OTRO perfil cuando los nombres colisionan por
   subcadena tras normalizar numerales romanos: 'Perfil Prequirúrgico I' → `…_1` ⊂ `…_10`
   ('Prequirúrgico X', el de $90.000 — la clase ERR-041 que ya fabricó un fantasma en el
   estrés). Igual 'Hemoparásitos I'⊂'II', 'Felino II'⊂'III', 'General'⊂'Generales de Salud'.
   Fix: pasada de nombre EXACTO normalizado ANTES del match difuso.

2. `catalog.resolve_tests` no podía resolver 'Estudio de Cálculo' (1603) NUNCA: 'estudio' es
   token estructural y 'cálculo' descriptor genérico — el nombre entero se filtraba y quedaba
   sin contenido distintivo. Fix: si lo que el cliente escribió ES el nombre completo de una
   fila (solo con extras estructurales), esa fila gana sin pasar por el filtro.
"""
from unittest.mock import patch

from app import catalog
from app.services import db

PERFILES = [
    {"code": "161", "name": "Perfil Prequirúrgico X", "species": "ambos", "price": 90000},
    {"code": "1339", "name": "Panel Generales de Salud", "species": "ambos", "price": 120000},
    {"code": "252", "name": "Perfil Hemoparásitos II", "species": "ambos", "price": 60000},
    {"code": "303", "name": "Perfil Felino III", "species": "felino", "price": 80000},
    # Los correctos DESPUÉS de sus colisionadores: el difuso encontraba primero al equivocado.
    {"code": "152", "name": "Perfil Prequirúrgico I", "species": "ambos", "price": 24000},
    {"code": "151", "name": "Perfil General", "species": "ambos", "price": 32000},
    {"code": "251", "name": "Perfil Hemoparásitos I", "species": "ambos", "price": 45000},
    {"code": "302", "name": "Perfil Felino II", "species": "felino", "price": 65000},
]


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def select(self, *_a, **_k):
        return self

    def eq(self, *_a, **_k):
        return self

    def limit(self, *_a, **_k):
        return self

    def execute(self):
        return type("R", (), {"data": self._rows})()


class _FakeClient:
    def table(self, *_a, **_k):
        return _FakeQuery(PERFILES)


def _find(nombre):
    with patch.object(db, "_client", _FakeClient()):
        return db.find_catalog_profile(nombre)


def test_perfil_por_nombre_exacto_gana_sobre_la_colision_romana():
    """El caso del dinero: 'Prequirúrgico I' NO puede devolver el X de $90.000."""
    assert _find("Perfil Prequirúrgico I")["code"] == "152"


def test_los_cuatro_nombres_que_colisionaban_devuelven_su_propio_perfil():
    esperados = {
        "Perfil General": "151",
        "Perfil Hemoparásitos I": "251",
        "Perfil Felino II": "302",
        "perfil felino ii": "302",  # el cliente escribe en minúsculas
        "perfil hemoparasitos i": "251",  # y sin tildes
    }
    for nombre, code in esperados.items():
        got = _find(nombre)
        assert got and got["code"] == code, f"{nombre!r} devolvió {got}"


def test_el_difuso_sigue_vivo_cuando_no_hay_nombre_exacto():
    """La pasada exacta es un carril previo, no un reemplazo: un nombre parcial que antes
    resolvía debe seguir resolviendo por el camino difuso."""
    got = _find("prequirurgico x")
    assert got and got["code"] == "161"


TESTS_CATALOGO = [
    {"code": "1603", "name": "Estudio de Cálculo", "category": "Uroanálisis", "price": 50000},
    {"code": "0101", "name": "Cuadro Hemático", "category": "Hematología", "price": 20000},
    {"code": "0201", "name": "Glucosa", "category": "Química", "price": 18000},
]


def test_estudio_de_calculo_resuelve_por_su_nombre_completo():
    """Nombre hecho SOLO de palabras filtradas: antes era irresoluble por nombre."""
    for texto in ("Estudio de Cálculo", "estudio de calculo", "necesito el estudio de calculo"):
        res = catalog.resolve_tests(texto, TESTS_CATALOGO, None)
        codes = [str(t["code"]) for t in (res.tests or [])]
        assert codes == ["1603"], f"{texto!r} → status={res.status}, {codes}"


def test_el_filtro_de_genericos_sigue_frenando_lo_vago():
    """El carril exacto no puede reabrir ERR-111: 'una prueba de orina' NO nombra un test."""
    res = catalog.resolve_tests("necesito una prueba de orina", TESTS_CATALOGO, None)
    assert not res.tests
