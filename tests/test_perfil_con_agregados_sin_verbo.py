"""'perfl 152 y agreagar sodio y potasio.' — los agregados no se pierden (ERR-187).

Estrés multi-orden del 28/10 (persona apurado_typos), reproducido sin modelo: si el modelo
ya anotaba sodio y potasio en `selected_tests`, `_enforce_catalog_profile_code_selection`
los borraba al fijar el perfil por código y nadie volvía a leer el mensaje. La orden salía
por $24.000 en vez de $48.000; intermitente porque dependía de qué anotara el modelo.
"""
import pytest

from app import orders
from app.enforcers import orden

PERFIL_152 = {"code": "152", "name": "Perfil Prequirúrgico I", "category": "prequirurgico",
              "species": "ambos", "price": 24000, "description": "Cuadro Hemático, ALT, Creatinina"}
CATALOGO = [{"code": "1405", "name": "Sodio", "price": 12000, "category": "Química", "species": "ambos"},
            {"code": "1404", "name": "Potasio", "price": 12000, "category": "Química", "species": "ambos"},
            {"code": "1101", "name": "Cuadro Hemático Completo", "price": 14000, "category": "Hematología",
             "species": "ambos"}]


@pytest.fixture(autouse=True)
def catalogo(monkeypatch):
    for modulo in (orden.db, orders.db):
        monkeypatch.setattr(modulo, "get_catalog_profiles_by_codes",
                            lambda codes, species=None: [PERFIL_152] if "152" in codes else [])
        monkeypatch.setattr(modulo, "list_catalog_tests", lambda limit=5000: list(CATALOGO))
        monkeypatch.setattr(modulo, "list_catalog_profiles_matching_category", lambda t, s=None, limit=11: [])
        monkeypatch.setattr(modulo, "get_tests_by_codes_or_names",
                            lambda items: [t for t in CATALOGO if t["code"] in items or t["name"] in items])


@pytest.mark.parametrize("anotado_por_el_modelo", [None, ["1405", "1404"]])
def test_perfil_por_codigo_con_analisis_nombrados_sin_verbo(anotado_por_el_modelo):
    fields = {"_client_found": True, "species": "Canino", "patient_name": "Rocky",
              "exam_type": "Perfil 152", "selected_tests": anotado_por_el_modelo}
    ai = {"intent": "route_scheduling", "captured_fields": fields, "phase": "fase_2_recogida_datos",
          "reply": "(del modelo)"}
    out = orden._enforce_catalog_profile_code_selection(
        {"client_id": "c1"}, ai, "perfl 152 y agreagar sodio y potasio.")
    campos = out["captured_fields"]
    assert campos["_selected_profile_code"] == "152"
    assert sorted(campos["selected_tests"]) == ["1404", "1405"]
    assert "Sodio" in out["reply"] and "Potasio" in out["reply"]
