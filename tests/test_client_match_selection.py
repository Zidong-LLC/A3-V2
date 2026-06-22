"""
Regresión: selección de una opción de la lista de coincidencias de cliente.

Bug "exacto, es la primera": cuando el bot mostraba varias veterinarias y el cliente
elegía una con una respuesta corta de confirmación ("exacto, es la primera" = opción 1),
el agente la interpretaba como "soy cliente nuevo" (por el "exacto") o re-buscaba
"la primera" como el nombre de una veterinaria nueva. La selección de la lista YA mostrada
debe tener prioridad sobre reinterpretar el mensaje como identificador/cliente nuevo, sin
depender de la cantidad de palabras del mensaje (ver tasks/errores-soluciones.md ERR-038).
"""
from unittest.mock import patch

OPTION_1 = {
    "id": "client-A", "clinic_name": "Veterinaria Los Andes",
    "tax_id": "900111111", "phone": "6015550001", "address": "Calle 80 # 10-20, Bogotá",
}
OPTION_2 = {
    "id": "client-B", "clinic_name": "Veterinaria Los Álamos",
    "tax_id": "900222222", "phone": "6015550002", "address": "Carrera 7 # 50-10, Bogotá",
}

# Mensaje del bot del turno anterior: la lista de coincidencias ya mostrada.
MATCH_LIST_BOT_MESSAGE = (
    "Encontré varios clientes registrados con 'los'. ¿Cuál es el correcto?\n"
    "1) Veterinaria Los Andes - Calle 80 # 10-20, Bogotá\n"
    "2) Veterinaria Los Álamos - Carrera 7 # 50-10, Bogotá\n"
    "Responde con el número o el nombre exacto.\n"
    "Si ninguna es la tuya, compárteme el NIT o un nombre más exacto."
)


def _full_ai_response(captured_fields, signal):
    """Respuesta del LLM con TODAS las claves requeridas por el schema. Simula la
    clasificación errónea que disparaba el bug (capturar 'la primera' como nombre y/o
    marcar cliente nuevo por el 'exacto')."""
    return {
        "reply": "ok",
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


def _run(user_message, ai_signal, ai_captured):
    """Ejecuta un turno de process_turn con BD en memoria y un LLM mockeado."""
    session = {
        "chat_id": "chat-1",
        "channel": "telegram",
        "client_id": None,
        "phase_current": "fase_2_recogida_datos",
        "intent_current": "route_scheduling",
        "captured_fields": {
            "_client_match_query": "los",
            "_client_match_options": [
                {k: OPTION_1.get(k) for k in ("id", "clinic_name", "tax_id", "phone", "address")},
                {k: OPTION_2.get(k) for k in ("id", "clinic_name", "tax_id", "phone", "address")},
            ],
        },
    }
    history = [
        {"role": "user", "content": "los"},
        {"role": "bot", "content": MATCH_LIST_BOT_MESSAGE},
    ]

    db_patches = {
        "get_or_create_session": dict(side_effect=lambda c, channel="telegram": session),
        "get_recent_messages": dict(side_effect=lambda c, limit=8: history[-limit:]),
        "save_message": dict(side_effect=lambda c, t, r: history.append({"role": r, "content": t})),
        "update_session": dict(side_effect=lambda c, ai: session.update(
            phase_current=ai["phase"], intent_current=ai["intent"], captured_fields=ai["captured_fields"])),
        "link_client_to_session": dict(side_effect=lambda c, cid: session.update(client_id=cid)),
        "get_client_by_id": dict(side_effect=lambda cid: next(
            (o for o in (OPTION_1, OPTION_2) if o["id"] == cid), None)),
        "get_courier_for_client": dict(return_value=None),
        "get_catalog_context": dict(return_value=""),
        "get_individual_tests_context": dict(return_value=""),
        "find_client_matches": dict(return_value=[]),
        "find_clients_by_tax_id": dict(return_value=[]),
    }

    from app import agent
    patchers = [patch(f"app.services.db.{n}", **kw) for n, kw in db_patches.items()]
    patchers.append(patch.object(
        agent.ai, "generate_turn",
        return_value=_full_ai_response(dict(ai_captured), ai_signal),
    ))
    for p in patchers:
        p.start()
    try:
        reply = agent.process_turn("chat-1", user_message)
    finally:
        for p in patchers:
            p.stop()
    return reply, session


def test_short_confirmation_with_ordinal_selects_option_one():
    """'exacto, es la primera' elige la opción 1, aunque el LLM marque cliente nuevo
    (por el 'exacto') y capture 'la primera' como nombre. No escala ni re-busca."""
    reply, session = _run(
        "exacto, es la primera",
        ai_signal="new_or_unregistered_client",
        ai_captured={"clinic_name": "la primera"},
    )
    assert session["client_id"] == OPTION_1["id"]
    assert "atención al cliente" not in (reply or "").lower()  # no escaló a registro
    assert "no encuentro" not in (reply or "").lower()         # no re-buscó como nombre


def test_plain_ordinal_selects_option_two():
    """'la segunda' elige la opción 2 sin depender de palabras de confirmación."""
    reply, session = _run(
        "la segunda",
        ai_signal="provides_client_identifier",
        ai_captured={"clinic_name": "la segunda"},
    )
    assert session["client_id"] == OPTION_2["id"]


def test_number_selection_still_works():
    """La selección por número ('el 1') sigue funcionando como antes."""
    reply, session = _run(
        "el 1",
        ai_signal="provides_requested_data",
        ai_captured={},
    )
    assert session["client_id"] == OPTION_1["id"]
