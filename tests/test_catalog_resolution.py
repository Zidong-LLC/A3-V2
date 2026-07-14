"""
Fase 0 — Red de seguridad del EJE CATÁLOGO (plan: atacar la causa raíz).

Ejercita la LÓGICA REAL de resolución texto→código de `app/services/db.py`
(no mocks perfectos: inyecta un catálogo controlado en `db._client` y deja
correr el matching de verdad). Congela el comportamiento bueno actual y deja
VISIBLE el residual conocido (ERR-053: un término genérico agrega un test caro
que el cliente no pidió). Los casos marcados `xfail` deben volverse verdes en la
Fase 1 con el resolvedor unívoco `app/catalog.resolve_tests`.

Invariante del eje: agregar a la orden SOLO con match inequívoco (código exacto,
nombre canónico completo o selección de menú). Un término genérico/de área NUNCA
resuelve por su cuenta a un test suelto.
"""
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.services import db


# ── Catálogo de prueba (precios reales de referencia) ───────────────────────────
CATALOG = [
    {"code": "1101", "name": "Cuadro Hemático Completo", "price": 14000,
     "category": "Hematología", "sample": "Sangre", "is_active": True, "species": "ambos"},
    {"code": "1309", "name": "Creatinina", "price": 12000,
     "category": "Química", "sample": "Suero", "is_active": True, "species": "ambos"},
    {"code": "1701", "name": "Coprológico", "price": 12000,
     "category": "Parasitología", "sample": "Materia Fecal", "is_active": True, "species": "ambos"},
    {"code": "1408", "name": "Gases sanguíneos Plus", "price": 90000,
     "category": "Gases", "sample": "Sangre", "is_active": True, "species": "ambos"},
    {"code": "1501", "name": "T3 Total", "price": 36000,
     "category": "Endocrinología", "sample": "Suero", "is_active": True, "species": "ambos"},
    {"code": "1201", "name": "PT (Tiempo de Protrombina)", "price": 18000,
     "category": "Coagulación", "sample": "Plasma", "is_active": True, "species": "ambos"},
]


class _FakeTable:
    """Soporta el chaining del SDK de Supabase y APLICA los filtros eq/in_ sobre las
    rows (fiel a la query real): sin esto, `get_tests_by_codes` con .in_("code", [...])
    devolvería el catálogo entero y los totales saldrían inflados."""
    def __init__(self, rows):
        self._rows = list(rows)

    def select(self, *a, **k):  return self
    def limit(self, *a, **k):   return self
    def order(self, *a, **k):   return self

    def eq(self, col, val):
        self._rows = [r for r in self._rows if r.get(col) == val]
        return self

    def in_(self, col, vals):
        allowed = set(vals)
        self._rows = [r for r in self._rows if r.get(col) in allowed]
        return self

    def execute(self):          return SimpleNamespace(data=list(self._rows))


class _FakeClient:
    def __init__(self, tables):
        self._tables = tables

    def table(self, name):
        return _FakeTable(self._tables.get(name, []))


@pytest.fixture
def catalog_db():
    """Inyecta el catálogo de prueba en el cliente real de db."""
    with patch.object(db, "_client", _FakeClient({"catalog_tests": CATALOG})):
        yield


def _codes(rows):
    return [r["code"] for r in rows]


# ── Lo que HOY funciona bien: match inequívoco resuelve ─────────────────────────

def test_exact_code_resolves(catalog_db):
    assert _codes(db.get_tests_by_codes_or_names(["1101"])) == ["1101"]


def test_exact_name_resolves(catalog_db):
    assert _codes(db.get_tests_by_codes_or_names(["Coprológico"])) == ["1701"]


def test_full_canonical_name_subsequence_resolves(catalog_db):
    # "cuadro hematico" es subsecuencia de palabras completas del nombre canónico.
    assert _codes(db.get_tests_by_codes_or_names(["cuadro hematico"])) == ["1101"]


def test_lone_digit_does_not_match_by_substring(catalog_db):
    # ERR-053 ya corregido: "3" no debe caer dentro de "T3 Total" por subcadena.
    assert db.get_tests_by_codes_or_names(["3"]) == []


# ── El RESIDUAL conocido (ERR-053): término genérico agrega un test caro ─────────
# Estos documentan el listón. Deben pasar a verde en la Fase 1 cuando la
# resolución exija match inequívoco y ofrezca opciones ante términos genéricos.

@pytest.mark.xfail(reason="Deuda Fase 1.4: get_tests_by_codes_or_names (bajo nivel) sigue "
                          "siendo laxa con términos genéricos. El FLUJO ya está protegido: "
                          "el handler usa catalog.resolve_tests (ver test_extra_analysis_offer::"
                          "test_generic_area_term_offers_options_instead_of_autoadding). Este "
                          "xfail se cierra cuando se elimine la función de bajo nivel.",
                   strict=True)
def test_generic_area_term_does_not_autoadd_expensive_test(catalog_db):
    # "sanguíneos" es un adjetivo de área, no un test concreto: NO debería resolver solo.
    assert db.get_tests_by_codes_or_names(["sanguíneos"]) == []


def test_generic_blood_phrase_does_not_resolve_today(catalog_db):
    # "análisis de sangre" no es subsecuencia de ningún NOMBRE canónico y "sangre"
    # solo vive en el campo sample (que este resolvedor no mira) → hoy da []. Bien.
    assert db.get_tests_by_codes_or_names(["análisis de sangre"]) == []


# ── Invariante de plata: todo código resuelto existe y trae precio real ──────────

def test_resolved_tests_carry_catalog_price(catalog_db):
    rows = db.get_tests_by_codes_or_names(["Coprológico", "Creatinina"])
    assert _codes(rows) == ["1701", "1309"]
    assert all(isinstance(r.get("price"), int) and r["price"] > 0 for r in rows)
    # El precio proviene del catálogo, nunca del texto del usuario.
    assert {r["code"]: r["price"] for r in rows} == {"1701": 12000, "1309": 12000}
