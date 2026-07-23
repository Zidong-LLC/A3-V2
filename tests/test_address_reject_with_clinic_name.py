"""
Regresión ERR-081 (prueba en vivo del usuario, 2026-07-21, chat 10): el bot preguntó
"¿Cuál es la dirección correcta donde debemos retirar la muestra?" y el cliente respondió
con el NOMBRE de otra sede ("Centro veterinario La Uribe"). El modelo lo capturó como
clinic_name, pero la sesión ya tenía client_id, así que nada volvía a buscar: la orden
quedó con el nombre nuevo y el client_id + dirección del cliente VIEJO (AV CL 32 19-26,
del Centro Médico Veterinario). Identidad cruzada: el motorizado iría a la dirección
equivocada y la orden se facturaría al cliente equivocado — y la sede correcta SÍ existía
en la base (Centro Medico Veterinario La Uribe, CL 172A 21A-28).
"""
from unittest.mock import MagicMock, patch

from app import agent

OLD_CLIENT_ID = "cli-OLD"

LA_URIBE = {
    "id": "cli-URIBE", "clinic_name": "Centro Medico Veterinario La Uribe",
    "address": "CL 172A 21A-28", "tax_id": "800900100-1", "phone": "", "email": "",
}

OTRA_SEDE = {
    "id": "cli-OTRA", "clinic_name": "Centro Veterinario La Uribe Norte",
    "address": "CL 180 10-15", "tax_id": "800900200-2", "phone": "", "email": "",
}

# Estado tras el rechazo de la dirección: identificado, pickup_address borrado,
# esperando la dirección correcta (así quedó la sesión real del chat 10).
ADDRESS_REJECTED = {
    "_client_found": True, "clinic_name": "Centro Médico Veterinario",
    "_client_display_name": "Centro Medico Veterinario",
    "_client_address": "AV CL 32 19-26", "tax_id": "19472811-0",
    "pickup_address": None, "_address_confirmed": False,
    "_address_confirmation_pending": False,
}


def _ai_response(captured, signal="unclear", reply="ok"):
    return {
        "reply": reply, "phase": "fase_2_recogida_datos", "intent": "route_scheduling",
        "service_area": "route_scheduling", "requires_handoff": False, "handoff_area": None,
        "captured_fields": captured, "confidence": 0.9, "message_mode": "flow_progress",
        "pending_intents": [], "user_intent_signal": signal, "resume_prompt": "",
    }


def _run_turn(msg, model_captured, exact=None, matches=None):
    session = {
        "external_chat_id": "c1", "client_id": OLD_CLIENT_ID, "channel": "telegram",
        "phase_current": "fase_2_recogida_datos", "intent_current": "route_scheduling",
        "captured_fields": dict(ADDRESS_REJECTED), "status": "in_progress",
    }
    fake_db = MagicMock()
    fake_db.get_or_create_session.return_value = session
    fake_db.get_recent_messages.return_value = [
        {"role": "user", "content": "No se, es la uribe"},
        {"role": "bot", "content": "¿Cuál es la dirección correcta donde debemos retirar la muestra?"},
    ]
    fake_db.get_client_memory.return_value = None
    fake_db.list_catalog_tests.return_value = []
    fake_db.find_tests_by_area.return_value = (None, [])
    fake_db.get_tests_by_codes_or_names.return_value = []
    fake_db.find_client_exact.return_value = exact
    fake_db.find_client_matches.return_value = matches or []
    with patch.object(agent, "db", fake_db), \
         patch.object(agent.ai, "generate_turn", return_value=_ai_response(model_captured)):
        reply = agent.process_turn("c1", msg)
    persisted = (fake_db.update_session.call_args[0][1]
                 if fake_db.update_session.call_args else {})
    return reply, persisted.get("captured_fields", {}), fake_db


def test_nombre_de_sede_existente_re_identifica_y_confirma_su_direccion():
    """El caso real: la sede nombrada existe (match único) → se re-vincula el client_id
    y se confirma la dirección de la sede NUEVA, no la del cliente viejo."""
    captured = dict(ADDRESS_REJECTED, clinic_name="Centro veterinario La Uribe")
    reply, fields, fake_db = _run_turn(
        "Centro veterinario La Uribe", captured, exact=None, matches=[LA_URIBE]
    )
    fake_db.link_client_to_session.assert_called_once_with("c1", "cli-URIBE")
    assert fields.get("clinic_name") == "Centro Medico Veterinario La Uribe"
    assert fields.get("pickup_address") == "CL 172A 21A-28"
    assert "AV CL 32 19-26" not in (reply or ""), "sigue ofreciendo la dirección del cliente viejo"
    assert "CL 172A 21A-28" in (reply or "")


def test_nombre_inexistente_no_pisa_al_cliente_identificado():
    """La sede nombrada NO existe: el cliente identificado queda intacto y se vuelve a
    pedir la dirección — nunca un nombre suelto reemplaza al cliente sin verificar."""
    captured = dict(ADDRESS_REJECTED, clinic_name="Veterinaria Fantasma")
    reply, fields, fake_db = _run_turn(
        "Veterinaria Fantasma", captured, exact=None, matches=[]
    )
    fake_db.link_client_to_session.assert_not_called()
    fake_db.clear_client_from_session.assert_not_called()
    assert fields.get("clinic_name") == "Centro Médico Veterinario"
    assert "dirección" in (reply or "").lower()


def test_varias_sedes_posibles_ofrecen_la_lista_para_elegir():
    """Con más de una coincidencia se muestra la lista (flujo de selección existente);
    no se adivina la sede."""
    captured = dict(ADDRESS_REJECTED, clinic_name="La Uribe")
    reply, fields, fake_db = _run_turn(
        "La Uribe", captured, exact=None, matches=[LA_URIBE, OTRA_SEDE]
    )
    fake_db.clear_client_from_session.assert_called_once()
    options = fields.get("_client_match_options") or []
    assert [o.get("clinic_name") for o in options] == [
        "Centro Medico Veterinario La Uribe", "Centro Veterinario La Uribe Norte",
    ]
    assert "La Uribe" in (reply or "")


def test_responder_con_una_direccion_sigue_el_flujo_normal():
    """Control (paso aprobado): si responde con una DIRECCIÓN, no se re-identifica nada."""
    captured = dict(ADDRESS_REJECTED, pickup_address="CL 100 20-30")
    reply, fields, fake_db = _run_turn("CL 100 20-30", captured)
    fake_db.link_client_to_session.assert_not_called()
    fake_db.clear_client_from_session.assert_not_called()
    assert fields.get("pickup_address") == "CL 100 20-30"
