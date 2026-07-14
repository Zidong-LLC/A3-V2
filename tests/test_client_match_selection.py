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


def _run(user_message, ai_signal, ai_captured, options=None):
    """Ejecuta un turno de process_turn con BD en memoria y un LLM mockeado."""
    listed = options if options is not None else [OPTION_1, OPTION_2]
    session = {
        "chat_id": "chat-1",
        "channel": "telegram",
        "client_id": None,
        "phase_current": "fase_2_recogida_datos",
        "intent_current": "route_scheduling",
        "captured_fields": {
            "_client_match_query": "los",
            "_client_match_options": [
                {k: o.get(k) for k in ("id", "clinic_name", "tax_id", "phone", "address")}
                for o in listed
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
        # Rutas SIN selección (re-pedir nombre exacto / escalar a cliente nuevo):
        "find_client_exact": dict(return_value=None),
        "create_request": dict(return_value={"request_id": "req-1", "order_number": "A3-2026-001"}),
        "create_pending_client_review": dict(return_value=None),
        "clear_client_from_session": dict(side_effect=lambda c: session.update(client_id=None)),
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


# ── ABIERTO-004: afirmación con coincidencia ÚNICA ────────────────────────────
# Ante "Lo más parecido que encuentro es: 1) X ... ¿Es esta?", el "sí, esa está
# bien" debe seleccionar la única opción de forma determinista (antes quedaba a
# merced del modelo: re-pedía el nombre exacto y descarrilaba la identificación).


def test_affirmation_with_single_match_selects_it():
    """'sí, esa está bien' con UNA sola coincidencia la selecciona (fallback tokens)."""
    reply, session = _run(
        "sí, esa está bien",
        ai_signal="provides_requested_data",
        ai_captured={},
        options=[OPTION_1],
    )
    assert session["client_id"] == OPTION_1["id"]
    assert "nombre exacto" not in (reply or "").lower()


def test_affirm_signal_selects_single_match_without_exact_tokens():
    """La lectura semántica de la IA (affirm) selecciona aunque la frase no tenga
    los tokens afirmativos exactos ('esa misma que te digo')."""
    reply, session = _run(
        "esa misma que te digo",
        ai_signal="affirm",
        ai_captured={},
        options=[OPTION_1],
    )
    assert session["client_id"] == OPTION_1["id"]


def test_affirmation_with_two_matches_does_not_select():
    """Con DOS coincidencias, un 'sí' pelado es ambiguo: NO selecciona; se re-pide
    la precisión (número/nombre exacto) como antes."""
    reply, session = _run(
        "sí, esa está bien",
        ai_signal="affirm",
        ai_captured={},
    )
    assert session["client_id"] is None


def test_new_client_claim_with_single_match_is_not_selected():
    """'sí, somos un cliente nuevo' NO se toma como selección de la coincidencia."""
    reply, session = _run(
        "sí, somos un cliente nuevo",
        ai_signal="new_or_unregistered_client",
        ai_captured={},
        options=[OPTION_1],
    )
    assert session["client_id"] is None


# ── QA modelo real: selección por palabra distintiva con relleno ──────────────
# 'la de quinta paredes' no elegía la sede porque el substring del texto COMPLETO
# ('la_de_quinta_paredes') no estaba contenido en el nombre. Ahora se puntúa por
# palabras significativas compartidas.


def test_selection_by_distinctive_word_with_filler():
    """'la de los andes' elige la sede correcta pese a las palabras de relleno."""
    reply, session = _run(
        "la de los andes",
        ai_signal="provides_client_identifier",
        ai_captured={"clinic_name": "la de los andes"},
    )
    assert session["client_id"] == OPTION_1["id"]


def test_selection_by_shared_word_common_to_both_stays_ambiguous():
    """Una palabra común a AMBAS sedes ('veterinaria') no alcanza para elegir."""
    reply, session = _run(
        "la veterinaria esa",
        ai_signal="provides_client_identifier",
        ai_captured={"clinic_name": "la veterinaria esa"},
    )
    assert session["client_id"] is None


# ── Cambio de SEDE mantiene el paciente y el análisis (QA extremo) ────────────

def test_branch_switch_keeps_patient_and_analysis():
    """'esta orden es para la otra sede' descarta solo la identificación/dirección pero
    conserva el paciente, el análisis, el médico y el pago (no reinicia la orden entera)."""
    from app import agent as ag
    session = {"chat_id": "c1", "client_id": "client-A"}
    fields = {
        "clinic_name": "Puppy Export Centro Mayor", "tax_id": "901780420",
        "pickup_address": "Calle 38", "_client_found": True, "_address_confirmed": True,
        "patient_name": "Nayara", "species": "Felino", "sex": "Hembra", "patient_age": "4 años",
        "requesting_doctor": "Ramirez", "owner_name": "Pedro",
        "selected_tests": ["1316"], "payment_method": "contraentrega",
    }
    with patch("app.services.db.clear_client_from_session"):
        out = ag._switch_branch_keep_order("c1", session, dict(fields))
    f = out["captured_fields"]
    # Identificación y dirección: descartadas.
    assert not f.get("clinic_name") and not f.get("tax_id") and not f.get("pickup_address")
    # Datos de la orden: se mantienen.
    assert f.get("patient_name") == "Nayara" and f.get("species") == "Felino"
    assert ag._as_text_items(f.get("selected_tests")) == ["1316"]
    assert f.get("requesting_doctor") == "Ramirez" and f.get("payment_method") == "contraentrega"
