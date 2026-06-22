"""
Parte B (pedido del usuario, 2026-06-22): antes del resumen final, ofrecer agregar otro
análisis/perfil o personalizar, y repetir tras cada agregado hasta que el cliente siga al
pago. Debe tener salida robusta (no bucle). Ver RESUELTO-017.
"""
from unittest.mock import patch

from app import agent

GLUCOSA = {"code": "1316", "name": "Glucosa (Ayunas)", "price": 12000, "category": "Química"}

COMPLETE = {
    "_client_found": True,
    "clinic_name": "Animal Pets",
    "pickup_address": "DG 51A SUR 61B-03",
    "requesting_doctor": "Dr Gastón",
    "patient_name": "Greta",
    "species": "Canino",
    "breed": "Bulldog",
    "sex": "Hembra",
    "patient_age": "3 años",
    "owner_name": "Jose",
    "observations": "sin observaciones",
    "exam_type": "Perfil Prequirúrgico I",
    "_selected_profile_code": "152",
    "_selected_profile_name": "Perfil Prequirúrgico I",
    "_selected_profile_price": 24000,
}
SESSION = {"client_id": "c1"}


def test_offers_extra_analysis_when_only_payment_missing():
    fields = dict(COMPLETE)
    out = agent._analysis_settled_response(SESSION, fields, "Listo, registro X.")
    assert fields["_offering_extra_analysis"] is True
    assert "agregar otro análisis" in out["reply"]
    assert "seguimos con el pago" in out["reply"]


def test_proceed_detection():
    for t in ("no", "así está bien", "no, seguimos con el pago", "listo", "ya", "contraentrega"):
        assert agent._wants_to_proceed_to_payment(t) is True
    for t in ("agregale glucosa", "quitale la creatinina", "otro perfil"):
        assert agent._wants_to_proceed_to_payment(t) is False


def test_answer_decline_goes_to_payment():
    fields = dict(COMPLETE, _offering_extra_analysis=True)
    out = agent._handle_extra_analysis_answer(SESSION, fields, "no, así está bien")
    assert fields.get("_offering_extra_analysis") is None
    assert out["reply"] == agent.PAYMENT_METHOD_QUESTION


def test_answer_payment_method_returns_none_to_let_pipeline_capture():
    fields = dict(COMPLETE, _offering_extra_analysis=True)
    out = agent._handle_extra_analysis_answer(SESSION, fields, "contraentrega")
    assert out is None
    assert fields.get("_offering_extra_analysis") is None


def test_answer_named_test_adds_and_reoffers():
    fields = dict(COMPLETE, _offering_extra_analysis=True)
    with patch.object(agent.db, "get_tests_by_codes_or_names", return_value=[GLUCOSA]), \
         patch.object(agent.db, "find_tests_by_area", return_value=(None, [])):
        out = agent._handle_extra_analysis_answer(SESSION, fields, "agregale glucosa")
    assert fields["selected_tests"] == ["1316"]
    assert fields["_offering_extra_analysis"] is True  # se vuelve a ofrecer
    assert "agrego" in out["reply"].lower()
    assert "seguimos con el pago" in out["reply"]


def test_answer_bare_yes_asks_which():
    fields = dict(COMPLETE, _offering_extra_analysis=True)
    with patch.object(agent.db, "get_tests_by_codes_or_names", return_value=[]), \
         patch.object(agent.db, "find_tests_by_area", return_value=(None, [])):
        out = agent._handle_extra_analysis_answer(SESSION, fields, "sí, dale")
    assert fields.get("_awaiting_additional_test") == "add"
    assert "Qué análisis quieres agregar" in out["reply"]


def test_new_order_resets_offer_flag():
    assert "_offering_extra_analysis" in agent._ORDER_RESET_FIELDS
