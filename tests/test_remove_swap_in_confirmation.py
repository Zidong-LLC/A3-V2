"""
ERR-141 — Quitar/cambiar un análisis por CÓDIGO caía en bucle.

Test en vivo (2026-08-21, orden de Joy con base 653 + adicional 952):

    CLIENTE: Saca el análisis 653 y cámbialo por el 1903
    BOT:     Claro. ¿Qué análisis quieres quitar?          ← ignoró el código de la frase
    CLIENTE: El 653
    BOT:     Claro. ¿Qué análisis quieres quitar?          ← bucle
    CLIENTE: 653
    BOT:     Ese ya está en la orden: 653 …                ← lo leyó como AGREGAR

El carril de remoción solo resolvía TESTS por nombre: un PERFIL a quitar (653) no
resolvía nunca, y la operación doble (sacar X + poner Y) se perdía entera.
"""
import pytest

from app import orders
from app.enforcers import confirmacion


PERFIL_653 = {"code": "653", "name": "Perfil Senior Canino III", "price": 58000}
PERFIL_952 = {"code": "952", "name": "Perfil Toxicológico Órgano Fosforados", "price": 90000}
TEST_1903 = {"code": "1903", "name": "Citología PAF", "price": 52000}


def _orden_de_joy() -> dict:
    return {
        "species": "Canino",
        "exam_type": "Perfil Senior Canino III",
        "_selected_profile_code": "653",
        "_selected_profile_name": "Perfil Senior Canino III",
        "_selected_profile_price": 58000,
        "_extra_profiles": [dict(PERFIL_952)],
    }


@pytest.fixture(autouse=True)
def catalogo(monkeypatch):
    def _profiles_by_codes(codes, species=None):
        return [{"653": PERFIL_653, "952": PERFIL_952}[c] for c in codes
                if c in ("653", "952")]

    def _tests_by_codes_or_names(terms):
        return [TEST_1903 for t in terms if str(t).strip() == "1903"]

    for mod in (orders, confirmacion):
        monkeypatch.setattr(mod.db, "get_catalog_profiles_by_codes", _profiles_by_codes)
        monkeypatch.setattr(mod.db, "get_tests_by_codes_or_names", _tests_by_codes_or_names)
    monkeypatch.setattr(confirmacion.db, "find_catalog_profile", lambda *a, **k: None)
    monkeypatch.setattr(confirmacion, "_area_options_for_profile_addition",
                        lambda *a, **k: None)


def test_saca_x_y_cambialo_por_y_en_un_turno():
    """La frase real completa: quita el 653, promueve el 952 a base y agrega el 1903."""
    fields = _orden_de_joy()
    response = confirmacion._confirmation_analysis_adjustment(
        {}, fields, "Saca el análisis 653 y cámbialo por el 1903", None)

    assert response is not None
    assert "quito 653" in response["reply"].lower()
    assert "1903" in response["reply"]
    assert fields["_selected_profile_code"] == "952", "el adicional pasa a ser la base"
    assert not fields.get("_extra_profiles")
    assert "1903" in (fields.get("selected_tests") or [])


def test_codigo_pelado_responde_a_que_quieres_quitar():
    """'653' tras '¿Qué análisis quieres quitar?' QUITA — nunca 'ese ya está en la orden'."""
    fields = _orden_de_joy()
    fields["_awaiting_additional_test"] = "remove"
    response = confirmacion._confirmation_analysis_adjustment({}, fields, "653", None)

    assert response is not None
    assert "quito 653" in response["reply"].lower()
    assert fields["_selected_profile_code"] == "952"
    assert not fields.get("_awaiting_additional_test")


def test_quitar_un_adicional_no_toca_la_base():
    fields = _orden_de_joy()
    quitados = orders._remove_order_items_by_code(fields, "saca el 952")
    assert [q["code"] for q in quitados] == ["952"]
    assert fields["_selected_profile_code"] == "653"
    assert not fields.get("_extra_profiles")


def test_codigo_que_no_esta_en_la_orden_no_quita_nada():
    fields = _orden_de_joy()
    assert orders._remove_order_items_by_code(fields, "saca el 1101") == []
    assert fields["_selected_profile_code"] == "653"
