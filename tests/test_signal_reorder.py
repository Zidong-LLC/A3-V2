"""Fase 3.3 — REORDEN pre-LLM (Tanda C): los atajos de INTENCIÓN que decidían por tokens
ANTES del modelo se degradan; el turno llega al modelo y el handler post-modelo actúa
SEÑAL-primero con los mismos tokens de RED y guards portados.

Estos tests prueban la MECÁNICA del pipeline con la señal fingida (guards, acción,
fallback por tokens). La emisión real de la señal la validan validate_flows.py (modelo
real) y la prueba en vivo — lección L51: no fingir el modelo para validar comprensión."""
from unittest.mock import MagicMock, patch

from app import agent


def _neutral_ai_response(signal="unclear", reply="ok, sigo con la orden"):
    return {
        "reply": reply, "phase": "fase_2_recogida_datos", "intent": "route_scheduling",
        "service_area": "route_scheduling", "requires_handoff": False, "handoff_area": None,
        "captured_fields": {}, "confidence": 0.9, "message_mode": "flow_progress",
        "pending_intents": [], "user_intent_signal": signal, "resume_prompt": "",
    }


REGISTERED = {
    "_client_found": True, "_order_registered": True, "clinic_name": "Animal Pets",
    "tax_id": "900123", "pickup_address": "DG 51A SUR", "_address_confirmed": True,
    "requesting_doctor": "Dr Titi", "patient_name": "Lolo", "species": "Equino",
    "selected_tests": ["1404"], "payment_method": "contraentrega",
}


def _run_turn(msg, signal, captured=None):
    session = {
        "external_chat_id": "c1", "client_id": "cli-A", "channel": "telegram",
        "phase_current": "fase_2_recogida_datos", "intent_current": "route_scheduling",
        "captured_fields": dict(captured if captured is not None else REGISTERED),
        "status": "in_progress",
    }
    fake_db = MagicMock()
    fake_db.get_or_create_session.return_value = session
    fake_db.get_recent_messages.return_value = [
        {"role": "user", "content": "hola"}, {"role": "bot", "content": "¿en qué te ayudo?"},
    ]
    fake_db.get_client_memory.return_value = None
    fake_db.list_catalog_tests.return_value = []
    fake_db.find_tests_by_area.return_value = (None, [])
    fake_db.get_tests_by_codes_or_names.return_value = []
    with patch.object(agent, "db", fake_db), \
         patch.object(agent.ai, "generate_turn", return_value=_neutral_ai_response(signal)):
        reply = agent.process_turn("c1", msg)
    persisted = (fake_db.update_session.call_args[0][1]
                 if fake_db.update_session.call_args else {})
    return reply, persisted, fake_db


def test_c1_tokens_are_the_net_when_signal_missing():
    """Red de tokens: el fraseo conocido dispara el followup aunque el modelo no emita
    la señal (unclear). El atajo pre-LLM degradado no pierde el caso conocido."""
    reply, persisted, _ = _run_turn("quiero otra orden para otro paciente", "unclear")
    fields = persisted.get("captured_fields", {})
    assert fields.get("_prev_order_snapshot"), "no arrancó la orden de seguimiento"
    assert not fields.get("patient_name")            # paciente reseteado
    assert fields.get("_client_found") is True       # cliente conservado


def test_c1_signal_covers_unknown_phrasing():
    """Señal-primero: un fraseo que los tokens NO conocen dispara el mismo followup
    cuando el modelo emite another_order. Esta es la ganancia del reorden."""
    msg = "me quedó pendiente enviarles sangre de un segundo peludo"
    assert not agent._explicitly_wants_another_order(msg)   # los tokens no lo cubren
    reply, persisted, _ = _run_turn(msg, "another_order")
    fields = persisted.get("captured_fields", {})
    assert fields.get("_prev_order_snapshot"), "la señal no disparó el followup"
    assert not fields.get("patient_name")


def test_c1_no_registered_order_means_no_followup():
    """Guard: sin orden registrada, ni la señal ni los tokens inician un followup —
    queda la respuesta del pipeline normal."""
    captured = dict(REGISTERED)
    captured.pop("_order_registered")
    reply, persisted, _ = _run_turn("quiero otra orden para otro paciente", "another_order")
    # con _order_registered sí dispara (control positivo del guard)
    assert persisted.get("captured_fields", {}).get("_prev_order_snapshot")
    reply2, persisted2, _ = _run_turn("necesito otra cosa", "unclear", captured=captured)
    fields2 = persisted2.get("captured_fields", {})
    assert not fields2.get("_prev_order_snapshot")
