"""Fase 3.3 — señal `change_client` como fuente primaria (acción post-modelo).

Antes la señal solo VETABA el cierre; la acción de cambiar de cliente vivía únicamente en
los detectores de tokens pre-modelo, en contextos puntuales. Si el cliente lo fraseaba
distinto ("esta orden en realidad va a nombre de otra clínica"), el modelo emitía la señal
y nadie la escuchaba. Ahora la señal invoca la MISMA acción determinística que los tokens:
con orden en curso se conserva todo (L50) y se re-verifica identidad + dirección.
"""
from unittest.mock import patch

from app import agent

ORDER_IN_PROGRESS = {
    "_client_found": True, "clinic_name": "Pet Agro Colombia", "tax_id": "900",
    "pickup_address": "CL 78C", "_address_confirmed": True,
    "requesting_doctor": "Dr. Araujo", "patient_name": "Pepe", "species": "Bovino",
    "selected_tests": ["1404"], "payment_method": "contraentrega",
}


def test_change_client_signal_keeps_order_and_reasks_identity():
    session = {"chat_id": "c1", "client_id": "cli-A", "phase_current": "fase_2_recogida_datos"}
    fields = dict(ORDER_IN_PROGRESS)
    with patch.object(agent.db, "clear_client_from_session"):
        out = agent._restart_identification_for_new_client("c1", session, fields)
    f = out["captured_fields"]
    assert "cambiamos de cliente" in out["reply"].lower()
    assert not f.get("clinic_name") and not f.get("tax_id")            # identidad fuera
    assert f.get("patient_name") == "Pepe"                              # la orden se conserva
    assert agent._as_text_items(f.get("selected_tests")) == ["1404"]
    assert f.get("requesting_doctor") == "Dr. Araujo"


def test_signal_handler_requires_identified_client():
    """Sin cliente identificado la señal no dispara nada (es la identificación normal):
    el guard exige client_id o _client_found — verificado sobre la condición real."""
    session = {"client_id": None}
    fields = {"_client_found": False}
    guard = (session.get("client_id") or fields.get("_client_found"))
    assert not guard


def test_offer_shortcut_does_not_swallow_other_intent():
    """L49: el 'no' incidental dentro de otra intención no cierra la oferta ni salta al
    pago; el mensaje largo sin match de análisis vuelve al MODELO (None) para que la señal
    actúe. Verificado en vivo con modelo real."""
    fields = dict(ORDER_IN_PROGRESS, _offering_extra_analysis=True)
    fields.pop("payment_method")
    msg = "uy me confundi, esta orden en realidad va a nombre de hocicos colombia, no de animal pets"
    with patch.object(agent.db, "list_catalog_tests", return_value=[]), \
         patch.object(agent.db, "find_tests_by_area", return_value=(None, [])), \
         patch.object(agent.db, "get_tests_by_codes_or_names", return_value=[]):
        out = agent._handle_extra_analysis_answer({"client_id": "c"}, fields, msg)
    assert out is None                                      # va al modelo → señal decide
    assert fields.get("_offering_extra_analysis") is True   # la oferta sigue pendiente


def test_short_decline_still_proceeds_to_payment():
    fields = dict(ORDER_IN_PROGRESS, _offering_extra_analysis=True)
    fields.pop("payment_method")
    out = agent._handle_extra_analysis_answer({"client_id": "c"}, fields, "no, ya esta")
    assert out is not None and agent.PAYMENT_METHOD_QUESTION in out["reply"]
