from unittest.mock import patch


def _ai_side_reply(reply, fields=None):
    return {
        "reply": reply,
        "intent": "route_scheduling",
        "phase": "fase_2_recogida_datos",
        "service_area": "route_scheduling",
        "captured_fields": fields or {},
        "message_mode": "side_question",
        "requires_handoff": False,
        "handoff_area": None,
        "resume_prompt": "",
        "confidence": 1.0,
        "pending_intents": [],
    }


def _ai_reply(intent, reply, fields=None, message_mode="flow_progress"):
    return {
        "reply": reply,
        "intent": intent,
        "phase": "fase_2_recogida_datos",
        "service_area": intent,
        "captured_fields": fields or {},
        "message_mode": message_mode,
        "requires_handoff": False,
        "handoff_area": None,
        "resume_prompt": "",
        "confidence": 1.0,
        "pending_intents": [],
        "user_intent_signal": "unclear",
    }


def test_side_question_before_identification_resumes_with_client_lookup():
    from app.agent import process_turn

    session = {
        "external_chat_id": "chat-side-1",
        "client_id": None,
        "phase_current": "fase_2_recogida_datos",
        "intent_current": "route_scheduling",
        "captured_fields": {},
    }
    history = [{"role": "bot", "content": "¿Con qué te ayudamos hoy?"}]

    with patch("app.services.db.get_or_create_session", return_value=session), \
         patch("app.services.db.get_recent_messages", return_value=history), \
         patch("app.services.db.save_message"), \
         patch("app.services.db.update_session"), \
         patch("app.services.db.get_catalog_context", return_value=""), \
         patch("app.services.ai.generate_turn", return_value=_ai_side_reply("Claro, seguimos con la recogida.")):
        reply = process_turn("chat-side-1", "estoy registrado te paso mis datos para programar la recogida")

    assert "NIT" in reply
    assert "nombre de la veterinaria" in reply


def test_side_question_mid_order_resumes_with_missing_field():
    from app.agent import process_turn

    fields = {"_client_found": True, "pickup_address": "Calle 1", "_address_confirmed": True}
    session = {
        "external_chat_id": "chat-side-2",
        "client_id": "client-1",
        "phase_current": "fase_2_recogida_datos",
        "intent_current": "route_scheduling",
        "captured_fields": fields,
    }
    history = [{"role": "bot", "content": "¿Cuál es el médico solicitante?"}]

    with patch("app.services.db.get_or_create_session", return_value=session), \
         patch("app.services.db.get_recent_messages", return_value=history), \
         patch("app.services.db.save_message"), \
         patch("app.services.db.update_session"), \
         patch("app.services.db.get_catalog_context", return_value=""), \
         patch("app.services.ai.interpret_route_field", return_value={"action": "clarify", "value": None, "reply": "Uy, eso no lo manejo por acá."}), \
         patch("app.services.ai.generate_turn", return_value=_ai_side_reply("Uy, eso no lo manejo por acá.", fields)):
        reply = process_turn("chat-side-2", "y cómo va el clima por allá?")

    assert "médico solicitante" in reply


def test_results_turnaround_question_is_answered_not_results_fixed_message():
    from app.agent import process_turn

    session = {
        "external_chat_id": "chat-side-3",
        "client_id": None,
        "phase_current": "fase_1_clasificacion",
        "intent_current": "unknown",
        "captured_fields": {},
    }
    history = [{"role": "bot", "content": "¿Con qué te ayudamos hoy?"}]

    with patch("app.services.db.get_or_create_session", return_value=session), \
         patch("app.services.db.get_recent_messages", return_value=history), \
         patch("app.services.db.save_message"), \
         patch("app.services.db.update_session"), \
         patch("app.services.ai.generate_turn"):
        reply = process_turn("chat-side-3", "Necesito saber cuanto tiempo tardan en dar los resultados primero")

    assert "Depende del análisis" in reply
    assert "consulta de resultados" not in reply
    assert "NIT" not in reply


def test_payment_answer_with_route_time_question_keeps_answer_before_summary():
    from app.agent import process_turn

    fields = {
        "_client_found": True,
        "clinic_name": "Veterinaria San Roque",
        "pickup_address": "Calle 1",
        "_address_confirmed": True,
        "requesting_doctor": "Dra. Laura",
        "patient_name": "Firulais",
        "species": "Canino",
        "breed": "Labrador",
        "sex": "Macho",
        "patient_age": "3 años",
        "owner_name": "Pedro",
        "observations": "sin observaciones",
        "exam_type": "Hemograma",
    }
    session = {
        "external_chat_id": "chat-side-4",
        "client_id": "client-1",
        "phase_current": "fase_2_recogida_datos",
        "intent_current": "route_scheduling",
        "captured_fields": fields,
    }
    history = [{"role": "bot", "content": "Antes de cerrar, ¿cómo prefieres el pago: contraentrega con el motorizado o pago en línea?"}]

    with patch("app.services.db.get_or_create_session", return_value=session), \
         patch("app.services.db.get_recent_messages", return_value=history), \
         patch("app.services.db.save_message"), \
         patch("app.services.db.update_session"), \
         patch("app.services.db.find_diagnostic_label", return_value=None), \
         patch("app.services.db.find_catalog_profiles", return_value=[]), \
         patch("app.services.db.find_tests_by_area", return_value=(None, [])), \
         patch("app.services.ai.generate_turn", return_value=_ai_reply("route_scheduling", "Registro pago en línea.", fields)):
        reply = process_turn("chat-side-4", "Online quiero pagar, más o menos a qué hora llegaría el repartidor?")

    assert "hora exacta de recogida" in reply
    assert "Antes de registrar" in reply
    assert "Forma de pago: pago_linea" in reply


def test_unregistered_answer_escalates_without_client_lookup():
    from app.agent import process_turn

    session = {
        "external_chat_id": "chat-side-5",
        "client_id": None,
        "phase_current": "fase_2_recogida_datos",
        "intent_current": "route_scheduling",
        "captured_fields": {"exam_type": "151-Perfil General"},
    }
    history = [{"role": "bot", "content": "¿Me compartes el NIT o el nombre de la veterinaria o médico veterinario?"}]
    fields = {"exam_type": "151-Perfil General", "clinic_name": "No Estoy Registrado"}
    ai_response = _ai_reply("route_scheduling", "Reviso el cliente.", fields)
    ai_response["user_intent_signal"] = "new_or_unregistered_client"
    updated = {}

    with patch("app.services.db.get_or_create_session", return_value=session), \
         patch("app.services.db.get_recent_messages", return_value=history), \
         patch("app.services.db.save_message"), \
         patch("app.services.db.update_session", side_effect=lambda c, ai: updated.update(ai)), \
         patch("app.services.db.create_request", return_value={"request_id": "req-1"}), \
         patch("app.services.db.find_clients_by_tax_id") as find_by_tax, \
         patch("app.services.db.find_client_matches") as find_matches, \
         patch("app.services.ai.generate_turn", return_value=ai_response):
        reply = process_turn("chat-side-5", "No estoy registrado")

    assert "alta" in reply
    assert "atención al cliente" in reply
    assert "No encuentro" not in reply
    assert updated["captured_fields"].get("clinic_name") is None
    find_by_tax.assert_not_called()
    find_matches.assert_not_called()


def test_client_name_strips_possessive_bridge_before_lookup():
    from app.agent import process_turn

    client = {
        "id": "client-animal-pets",
        "clinic_name": "Animal Pets",
        "tax_id": "53115419-1",
        "address": "DG 51A SUR 61B-03",
        "phone": "300111",
    }
    session = {
        "external_chat_id": "chat-side-6",
        "client_id": None,
        "phase_current": "fase_2_recogida_datos",
        "intent_current": "route_scheduling",
        "captured_fields": {},
    }
    history = [{"role": "bot", "content": "¿Me compartes el NIT o el nombre de la veterinaria o médico veterinario?"}]
    ai_response = _ai_reply("route_scheduling", "Reviso.", {"clinic_name": "Mía Es Animal Pet"})
    ai_response["user_intent_signal"] = "provides_client_identifier"

    with patch("app.services.db.get_or_create_session", return_value=session), \
         patch("app.services.db.get_recent_messages", return_value=history), \
         patch("app.services.db.save_message"), \
         patch("app.services.db.update_session"), \
         patch("app.services.db.link_client_to_session"), \
         patch("app.services.db.get_catalog_context", return_value=""), \
         patch("app.services.db.list_diagnostic_labels", return_value=[]), \
         patch("app.services.db.find_clients_by_tax_id", return_value=[]), \
         patch("app.services.db.find_client_matches", return_value=[client]) as find_matches, \
         patch("app.services.ai.generate_turn", return_value=ai_response):
        reply = process_turn("chat-side-6", "Nombre de la clínica mía es Animal Pet")

    find_matches.assert_called_once_with("Animal Pet", limit=6)
    assert "Animal Pets" in reply


def test_confirmation_with_other_clinic_restarts_identification_instead_of_closing():
    from app.agent import CONFIRMATION_PHASE, process_turn

    fields = {
        "clinic_name": "Animal Pets",
        "pickup_address": "DG 51A SUR 61B-03",
        "_address_confirmed": True,
        "requesting_doctor": "Luciano",
        "patient_name": "Juancito",
        "species": "Canino",
        "breed": "Rottweiler",
        "sex": "Macho",
        "patient_age": "5 años",
        "owner_name": "Cristóbal",
        "observations": "sin observaciones",
        "exam_type": "Hemograma",
        "payment_method": "pago_linea",
    }
    session = {
        "external_chat_id": "chat-side-6",
        "client_id": "client-1",
        "phase_current": CONFIRMATION_PHASE,
        "intent_current": "route_scheduling",
        "captured_fields": fields,
    }
    history = [{"role": "bot", "content": "¿Confirmas estos datos? (Sí / Corregir)"}]

    with patch("app.services.db.get_or_create_session", return_value=session), \
         patch("app.services.db.get_recent_messages", return_value=history), \
         patch("app.services.db.save_message"), \
         patch("app.services.db.update_session"), \
         patch("app.services.db.clear_client_from_session") as clear_client, \
         patch("app.services.db.create_request") as create_request:
        reply = process_turn("chat-side-6", "sí está correcto, pero es para otra veterinaria")

    assert "cambiamos de cliente" in reply.lower()
    assert "NIT" in reply
    clear_client.assert_called_once_with("chat-side-6")
    create_request.assert_not_called()


def test_followup_order_for_other_clients_restarts_identification():
    from app.agent import process_turn

    fields = {
        "clinic_name": "Animal Pets",
        "pickup_address": "DG 51A SUR 61B-03",
        "requesting_doctor": "Luciano",
        "payment_method": "pago_linea",
        "_client_found": True,
        "_order_registered": True,
        "_prev_order_snapshot": {"exam_type": "Hemograma", "patient_name": "Juancito"},
    }
    session = {
        "external_chat_id": "chat-side-7",
        "client_id": "client-1",
        "phase_current": "fase_2_recogida_datos",
        "intent_current": "route_scheduling",
        "captured_fields": fields,
    }
    history = [{"role": "bot", "content": "¿Te ayudo con algo más o necesitas crear otra orden?"}]

    with patch("app.services.db.get_or_create_session", return_value=session), \
         patch("app.services.db.get_recent_messages", return_value=history), \
         patch("app.services.db.save_message"), \
         patch("app.services.db.update_session"), \
         patch("app.services.db.clear_client_from_session") as clear_client:
        reply = process_turn("chat-side-7", "Necesitaría hacer otros análisis para otros clientes")

    assert "cambiamos de cliente" in reply.lower()
    assert "NIT" in reply
    assert "médico solicitante" not in reply
    clear_client.assert_called_once_with("chat-side-7")
