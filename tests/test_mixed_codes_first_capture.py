"""
Pedido MIXTO en la primera captura: un perfil y varios análisis por código, en una frase.

Caso medido con el modelo real (QA de cobertura del catálogo): "perfil 956, 2016 y 1901"
—956 es perfil, 2016 y 1901 son análisis— perdía LOS TRES códigos y el bot respondía con una
lista de sugerencias de la etiqueta FELINOS.

Eran dos borrados en cadena:
  1. `_enforce_catalog_profile_code_selection` resolvía el perfil y hacía
     `selected_tests = None`, matando los análisis del mismo turno.
  2. `_enforce_diagnostic_label_help` no miraba `_selected_profile_code`, así que después
     borraba también el perfil (el nombre "Perfil Toxicológico Felinos" contiene "felinos",
     y las etiquetas diagnósticas se recorren alfabéticamente).

Es un error de dinero, de la familia de ERR-077 (eligió "1, 3 y 6" y quedó solo el 1) y
ERR-103 (el perfil por código que se perdía en la ventana de oferta).
"""
from unittest.mock import MagicMock

import pytest

from app.enforcers import orden


PERFIL_956 = {"code": "956", "name": "Perfil Toxicológico Felinos", "category": "toxicologico",
              "species": "felino", "price": 58000, "description": ""}
PERFIL_754 = {"code": "754", "name": "Perfil Dermatológico IV", "category": "dermatologico",
              "species": "ambos", "price": 25000, "description": ""}
TEST_2016 = {"code": "2016", "name": "Preñez (Relaxina) Canina", "price": 40000, "category": "x"}
TEST_1901 = {"code": "1901", "name": "Citología Vaginal", "price": 20000, "category": "x"}

PERFILES = {"956": PERFIL_956, "754": PERFIL_754}
TESTS = {"2016": TEST_2016, "1901": TEST_1901}

SESSION = {"client_id": "cli-1"}


@pytest.fixture(autouse=True)
def catalogo(monkeypatch):
    """Mock de infraestructura: solo las consultas a Supabase."""
    monkeypatch.setattr(orden.db, "get_catalog_profiles_by_codes",
                        lambda codes, species=None: [PERFILES[c] for c in codes if c in PERFILES])
    monkeypatch.setattr(orden.db, "get_tests_by_codes",
                        lambda codes: [TESTS[c] for c in codes if c in TESTS])
    monkeypatch.setattr(orden.db, "get_tests_by_codes_or_names",
                        lambda items: [TESTS[c] for c in items if c in TESTS])


def _respuesta(mensaje: str) -> dict:
    fields = {"_client_found": True, "species": "Felino", "patient_name": "Marla"}
    ai = {"intent": "route_scheduling", "captured_fields": fields,
          "phase": "fase_2_recogida_datos", "reply": "(del modelo)"}
    return orden._enforce_catalog_profile_code_selection(SESSION, ai, mensaje)


def test_perfil_y_dos_analisis_en_una_frase_no_pierde_nada():
    """EL caso: los tres códigos tienen que quedar en la orden."""
    out = _respuesta("perfil 956, 2016 y 1901")
    fields = out["captured_fields"]
    assert fields.get("_selected_profile_code") == "956"
    sueltos = [str(t) for t in (fields.get("selected_tests") or [])]
    assert any("2016" in s for s in sueltos), f"se perdió el 2016: {sueltos}"
    assert any("1901" in s for s in sueltos), f"se perdió el 1901: {sueltos}"


def test_el_acuse_nombra_el_perfil_y_los_analisis():
    """El cliente tiene que ver que quedaron los tres, no enterarse en el resumen."""
    reply = _respuesta("perfil 956, 2016 y 1901")["reply"]
    assert "956" in reply and "2016" in reply and "1901" in reply


def test_dos_perfiles_en_una_frase_se_enganchan_los_dos():
    """Antes se rendía con 2+ perfiles (`if len(profiles) != 1: return`)."""
    fields = _respuesta("quiero el perfil 956 y el perfil 754")["captured_fields"]
    codigos = {fields.get("_selected_profile_code")} | {
        str(p.get("code")) for p in (fields.get("_extra_profiles") or [])}
    assert codigos == {"956", "754"}


def test_un_perfil_solo_sigue_por_el_camino_de_siempre():
    """No-regresión: el caso simple no cambia de carril."""
    fields = _respuesta("perfil 956")["captured_fields"]
    assert fields.get("_selected_profile_code") == "956"


def test_la_etiqueta_diagnostica_cede_si_ya_hay_perfil_resuelto():
    """El segundo borrado: sin este guard, la ayuda por etiqueta pisaba el perfil."""
    fields = {"_client_found": True, "species": "Felino", "_selected_profile_code": "956",
              "exam_type": "Perfil Toxicológico Felinos"}
    ai = {"intent": "route_scheduling", "captured_fields": fields,
          "phase": "fase_2_recogida_datos", "reply": "(del modelo)"}
    out = orden._enforce_diagnostic_label_help(SESSION, ai, {}, "perfil 956", [])
    assert out["captured_fields"].get("_selected_profile_code") == "956"
    assert out["captured_fields"].get("exam_type") == "Perfil Toxicológico Felinos"
