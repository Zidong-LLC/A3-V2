"""
Regresión ERR-046 (flujo H de validate_flows, 2026-07-03): con la confirmación de
dirección PENDIENTE ("¿Es correcta?"), si el cliente respondía otra cosa ("quiero un
análisis de orina"), el guardrail de progreso contaba lo capturado en ESE MISMO turno
como "el flujo ya avanzó" y daba la dirección por confirmada en silencio; el bot seguía
con la siguiente pregunta y la confirmación se perdía. Fix: el progreso solo cuenta
turnos ANTERIORES, y ante una respuesta que no resuelve la confirmación se conserva lo
capturado pero se re-pregunta la dirección en el mismo mensaje.
"""
from unittest.mock import patch

from app import agent

REGISTERED_ADDRESS = "Calle 45 # 12-34, Bogotá"


def _full_ai_response(reply, captured_fields, signal):
    return {
        "reply": reply,
        "intent": "route_scheduling",
        "phase": "fase_2_recogida_datos",
        "service_area": "route_scheduling",
        "captured_fields": captured_fields,
        "message_mode": "flow_progress",
        "user_intent_signal": signal,
        "requires_handoff": False,
        "handoff_area": None,
        "resume_prompt": "",
        "confidence": 1.0,
        "pending_intents": [],
    }


def _run(user_message, ai_reply, ai_captured, ai_signal="provides_requested_data",
         prev_extra=None):
    """Turno completo con cliente ya identificado y confirmación de dirección pendiente."""
    prev_fields = {
        "_client_found": True,
        "clinic_name": "Veterinaria San Roque",
        "pickup_address": REGISTERED_ADDRESS,
        "_client_address": REGISTERED_ADDRESS,
        "_address_confirmation_pending": True,
        "_address_confirmed": False,
    }
    prev_fields.update(prev_extra or {})
    session = {
        "chat_id": "chat-1",
        "channel": "telegram",
        "client_id": "client-A",
        "phase_current": "fase_2_recogida_datos",
        "intent_current": "route_scheduling",
        "captured_fields": prev_fields,
    }
    history = [
        {"role": "user", "content": "Somos la Veterinaria San Roque"},
        {"role": "bot", "content": f"Tenemos como domicilio de retiro: {REGISTERED_ADDRESS}. ¿Es correcta?"},
    ]
    merged_captured = dict(prev_fields)
    merged_captured.update(ai_captured)

    db_patches = {
        "get_or_create_session": dict(side_effect=lambda c, channel="telegram": session),
        "get_recent_messages": dict(side_effect=lambda c, limit=8: history[-limit:]),
        "save_message": dict(side_effect=lambda c, t, r: history.append({"role": r, "content": t})),
        "update_session": dict(side_effect=lambda c, ai: session.update(
            phase_current=ai["phase"], intent_current=ai["intent"], captured_fields=ai["captured_fields"])),
        "get_client_by_id": dict(return_value={
            "id": "client-A", "clinic_name": "Veterinaria San Roque",
            "tax_id": "900123456", "phone": "6015551234", "address": REGISTERED_ADDRESS,
        }),
        "get_courier_for_client": dict(return_value=None),
        "get_catalog_context": dict(return_value=""),
        "get_individual_tests_context": dict(return_value=""),
        "get_last_order_for_client": dict(return_value=None),
        "list_diagnostic_labels": dict(return_value=[]),
        "find_diagnostic_label": dict(return_value=None),
        "get_tests_for_label": dict(return_value=[]),
        "find_tests_by_area": dict(return_value=(None, [])),
        "get_tests_by_codes_or_names": dict(return_value=[]),
        "get_tests_by_codes": dict(return_value=[]),
        "find_catalog_profiles": dict(return_value=[]),
        "find_catalog_profile": dict(return_value=None),
        "get_catalog_profiles_by_codes": dict(return_value=[]),
        "list_catalog_profiles_for_species": dict(return_value=[]),
        "list_catalog_profiles_matching_category": dict(return_value=[]),
    }

    patchers = [patch(f"app.services.db.{n}", **kw) for n, kw in db_patches.items()]
    patchers.append(patch.object(
        agent.ai, "generate_turn",
        return_value=_full_ai_response(ai_reply, merged_captured, ai_signal),
    ))
    for p in patchers:
        p.start()
    try:
        reply = agent.process_turn("chat-1", user_message)
    finally:
        for p in patchers:
            p.stop()
    return reply, session["captured_fields"]


def test_dodge_keeps_data_and_reasks_address():
    """'quiero un análisis de orina' ante '¿Es correcta?' conserva lo capturado pero
    RE-PREGUNTA la dirección; no la da por confirmada en silencio."""
    reply, fields = _run(
        "quiero un análisis de orina",
        ai_reply="Perfecto, lo anoto. ¿Cuál es el médico solicitante?",
        ai_captured={"exam_type": "Parcial de Orina"},
    )
    assert fields.get("_address_confirmation_pending") is True
    assert fields.get("_address_confirmed") is not True
    assert fields.get("exam_type") == "Parcial de Orina"
    assert REGISTERED_ADDRESS in (reply or "")
    assert "médico" not in (reply or "").lower()


def test_confirmation_still_resolves_address():
    """'sí, esa está bien' sigue confirmando la dirección como antes."""
    reply, fields = _run(
        "sí, esa está bien",
        ai_reply="Perfecto. ¿Cuál es el médico solicitante?",
        ai_captured={},
        ai_signal="affirm",
    )
    assert fields.get("_address_confirmation_pending") is False
    assert fields.get("_address_confirmed") is True


def test_new_address_in_message_counts_as_correction():
    """Si en vez de confirmar da OTRA dirección, esa vale como corrección confirmada."""
    reply, fields = _run(
        "mejor recojan en la Carrera 9 # 8-76",
        ai_reply="Listo, registro Carrera 9 # 8-76. ¿Cuál es el médico solicitante?",
        ai_captured={"pickup_address": "Carrera 9 # 8-76"},
    )
    assert fields.get("_address_confirmation_pending") is False
    assert fields.get("_address_confirmed") is True
    assert fields.get("pickup_address") == "Carrera 9 # 8-76"


def test_legacy_progressed_session_still_autoconfirms():
    """Sesión que YA avanzó en turnos anteriores (médico/paciente/análisis previos):
    el flag pegado se baja solo, y un 'no' posterior (p. ej. de observaciones) no se
    reinterpreta como rechazo de la dirección."""
    reply, fields = _run(
        "no",
        ai_reply="Perfecto, sin observaciones. ¿Qué análisis o perfil desean?",
        ai_captured={"observations": "sin observaciones"},
        prev_extra={
            "requesting_doctor": "Dra. Laura Méndez",
            "patient_name": "Firulais",
            "species": "Canino",
        },
    )
    assert fields.get("_address_confirmation_pending") is False
    assert fields.get("_address_confirmed") is True


# ── Fase 3.3 (piloto): confirmación de dirección por señal del LLM ──────────────
# La confirmación deja de depender de listas de tokens: la lectura semántica de la IA
# (user_intent_signal) es la fuente primaria; los tokens son fallback.


def test_confirms_address_signal_beats_misleading_tokens():
    """'no hay drama, esa dirección está bien' CONFIRMA, pero tiene un 'no' que hace que los
    tokens la RECHACEN. La lectura semántica de la IA (affirm) manda sobre los tokens."""
    msg = "no hay drama, esa dirección está bien"
    assert not agent._confirms_address(msg)                       # los tokens la tumban por el 'no'
    assert agent._confirms_address_now({"user_intent_signal": "affirm"}, msg)
    # y al revés: un 'sí' incidental NO confirma si la IA leyó que rechaza/corrige
    assert not agent._confirms_address_now({"user_intent_signal": "negate"}, "sí")


def test_rejects_address_by_signal():
    assert agent._rejects_address_now({"user_intent_signal": "negate"}, "esa no")
    assert agent._rejects_address_now({"user_intent_signal": "correction"}, "cambiala")
    assert not agent._rejects_address_now({"user_intent_signal": "affirm"}, "no")  # affirm gana


def test_address_signal_fallback_preserves_tokens():
    """Sin señal clara (unclear), se mantiene el comportamiento por tokens."""
    unclear = {"user_intent_signal": "unclear"}
    assert agent._confirms_address_now(unclear, "sí, correcta")
    assert not agent._confirms_address_now(unclear, "no, es otra")
    assert agent._rejects_address_now(unclear, "no, es otra")
