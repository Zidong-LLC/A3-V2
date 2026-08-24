"""
ERR-140 — Un código que no existe en el catálogo moría en SILENCIO.

Test en vivo (2026-08-21): el cliente pidió el 1903 tres veces ("952 y 1903",
"Agrega 1903", "cámbialo por el 1903") y el bot jamás dijo "ese código no lo tengo" —
lo descartó calladamente cada vez, dejando al cliente dando vueltas. (El 1903 además
SÍ existía en el PDF del catálogo: sección Convenio SERVIPAT nunca cargada — las dos
mitades del bug se arreglan por separado.)
"""
import pytest

from app import orders
from app.enforcers import confirmacion


PERFIL_952 = {"code": "952", "name": "Perfil Toxicológico Órgano Fosforados", "price": 90000}
TEST_1101 = {"code": "1101", "name": "Cuadro Hemático Completo", "price": 14000}


@pytest.fixture(autouse=True)
def catalogo(monkeypatch):
    def _profiles_by_codes(codes, species=None):
        return [PERFIL_952 for c in codes if c == "952"]

    def _tests_by_codes_or_names(terms):
        return [TEST_1101 for t in terms if "1101" in str(t)]

    monkeypatch.setattr(orders.db, "get_catalog_profiles_by_codes", _profiles_by_codes)
    monkeypatch.setattr(orders.db, "get_tests_by_codes_or_names", _tests_by_codes_or_names)


def test_codigo_inexistente_se_detecta():
    assert orders._unknown_catalog_codes({}, "quiero el 9999") == ["9999"]


def test_codigo_de_perfil_y_de_test_son_conocidos():
    assert orders._unknown_catalog_codes({}, "el 952 y el 1101") == []


def test_caso_mixto_conocido_mas_desconocido():
    """'El análisis es 952 y 9999': el válido se registra, el inválido se AVISA."""
    assert orders._unknown_catalog_codes({}, "el 952 y el 9999") == ["9999"]


def test_sin_codigos_no_hay_nada_que_avisar():
    assert orders._unknown_catalog_codes({}, "sí, dale, gracias") == []


def test_fallo_de_infra_nunca_rompe_el_turno(monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("supabase caída")

    monkeypatch.setattr(orders.db, "get_catalog_profiles_by_codes", _boom)
    assert orders._unknown_catalog_codes({}, "el 9999") == []


def test_en_confirmacion_el_codigo_desconocido_se_avisa(monkeypatch):
    """El carril de ajuste en confirmación responde 'no está en el catálogo' en vez de
    la repregunta ciega '¿Qué análisis quieres agregar?'."""
    monkeypatch.setattr(confirmacion.db, "get_tests_by_codes_or_names", lambda terms: [])
    monkeypatch.setattr(confirmacion.db, "get_catalog_profiles_by_codes", lambda c, s=None: [])
    monkeypatch.setattr(confirmacion.db, "find_catalog_profile", lambda *a, **k: None)
    monkeypatch.setattr(confirmacion, "_area_options_for_profile_addition",
                        lambda *a, **k: None)

    fields = {"_awaiting_additional_test": "add", "species": "Canino"}
    response = confirmacion._confirmation_analysis_adjustment({}, fields, "9999", None)

    assert response is not None
    assert "9999" in response["reply"]
    assert "no está en el catálogo" in response["reply"]
    assert fields["_awaiting_additional_test"] == "add", "sigue esperando el análisis"
