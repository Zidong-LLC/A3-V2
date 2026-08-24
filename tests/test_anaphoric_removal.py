"""
ERR-143 — "No ese sácalo" se ignoraba por completo.

Test en vivo (2026-08-21): el bot ofreció seguir con el perfil heredado ("Claro, seguimos
con Perfil Senior Canino III ($58.000). ¿Qué análisis quieres agregarle?") y el cliente
respondió "No ese sácalo". El bot saltó a preguntar observaciones — ni lo sacó ni acusó
recibo. Dos capas: "sácalo" (clítico) no estaba en ningún token de quitar, y "ese" no
nombra nada — hay que resolver la referencia contra los ítems de la orden.

Regla: UN ítem en la orden → referente inequívoco, se quita; varios → pregunta cerrada
con la lista (ante la duda se pregunta, no se adivina).
"""
import pytest

from app.detectors.analisis import _is_anaphoric_removal
from app.enforcers import orden


PERFIL_653 = {"code": "653", "name": "Perfil Senior Canino III", "price": 58000}
PERFIL_952 = {"code": "952", "name": "Perfil Toxicológico Órgano Fosforados", "price": 90000}


@pytest.fixture(autouse=True)
def aislar_infra(monkeypatch):
    monkeypatch.setattr(orden.db, "get_tests_by_codes_or_names", lambda terms: [])
    monkeypatch.setattr(orden.db, "get_catalog_profiles_by_codes", lambda c, s=None: [])
    monkeypatch.setattr(orden.db, "list_catalog_tests", lambda limit=5000: [])
    monkeypatch.setattr(orden, "_area_options_for_profile_addition", lambda *a, **k: None)
    monkeypatch.setattr(orden, "_category_profiles_menu_response", lambda *a, **k: None)
    # La respuesta centralizada re-ofrece/avanza; acá solo importa el acuse.
    monkeypatch.setattr(orden, "_analysis_settled_response",
                        lambda session, fields, intro: {"reply": intro, "captured_fields": fields})


def test_detector_frase_real():
    assert _is_anaphoric_removal("No ese sácalo") is True


@pytest.mark.parametrize("frase", ["quita eso", "eso sacalo", "elimínalo, ese no"])
def test_detector_variantes(frase):
    assert _is_anaphoric_removal(frase) is True


@pytest.mark.parametrize("frase", [
    "saca el 653",                 # nombra código: no es anafórico
    "la orden está sin observaciones",  # "sin" no es verbo de quitar
    "quita la glucosa",            # nombra análisis, lo resuelve el catálogo
])
def test_detector_no_dispara_de_mas(frase):
    if frase == "quita la glucosa":
        # dispara el verbo pero SIN pronombre no es anafórico
        assert _is_anaphoric_removal(frase) is False
    else:
        assert _is_anaphoric_removal(frase) is False


def test_un_solo_item_se_quita_directo():
    """Con un único ítem, 'ese' es inequívoco: se quita sin repreguntar."""
    fields = {"_offering_extra_analysis": True, "exam_type": "Perfil Senior Canino III",
              "_selected_profile_code": "653", "_selected_profile_name": "Perfil Senior Canino III",
              "_selected_profile_price": 58000}
    out = orden._handle_extra_analysis_answer({}, fields, "No ese sácalo")
    assert out is not None
    assert "quito 653" in out["reply"]
    assert not fields.get("_selected_profile_code")


def test_varios_items_pregunta_cual():
    """Con base + adicional, se pregunta con la lista y queda esperando el código."""
    fields = {"_offering_extra_analysis": True, "exam_type": "Perfil Senior Canino III",
              "_selected_profile_code": "653", "_selected_profile_name": "Perfil Senior Canino III",
              "_selected_profile_price": 58000,
              "_extra_profiles": [dict(PERFIL_952)]}
    out = orden._handle_extra_analysis_answer({}, fields, "No ese sácalo")
    assert out is not None
    assert "cuál quito" in out["reply"] or "cual quito" in out["reply"]
    assert "653" in out["reply"] and "952" in out["reply"]
    assert fields["_awaiting_additional_test"] == "remove"


def test_el_codigo_que_responde_a_cual_quito_quita():
    """Turno siguiente: '952' con la espera de remoción armada QUITA el adicional."""
    fields = {"_offering_extra_analysis": True, "_awaiting_additional_test": "remove",
              "exam_type": "Perfil Senior Canino III",
              "_selected_profile_code": "653", "_selected_profile_name": "Perfil Senior Canino III",
              "_selected_profile_price": 58000,
              "_extra_profiles": [dict(PERFIL_952)]}
    out = orden._handle_extra_analysis_answer({}, fields, "952")
    assert out is not None
    assert "quito 952" in out["reply"]
    assert fields["_selected_profile_code"] == "653"
    assert not fields.get("_extra_profiles")
    assert not fields.get("_awaiting_additional_test")


def test_saca_el_653_por_codigo_en_la_oferta():
    """ERR-141 en el carril de la OFERTA: quitar un PERFIL por código también funciona acá."""
    fields = {"_offering_extra_analysis": True, "exam_type": "Perfil Senior Canino III",
              "_selected_profile_code": "653", "_selected_profile_name": "Perfil Senior Canino III",
              "_selected_profile_price": 58000}
    out = orden._handle_extra_analysis_answer({}, fields, "saca el 653")
    assert out is not None
    assert "quito 653" in out["reply"]
    assert not fields.get("_selected_profile_code")
