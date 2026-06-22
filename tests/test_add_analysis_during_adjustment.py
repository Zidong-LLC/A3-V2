"""
Regresión (chat 4 real, 2026-06-22): agregar otro análisis/perfil se trababa.

Dos fallos reproducidos:
1. Intención compuesta: "quiero el perfil 152 al cual le quiero agregar un analisis extra"
   → el bot fijaba el perfil y saltaba al pago, descartando el "agregar".
2. Pregunta de catálogo durante el ajuste: estando personalizando/confirmando,
   "que analisis de orina tienen" → el bot repetía el resumen sin listar opciones de orina
   y el usuario quedaba sin respuesta.

El arreglo: durante el ajuste de un perfil, una pregunta abierta por ÁREA lista las opciones
de esa área marcadas para AGREGAR al perfil base (no reemplazarlo). Ver errores-soluciones.md.
"""
from unittest.mock import patch

from app import agent

PROFILE_152 = {
    "code": "152", "name": "Perfil Prequirúrgico I", "species": "ambos",
    "description": "Cuadro Hemático, ALT, Creatinina", "price": 24000,
}
URO = {"code": "1601", "name": "Parcial de Orina", "price": 16000, "category": "Uroanálisis"}
URO2 = {"code": "1602", "name": "Urocultivo", "price": 28000, "category": "Uroanálisis"}

BASE_FIELDS = {
    "clinic_name": "Animal Pets",
    "pickup_address": "DG 51A SUR 61B-03",
    "requesting_doctor": "Dr. Gastón Alcojor",
    "patient_name": "Greta",
    "species": "Felino",
    "breed": "Siames",
    "sex": "Hembra",
    "patient_age": "3 años",
    "owner_name": "Jose",
    "observations": "sin observaciones",
    "payment_method": "pago en línea",
    "exam_type": "Perfil Prequirúrgico I",
    "_selected_profile_code": "152",
    "_selected_profile_name": "Perfil Prequirúrgico I",
    "_selected_profile_price": 24000,
}


def test_area_question_while_awaiting_addition_lists_options_not_summary():
    """Con `_awaiting_additional_test` pendiente, 'que analisis de orina tienen' lista las
    opciones de orina (no repite el resumen) y las marca para AGREGAR al perfil base."""
    fields = dict(BASE_FIELDS, _awaiting_additional_test="add")
    with patch.object(agent.db, "get_tests_by_codes_or_names", return_value=[]), \
         patch.object(agent.db, "find_tests_by_area", return_value=("Uroanálisis", [URO, URO2])):
        out = agent._confirmation_analysis_adjustment(
            {"client_id": "client-1"}, fields, "que analisis de orina tienen", None
        )

    assert out is not None
    assert "orina" in out["reply"].lower()
    assert "1601" in out["reply"]
    assert out["captured_fields"]["_test_menu_adds_to_profile"] is True
    assert out["captured_fields"]["_test_menu_options"]
    # No perdió el perfil base ni cerró la orden.
    assert out["captured_fields"]["_selected_profile_code"] == "152"
    assert "¿Confirmas estos datos?" not in out["reply"]


def test_area_question_during_customization_lists_options():
    """Personalizando un perfil, 'que analisis de orina tienen' lista las opciones de área."""
    fields = dict(BASE_FIELDS, _profile_customizing=True)
    ai_response = agent._base_route_response("...", dict(fields))
    with patch.object(agent.db, "find_tests_by_area", return_value=("Uroanálisis", [URO, URO2])):
        out = agent._enforce_profile_customization_changes(ai_response, dict(fields), "que analisis de orina tienen")

    assert "1601" in out["reply"]
    assert out["captured_fields"]["_test_menu_adds_to_profile"] is True


def test_menu_addition_adds_to_base_profile_without_replacing():
    """Elegir una opción del menú de área SUMA al perfil base (lo conserva), no lo reemplaza."""
    fields = dict(BASE_FIELDS,
                  _test_menu_adds_to_profile=True,
                  _test_menu_options=[URO, URO2])

    def by_codes_or_names(items):
        wanted = {str(i) for i in items}
        return [r for r in (URO, URO2) if r["code"] in wanted or r["name"] in items]

    with patch.object(agent.db, "get_tests_by_codes_or_names", side_effect=by_codes_or_names), \
         patch.object(agent.db, "get_tests_by_codes", side_effect=by_codes_or_names):
        out = agent._capture_menu_addition_to_profile({"client_id": "client-1"}, fields, [URO])

    assert out["captured_fields"]["_selected_profile_code"] == "152"   # perfil base intacto
    assert out["captured_fields"]["selected_tests"] == ["1601"]
    assert out["captured_fields"].get("_test_menu_adds_to_profile") is None
    assert out["captured_fields"].get("_profile_customizing") is False
    assert "Parcial de Orina" in out["reply"]


def test_compound_intent_profile_plus_add_does_not_jump_to_payment():
    """'perfil 152 + análisis extra' fija el perfil y pregunta qué agregar,
    sin saltar al pago."""
    session = {"client_id": "client-1"}
    for text in (
        "quiero el perfil 152 al cual le quiero agregar un analisis extra",
        "si quiero el perfil 152 mas un analisis extra",
    ):
        fields = dict(BASE_FIELDS)
        # Sin perfil/pago resueltos aún: simula el turno donde el cliente lo pide.
        for k in ("payment_method", "_selected_profile_code", "_selected_profile_name", "_selected_profile_price"):
            fields.pop(k, None)
        fields["exam_type"] = None
        ai_response = agent._base_route_response("...", fields)

        with patch.object(agent.db, "get_catalog_profiles_by_codes", return_value=[PROFILE_152]), \
             patch.object(agent.db, "find_tests_by_area", return_value=(None, [])), \
             patch.object(agent.db, "get_tests_by_codes_or_names", return_value=[]):
            out = agent._enforce_catalog_profile_code_selection(session, ai_response, text)

        assert out["captured_fields"]["_selected_profile_code"] == "152"
        assert out["captured_fields"]["_profile_customizing"] is True
        assert out["captured_fields"]["_awaiting_additional_test"] == "add"
        assert "agregar" in out["reply"].lower()
        assert "pago" not in out["reply"].lower()


def test_profile_menu_selection_with_extra_analysis_does_not_only_offer_payment_step():
    fields = dict(BASE_FIELDS, _profile_menu_options=[PROFILE_152])
    for k in ("payment_method", "_selected_profile_code", "_selected_profile_name", "_selected_profile_price"):
        fields.pop(k, None)
    fields["exam_type"] = None

    with patch.object(agent.db, "get_catalog_profiles_by_codes", return_value=[PROFILE_152]), \
         patch.object(agent.db, "find_tests_by_area", return_value=(None, [])), \
         patch.object(agent.db, "get_tests_by_codes_or_names", return_value=[]):
        out = agent._capture_profile_menu_selection(
            {"client_id": "client-1"}, fields, PROFILE_152,
            "si quiero el perfil 152 mas un analisis extra",
        )

    assert out["captured_fields"]["_selected_profile_code"] == "152"
    assert out["captured_fields"]["_awaiting_additional_test"] == "add"
    assert "qué análisis quieres agregar" in out["reply"].lower()
    assert "seguimos con el pago" not in out["reply"].lower()


def test_plain_profile_code_still_advances_normally():
    """Sin intención de agregar, 'perfil 152' sigue capturando el perfil y avanzando (B6 intacto)."""
    session = {"client_id": "client-1"}
    fields = dict(BASE_FIELDS)
    for k in ("payment_method", "_selected_profile_code", "_selected_profile_name", "_selected_profile_price"):
        fields.pop(k, None)
    fields["exam_type"] = None
    ai_response = agent._base_route_response("...", fields)

    with patch.object(agent.db, "get_catalog_profiles_by_codes", return_value=[PROFILE_152]):
        out = agent._enforce_catalog_profile_code_selection(session, ai_response, "el perfil 152")

    assert out["captured_fields"]["_selected_profile_code"] == "152"
    assert out["captured_fields"].get("_awaiting_additional_test") is None
    assert out["captured_fields"].get("_profile_customizing") is not True
