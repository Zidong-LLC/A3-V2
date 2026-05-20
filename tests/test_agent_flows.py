"""
Tests de flujo del agente con mocks de servicios externos.
Cubre casos 1, 2, 3, 5, 7, 8, 9, 10, 11 del bootstrap sección 12.
"""
import pytest
from unittest.mock import patch, MagicMock


# Fixtures

def _make_session(phase="fase_1_clasificacion", intent="unknown", client_id=None, captured=None):
    return {
        "external_chat_id": "test-chat-1",
        "client_id": client_id,
        "phase_current": phase,
        "intent_current": intent,
        "captured_fields": captured or {},
    }


_HISTORY_WITH_CONTEXT = [
    {"role": "user", "content": "Hola"},
    {"role": "bot", "content": "Hola, en que te puedo ayudar?"},
]


def _make_ai_response(phase, intent, requires_handoff=False, handoff_area=None, pending=None):
    return {
        "reply": "respuesta de prueba",
        "intent": intent,
        "phase": phase,
        "service_area": intent,
        "captured_fields": {
            "clinic_name": None,
            "tax_id": None,
            "pickup_address": "Calle 1",
            "exam_type": "hemograma",
            "patient_name": None,
            "species": None,
            "patient_age": None,
            "owner_name": None,
            "payment_method": None,
            "selected_tests": None,
            "removed_tests": None,
            "_pending_intents": pending or [],
        },
        "message_mode": "flow_progress",
        "requires_handoff": requires_handoff,
        "handoff_area": handoff_area,
        "resume_prompt": "",
        "confidence": 0.95,
        "pending_intents": pending or [],
    }


# Test 1: cliente con motorizado asignado -> solicitud 'assigned'

def test_request_assigned_when_courier_exists():
    session = _make_session(client_id="client-uuid-1")
    ai_resp = _make_ai_response("fase_6_cierre", "route_scheduling")
    ai_resp["captured_fields"].update({
        "patient_name": "Toby",
        "species": "canino",
        "payment_method": "contraentrega",
    })

    courier = {"id": "courier-uuid-1", "name": "Carlos", "phone": "123", "availability": "available"}

    with patch("app.services.db.get_or_create_session", return_value=session), \
         patch("app.services.db.get_recent_messages", return_value=_HISTORY_WITH_CONTEXT), \
         patch("app.services.db.get_catalog_context", return_value=""), \
         patch("app.services.ai.generate_turn", return_value=ai_resp), \
         patch("app.services.db.identify_client", return_value=None), \
         patch("app.services.db.save_message"), \
         patch("app.services.db.update_session"), \
         patch("app.services.db.get_courier_for_client", return_value=courier) as mock_courier, \
         patch("app.services.db.create_request", return_value="req-uuid-1") as mock_create:

        from app.agent import process_turn
        process_turn("test-chat-1", "Necesito una ruta para hoy")

        mock_create.assert_called_once()
        call_args = mock_create.call_args[0]
        assert call_args[2]["intent"] == "route_scheduling"


# Test 2: cliente sin motorizado -> error_pending_assignment

def test_request_error_when_no_courier():
    session = _make_session(client_id="client-uuid-2")
    ai_resp = _make_ai_response("fase_6_cierre", "route_scheduling")
    ai_resp["captured_fields"].update({
        "patient_name": "Toby",
        "species": "canino",
        "payment_method": "contraentrega",
    })

    with patch("app.services.db.get_or_create_session", return_value=session), \
         patch("app.services.db.get_recent_messages", return_value=_HISTORY_WITH_CONTEXT), \
         patch("app.services.ai.generate_turn", return_value=ai_resp), \
         patch("app.services.db.identify_client", return_value=None), \
         patch("app.services.db.save_message"), \
         patch("app.services.db.update_session"), \
         patch("app.services.db.get_courier_for_client", return_value=None), \
         patch("app.services.db._client") as mock_db_client:

        # Simular insert en requests y request_events
        mock_table = MagicMock()
        mock_table.insert.return_value.execute.return_value.data = [{"id": "req-uuid-2"}]
        mock_db_client.table.return_value = mock_table

        from app.agent import process_turn
        reply = process_turn("test-chat-1", "Necesito una ruta para hoy")
        assert "registrado" in reply.lower()


# Test 3 & 10: cliente nuevo -> fase_7_escalado inmediato

def test_new_client_escalates_immediately():
    session = _make_session()
    ai_resp = _make_ai_response(
        "fase_7_escalado", "new_client",
        requires_handoff=True, handoff_area="operaciones"
    )

    with patch("app.services.db.get_or_create_session", return_value=session), \
         patch("app.services.db.get_recent_messages", return_value=_HISTORY_WITH_CONTEXT), \
         patch("app.services.ai.generate_turn", return_value=ai_resp), \
         patch("app.services.db.identify_client", return_value=None), \
         patch("app.services.db.save_message"), \
         patch("app.services.db.update_session"), \
         patch("app.services.db.create_request", return_value="req-uuid-3") as mock_create:

        from app.agent import process_turn
        process_turn("test-chat-1", "Quiero registrarme como cliente nuevo")

        mock_create.assert_called_once()
        call_args = mock_create.call_args[0]
        assert call_args[2]["intent"] == "new_client"
        assert call_args[2]["requires_handoff"] is True


# Test 9: gestión de pagos -> fase_7_escalado, handoff_area=contabilidad

def test_accounting_escalates_to_contabilidad():
    session = _make_session()
    ai_resp = _make_ai_response(
        "fase_7_escalado", "accounting",
        requires_handoff=True, handoff_area="contabilidad"
    )

    with patch("app.services.db.get_or_create_session", return_value=session), \
         patch("app.services.db.get_recent_messages", return_value=_HISTORY_WITH_CONTEXT), \
         patch("app.services.ai.generate_turn", return_value=ai_resp), \
         patch("app.services.db.identify_client", return_value=None), \
         patch("app.services.db.save_message"), \
         patch("app.services.db.update_session"), \
         patch("app.services.db.create_request", return_value="req-uuid-4") as mock_create:

        from app.agent import process_turn
        process_turn("test-chat-1", "Necesito hablar del pago de la factura")

        mock_create.assert_called_once()
        call_args = mock_create.call_args[0]
        assert call_args[2]["handoff_area"] == "contabilidad"


# Test 5: múltiples intenciones -> pending_intents guardados en sesión

def test_pending_intents_saved_to_session():
    session = _make_session()
    ai_resp = _make_ai_response(
        "fase_2_recogida_datos", "results",
        pending=["route_scheduling"]
    )

    captured_in_update = {}

    def fake_update(chat_id, response):
        captured_in_update.update(response["captured_fields"])

    with patch("app.services.db.get_or_create_session", return_value=session), \
         patch("app.services.db.get_recent_messages", return_value=_HISTORY_WITH_CONTEXT), \
         patch("app.services.ai.generate_turn", return_value=ai_resp), \
         patch("app.services.db.identify_client", return_value=None), \
         patch("app.services.db.save_message"), \
         patch("app.services.db.update_session", side_effect=fake_update), \
         patch("app.services.db.create_request"):

        from app.agent import process_turn
        process_turn("test-chat-1", "Quiero saber de Toby y también programar una ruta")

        assert captured_in_update.get("_pending_intents") == ["route_scheduling"]


# Test 8: conversación retomada -> no hay saludo redundante (R2)

def test_resumed_conversation_no_greeting():
    history = [
        {"role": "user", "content": "Hola, necesito una ruta"},
        {"role": "bot", "content": "¿De qué clínica es la solicitud?"},
    ]
    session = _make_session(phase="fase_2_recogida_datos", intent="route_scheduling")
    ai_resp = _make_ai_response("fase_2_recogida_datos", "route_scheduling")
    ai_resp["reply"] = "¿Qué tipo de análisis van a enviar?"

    with patch("app.services.db.get_or_create_session", return_value=session), \
         patch("app.services.db.get_recent_messages", return_value=history), \
         patch("app.services.db.get_catalog_context", return_value=""), \
         patch("app.services.ai.generate_turn", return_value=ai_resp) as mock_ai, \
         patch("app.services.db.identify_client", return_value=None), \
         patch("app.services.db.save_message"), \
         patch("app.services.db.update_session"), \
         patch("app.services.db.create_request"):

        from app.agent import process_turn
        reply = process_turn("test-chat-1", "Clínica San Marcos")

        # Verificar que el historial previo se pasó al modelo
        call_kwargs = mock_ai.call_args
        history_passed = call_kwargs[1].get("history") or call_kwargs[0][1]
        assert len(history_passed) == 2
        assert "Hola" in history_passed[0]["content"]


# Test 11: toda solicitud de ruta -> priority siempre "normal" en el request

def test_request_priority_always_normal():
    session = _make_session(client_id="client-uuid-5")
    ai_resp = _make_ai_response("fase_6_cierre", "route_scheduling")
    ai_resp["captured_fields"].update({
        "patient_name": "Toby",
        "species": "canino",
        "payment_method": "contraentrega",
    })

    courier = {"id": "courier-uuid-5", "name": "Pedro"}

    with patch("app.services.db.get_or_create_session", return_value=session), \
         patch("app.services.db.get_recent_messages", return_value=_HISTORY_WITH_CONTEXT), \
         patch("app.services.ai.generate_turn", return_value=ai_resp), \
         patch("app.services.db.identify_client", return_value=None), \
         patch("app.services.db.save_message"), \
         patch("app.services.db.update_session"), \
         patch("app.services.db.get_courier_for_client", return_value=courier), \
         patch("app.services.db.create_request", return_value="req-uuid-5") as mock_create:

        from app.agent import process_turn
        process_turn("test-chat-1", "Necesito una ruta")

        mock_create.assert_called_once()
        call_args = mock_create.call_args[0]
        assert call_args[2].get("captured_fields", {}).get("priority") != "urgent"


# Test adicional: primer turno devuelve bienvenida sin llamar IA

def test_first_turn_returns_welcome_without_ai_call():
    session = _make_session()

    with patch("app.services.db.get_or_create_session", return_value=session), \
         patch("app.services.db.get_recent_messages", return_value=[]), \
         patch("app.services.ai.generate_turn") as mock_ai, \
         patch("app.services.db.save_message") as mock_save:

        from app.agent import process_turn
        reply = process_turn("test-chat-1", "Hola")

        assert "Bienvenido a A3" in reply
        mock_ai.assert_not_called()
        assert mock_save.call_count == 2


# Test adicional: despedida en fase terminal cierra sin llamar IA

def test_terminal_farewell_skips_ai_and_returns_farewell():
    session = _make_session(phase="fase_6_cierre")

    with patch("app.services.db.get_or_create_session", return_value=session), \
         patch("app.services.db.get_recent_messages", return_value=_HISTORY_WITH_CONTEXT), \
         patch("app.services.ai.generate_turn") as mock_ai, \
         patch("app.services.db.update_session") as mock_update, \
         patch("app.services.db.create_request") as mock_create, \
         patch("app.services.db.save_message") as mock_save:

        from app.agent import process_turn
        reply = process_turn("test-chat-1", "gracias")

        assert "Hasta luego" in reply
        mock_ai.assert_not_called()
        mock_update.assert_not_called()
        mock_create.assert_not_called()
        assert mock_save.call_count == 2


def test_terminal_message_with_new_query_does_not_trigger_farewell():
    session = _make_session(phase="fase_7_escalado", intent="new_client", client_id="client-uuid-7")
    ai_resp = _make_ai_response("fase_7_escalado", "new_client", requires_handoff=True, handoff_area="operaciones")
    ai_resp["reply"] = "Claro, podés hacer otra consulta. Contame qué perfil te interesa."

    with patch("app.services.db.get_or_create_session", return_value=session), \
         patch("app.services.db.get_recent_messages", return_value=_HISTORY_WITH_CONTEXT), \
         patch("app.services.ai.generate_turn", return_value=ai_resp) as mock_ai, \
         patch("app.services.db.save_message"), \
         patch("app.services.db.update_session"), \
         patch("app.services.db.create_request") as mock_create:

        from app.agent import process_turn
        reply = process_turn("test-chat-1", "Dale puedo hacerte otra consulta")

        assert "otra consulta" in reply.lower()
        assert "hasta luego" not in reply.lower()
        mock_ai.assert_called_once()
        mock_create.assert_not_called()


def test_pending_route_intent_is_passed_after_results_turn():
    session = _make_session(
        phase="fase_2_recogida_datos",
        intent="results",
        captured={"_pending_intents": ["route_scheduling"]},
    )
    ai_resp = _make_ai_response("fase_2_recogida_datos", "route_scheduling")
    seen = {}

    def fake_generate_turn(*args, **kwargs):
        seen["pending_intents"] = kwargs.get("pending_intents")
        return ai_resp

    with patch("app.services.db.get_or_create_session", return_value=session), \
         patch("app.services.db.get_recent_messages", return_value=_HISTORY_WITH_CONTEXT), \
         patch("app.services.ai.generate_turn", side_effect=fake_generate_turn), \
         patch("app.services.db.identify_client", return_value=None), \
         patch("app.services.db.save_message"), \
         patch("app.services.db.update_session"), \
         patch("app.services.db.create_request") as mock_create:

        from app.agent import process_turn
        process_turn("test-chat-pending-route", "Listo, ahora programemos la ruta")

        assert seen["pending_intents"] == ["route_scheduling"]
        mock_create.assert_not_called()


def test_resume_after_handoff_with_corrected_nit_finds_client_without_creating_request():
    session = _make_session(
        phase="fase_7_escalado",
        intent="new_client",
        captured={
            "tax_id": "900296338",
            "clinic_name": None,
            "_asked_if_new_client": True,
            "_handoff_announced": True,
            "_client_not_found": True,
        },
    )
    ai_resp = _make_ai_response("fase_2_recogida_datos", "route_scheduling")
    ai_resp["captured_fields"].update({
        "tax_id": "79371045",
        "clinic_name": None,
        "pickup_address": None,
    })
    client = {
        "id": "client-after-handoff",
        "clinic_name": "Clínica Retomada",
        "address": "Calle 45 # 67-89",
    }

    with patch("app.services.db.get_or_create_session", return_value=session), \
         patch("app.services.db.get_recent_messages", return_value=_HISTORY_WITH_CONTEXT), \
         patch("app.services.db.get_catalog_context", return_value=""), \
         patch("app.services.ai.generate_turn", return_value=ai_resp), \
         patch("app.services.db.identify_client", return_value=client), \
         patch("app.services.db.link_client_to_session") as mock_link, \
         patch("app.services.db.save_message"), \
         patch("app.services.db.update_session") as mock_update, \
         patch("app.services.db.create_request") as mock_create:

        from app.agent import process_turn
        reply = process_turn("test-chat-after-handoff", "Ya me activaron, el NIT correcto es 79371045")

        assert "Clínica Retomada" in reply
        assert "Calle 45 # 67-89" in reply
        mock_link.assert_called_once_with("test-chat-after-handoff", "client-after-handoff")
        update_payload = mock_update.call_args[0][1]
        assert update_payload["captured_fields"].get("_client_found") is True
        mock_create.assert_not_called()


def test_new_route_after_closed_order_does_not_ask_for_identification_again():
    session = _make_session(
        phase="fase_6_cierre",
        intent="route_scheduling",
        client_id="client-repeat-route",
        captured={
            "clinic_name": "Clínica Test",
            "pickup_address": "Calle anterior",
            "exam_type": "hemograma",
            "patient_name": "Toby",
            "species": "canino",
            "payment_method": "contraentrega",
            "_client_found": True,
        },
    )
    ai_resp = _make_ai_response("fase_2_recogida_datos", "route_scheduling")
    ai_resp["reply"] = "¿Me indicás el NIT o el nombre de la veterinaria para ver si está registrada?"
    ai_resp["captured_fields"].update({
        "clinic_name": "Clínica Test",
        "tax_id": None,
        "pickup_address": None,
        "exam_type": None,
        "patient_name": None,
        "species": None,
        "payment_method": None,
    })

    with patch("app.services.db.get_or_create_session", return_value=session), \
         patch("app.services.db.get_recent_messages", return_value=_HISTORY_WITH_CONTEXT), \
         patch("app.services.ai.generate_turn", return_value=ai_resp), \
         patch("app.services.db.save_message"), \
         patch("app.services.db.update_session") as mock_update, \
         patch("app.services.db.create_request") as mock_create:

        from app.agent import process_turn
        reply = process_turn("test-chat-repeat-route", "Necesito otra ruta")

        assert "nit" not in reply.lower()
        assert "veterinaria" not in reply.lower()
        assert "dirección" in reply.lower() or "direccion" in reply.lower() or "análisis" in reply.lower() or "analisis" in reply.lower()
        update_payload = mock_update.call_args[0][1]
        assert update_payload["captured_fields"].get("_client_found") is True
        mock_create.assert_not_called()


# Test adicional: alerta de bucle se inyecta al contexto de IA

def test_force_close_hint_is_passed_to_ai_after_two_affirmatives():
    session = _make_session(phase="fase_2_recogida_datos")
    history = [
        {"role": "user", "content": "si"},
        {"role": "bot", "content": "ok"},
        {"role": "user", "content": "perfecto"},
        {"role": "bot", "content": "dale"},
    ]
    ai_resp = _make_ai_response("fase_2_recogida_datos", "route_scheduling")

    seen_hint = {"value": None}

    def fake_generate_turn(*args, **kwargs):
        session_param = kwargs.get("session") if kwargs else args[0]
        seen_hint["value"] = session_param.get("_force_close_hint")
        return ai_resp

    with patch("app.services.db.get_or_create_session", return_value=session), \
         patch("app.services.db.get_recent_messages", return_value=history), \
         patch("app.services.ai.generate_turn", side_effect=fake_generate_turn), \
         patch("app.services.db.identify_client", return_value=None), \
         patch("app.services.db.save_message"), \
         patch("app.services.db.update_session"), \
         patch("app.services.db.create_request"):

        from app.agent import process_turn
        process_turn("test-chat-1", "ok")

        assert seen_hint["value"] is not None
        assert "ALERTA DE BUCLE" in seen_hint["value"]


# Test adicional: cancellation no debe crear solicitud

def test_cancellation_message_mode_does_not_create_request():
    session = _make_session(phase="fase_2_recogida_datos", intent="route_scheduling")
    ai_resp = _make_ai_response("fase_2_recogida_datos", "route_scheduling")
    ai_resp["message_mode"] = "cancellation"

    with patch("app.services.db.get_or_create_session", return_value=session), \
         patch("app.services.db.get_recent_messages", return_value=_HISTORY_WITH_CONTEXT), \
         patch("app.services.db.get_catalog_context", return_value=""), \
         patch("app.services.ai.generate_turn", return_value=ai_resp), \
         patch("app.services.db.identify_client", return_value=None), \
         patch("app.services.db.save_message"), \
         patch("app.services.db.update_session"), \
         patch("app.services.db.create_request") as mock_create:

        from app.agent import process_turn
        reply = process_turn("test-chat-1", "Quiero cancelar")

        assert reply == "respuesta de prueba"
        mock_create.assert_not_called()


def test_terminal_cancellation_does_not_create_route_request():
    session = _make_session(
        phase="fase_2_recogida_datos",
        intent="route_scheduling",
        client_id="client-cancel-route",
        captured={
            "clinic_name": "Clínica Test",
            "pickup_address": "Calle 1",
            "exam_type": "hemograma",
            "patient_name": "Toby",
            "species": "canino",
            "payment_method": "contraentrega",
            "_client_found": True,
        },
    )
    ai_resp = _make_ai_response("fase_6_cierre", "route_scheduling")
    ai_resp["message_mode"] = "cancellation"
    ai_resp["reply"] = "Entendido, cancelé la solicitud en curso."
    ai_resp["captured_fields"].update({
        "clinic_name": "Clínica Test",
        "pickup_address": "Calle 1",
        "exam_type": "hemograma",
        "patient_name": "Toby",
        "species": "canino",
        "payment_method": "contraentrega",
    })

    with patch("app.services.db.get_or_create_session", return_value=session), \
         patch("app.services.db.get_recent_messages", return_value=_HISTORY_WITH_CONTEXT), \
         patch("app.services.db.get_catalog_context", return_value=""), \
         patch("app.services.ai.generate_turn", return_value=ai_resp), \
         patch("app.services.db.identify_client", return_value=None), \
         patch("app.services.db.get_courier_for_client", return_value=None), \
         patch("app.services.db.save_message"), \
         patch("app.services.db.update_session") as mock_update, \
         patch("app.services.db.create_request") as mock_create:

        from app.agent import process_turn
        reply = process_turn("test-chat-cancel-route", "Mejor cancela todo")

        assert "cancel" in reply.lower()
        assert mock_update.call_args[0][1]["message_mode"] == "cancellation"
        mock_create.assert_not_called()


# Test 6: repite sin dar dato -> ofrecer opciones concretas

def test_user_repeats_without_data_gets_concrete_options():
    history = [
        {"role": "user", "content": "Necesito una ruta"},
        {"role": "bot", "content": "¿Me indicás el NIT o nombre de la veterinaria?"},
        {"role": "user", "content": "No se"},
        {"role": "bot", "content": "¿Me indicás el NIT o nombre de la veterinaria?"},
    ]
    session = _make_session(phase="fase_2_recogida_datos", intent="route_scheduling")
    ai_resp = _make_ai_response("fase_2_recogida_datos", "route_scheduling")
    ai_resp["reply"] = (
        "Te ayudo con eso. Podemos hacerlo de dos formas: "
        "1) me compartís el NIT, o 2) me das el nombre exacto de la veterinaria."
    )

    with patch("app.services.db.get_or_create_session", return_value=session), \
         patch("app.services.db.get_recent_messages", return_value=history), \
         patch("app.services.db.get_catalog_context", return_value=""), \
         patch("app.services.ai.generate_turn", return_value=ai_resp), \
         patch("app.services.db.identify_client", return_value=None), \
         patch("app.services.db.save_message"), \
         patch("app.services.db.update_session"), \
         patch("app.services.db.create_request") as mock_create:

        from app.agent import process_turn
        reply = process_turn("test-chat-1", "No tengo ese dato")

        assert "1)" in reply
        assert "2)" in reply
        assert "nit" in reply.lower()
        assert "nombre" in reply.lower()
        mock_create.assert_not_called()


def test_repeated_identification_question_is_rephrased_with_options():
    repeated_question = "¿Me indicás el NIT o el nombre de la veterinaria para ver si está registrada?"
    history = [
        {"role": "user", "content": "Necesito una ruta"},
        {"role": "bot", "content": repeated_question},
        {"role": "user", "content": "No tengo el dato exacto"},
    ]
    session = _make_session(phase="fase_2_recogida_datos", intent="route_scheduling")
    ai_resp = _make_ai_response("fase_2_recogida_datos", "route_scheduling")
    ai_resp["reply"] = repeated_question
    ai_resp["captured_fields"].update({"clinic_name": None, "tax_id": None})

    with patch("app.services.db.get_or_create_session", return_value=session), \
         patch("app.services.db.get_recent_messages", return_value=history), \
         patch("app.services.db.get_catalog_context", return_value=""), \
         patch("app.services.ai.generate_turn", return_value=ai_resp), \
         patch("app.services.db.identify_client", return_value=None), \
         patch("app.services.db.save_message"), \
         patch("app.services.db.update_session") as mock_update, \
         patch("app.services.db.create_request") as mock_create:

        from app.agent import process_turn
        reply = process_turn("test-chat-1", "No tengo el dato exacto")

        assert reply != repeated_question
        assert "1)" in reply
        assert "2)" in reply
        assert "nit" in reply.lower()
        assert "nombre" in reply.lower()
        assert mock_update.call_args[0][1]["reply"] == reply
        mock_create.assert_not_called()


# Regresión: no repetir escalado cuando ya fue anunciado

def test_no_repeat_handoff_message_when_already_announced_and_user_asks_profiles():
    session = _make_session(
        phase="fase_7_escalado",
        intent="new_client",
        captured={
            "tax_id": "22778262",
            "clinic_name": None,
            "_asked_if_new_client": True,
            "_handoff_announced": True,
            "_client_not_found": True,
        },
    )
    ai_resp = _make_ai_response("fase_7_escalado", "new_client", requires_handoff=True, handoff_area="operaciones")
    ai_resp["reply"] = "Claro. Tenemos perfiles de hematología, química sanguínea y hormonales."
    ai_resp["captured_fields"]["tax_id"] = "22778262"

    with patch("app.services.db.get_or_create_session", return_value=session), \
         patch("app.services.db.get_recent_messages", return_value=_HISTORY_WITH_CONTEXT), \
         patch("app.services.ai.generate_turn", return_value=ai_resp), \
         patch("app.services.db.identify_client", return_value=None), \
         patch("app.services.db.save_message"), \
         patch("app.services.db.update_session") as mock_update, \
         patch("app.services.db.create_request") as mock_create:

        from app.agent import process_turn
        reply = process_turn("test-chat-1", "me podrias informar un poco de los perfiles")

        assert "perfiles" in reply.lower()
        assert "no encuentro la veterinaria" not in reply.lower()
        mock_create.assert_not_called()

        update_payload = mock_update.call_args[0][1]
        assert update_payload["captured_fields"].get("_handoff_announced") is True


# Regresión: primer escalado marca bandera de anuncio

def test_first_handoff_sets_announced_flag():
    session = _make_session(
        phase="fase_2_recogida_datos",
        intent="route_scheduling",
        captured={"_asked_if_new_client": True},
    )
    ai_resp = _make_ai_response("fase_2_recogida_datos", "route_scheduling")
    ai_resp["captured_fields"]["tax_id"] = "22778262"

    with patch("app.services.db.get_or_create_session", return_value=session), \
         patch("app.services.db.get_recent_messages", return_value=_HISTORY_WITH_CONTEXT), \
         patch("app.services.db.get_catalog_context", return_value=""), \
         patch("app.services.ai.generate_turn", return_value=ai_resp), \
         patch("app.services.db.identify_client", return_value=None), \
         patch("app.services.db.save_message"), \
         patch("app.services.db.update_session") as mock_update, \
         patch("app.services.db.create_request", return_value="req-uuid-handoff") as mock_create:

        from app.agent import process_turn
        reply = process_turn("test-chat-1", "si soy cliente nuevo")

        assert "cliente" in reply.lower()
        mock_create.assert_called_once()

        update_payload = mock_update.call_args[0][1]
        assert update_payload["phase"] == "fase_7_escalado"
        assert update_payload["captured_fields"].get("_handoff_announced") is True


def test_accounting_handoff_does_not_ask_followup_question():
    session = _make_session(phase="fase_2_recogida_datos", intent="accounting")
    ai_resp = _make_ai_response("fase_7_escalado", "accounting", requires_handoff=True, handoff_area="contabilidad")
    ai_resp["reply"] = (
        "Perfecto, eso lo maneja el equipo de contabilidad. "
        "¿Me confirmás el número de factura o el valor a pagar?"
    )

    with patch("app.services.db.get_or_create_session", return_value=session), \
         patch("app.services.db.get_recent_messages", return_value=_HISTORY_WITH_CONTEXT), \
         patch("app.services.ai.generate_turn", return_value=ai_resp), \
         patch("app.services.db.identify_client", return_value=None), \
         patch("app.services.db.save_message"), \
         patch("app.services.db.update_session") as mock_update, \
         patch("app.services.db.create_request") as mock_create:

        from app.agent import process_turn
        reply = process_turn("test-chat-1", "Tengo una pregunta de pago")

        assert "contabilidad" in reply.lower()
        assert "?" not in reply
        update_payload = mock_update.call_args[0][1]
        assert update_payload["requires_handoff"] is True
        assert update_payload["phase"] == "fase_7_escalado"
        mock_create.assert_called_once()


def test_non_handoff_reply_is_limited_to_one_question():
    session = _make_session(phase="fase_2_recogida_datos", intent="route_scheduling", client_id="client-uuid-8")
    ai_resp = _make_ai_response("fase_2_recogida_datos", "route_scheduling")
    ai_resp["reply"] = "¿Me compartís el NIT? ¿Y también el nombre de la veterinaria?"

    with patch("app.services.db.get_or_create_session", return_value=session), \
         patch("app.services.db.get_recent_messages", return_value=_HISTORY_WITH_CONTEXT), \
         patch("app.services.db.get_catalog_context", return_value=""), \
         patch("app.services.ai.generate_turn", return_value=ai_resp), \
         patch("app.services.db.save_message"), \
         patch("app.services.db.update_session") as mock_update, \
         patch("app.services.db.create_request") as mock_create:

        from app.agent import process_turn
        reply = process_turn("test-chat-1", "Necesito programar una ruta")

        assert reply.count("?") == 1
        update_payload = mock_update.call_args[0][1]
        assert update_payload["reply"].count("?") == 1
        mock_create.assert_not_called()


def test_client_found_reply_uses_registered_address_not_placeholder():
    session = _make_session(phase="fase_2_recogida_datos", intent="route_scheduling")
    first_ai_resp = _make_ai_response("fase_2_recogida_datos", "route_scheduling")
    first_ai_resp["captured_fields"].update({
        "clinic_name": None,
        "tax_id": "79371045",
        "pickup_address": None,
    })
    second_ai_resp = _make_ai_response("fase_2_recogida_datos", "route_scheduling")
    second_ai_resp["reply"] = "Perfecto. Tenemos como domicilio de retiro: {direccion}. ¿Es correcta?"

    client = {
        "id": "client-uuid-address",
        "clinic_name": "Clínica San Marcos",
        "address": "Calle 123 # 45-67",
    }

    with patch("app.services.db.get_or_create_session", return_value=session), \
         patch("app.services.db.get_recent_messages", return_value=_HISTORY_WITH_CONTEXT), \
         patch("app.services.db.get_catalog_context", return_value=""), \
         patch("app.services.ai.generate_turn", side_effect=[first_ai_resp, second_ai_resp]), \
         patch("app.services.db.identify_client", return_value=client), \
         patch("app.services.db.link_client_to_session"), \
         patch("app.services.db.save_message"), \
         patch("app.services.db.update_session") as mock_update, \
         patch("app.services.db.create_request") as mock_create:

        from app.agent import process_turn
        reply = process_turn("test-chat-1", "79371045")

        assert "Calle 123 # 45-67" in reply
        assert "{direccion}" not in reply
        update_payload = mock_update.call_args[0][1]
        assert update_payload["captured_fields"]["pickup_address"] == "Calle 123 # 45-67"
        mock_create.assert_not_called()


def test_second_unmatched_lookup_does_not_escalate_without_new_client_confirmation():
    session = _make_session(
        phase="fase_2_recogida_datos",
        intent="route_scheduling",
        captured={
            "tax_id": "900296338",
            "clinic_name": None,
            "_asked_if_new_client": True,
            "_client_not_found": True,
        },
    )
    ai_resp = _make_ai_response("fase_2_recogida_datos", "route_scheduling")
    ai_resp["captured_fields"].update({
        "tax_id": "53090826",
        "clinic_name": None,
    })

    with patch("app.services.db.get_or_create_session", return_value=session), \
         patch("app.services.db.get_recent_messages", return_value=_HISTORY_WITH_CONTEXT), \
         patch("app.services.db.get_catalog_context", return_value=""), \
         patch("app.services.ai.generate_turn", return_value=ai_resp), \
         patch("app.services.db.identify_client", return_value=None), \
         patch("app.services.db.save_message"), \
         patch("app.services.db.update_session") as mock_update, \
         patch("app.services.db.create_request") as mock_create:

        from app.agent import process_turn
        reply = process_turn("test-chat-1", "53090826")

        assert "cliente nuevo" in reply.lower()
        assert "confirm" in reply.lower()
        update_payload = mock_update.call_args[0][1]
        assert update_payload["phase"] == "fase_2_recogida_datos"
        assert update_payload["requires_handoff"] is False
        assert update_payload["captured_fields"].get("_handoff_announced") is not True
        mock_create.assert_not_called()


def test_corrected_nit_after_failed_lookup_finds_client_without_escalating():
    session = _make_session(
        phase="fase_2_recogida_datos",
        intent="route_scheduling",
        captured={
            "tax_id": "900296338",
            "clinic_name": None,
            "_asked_if_new_client": True,
            "_client_not_found": True,
        },
    )
    ai_resp = _make_ai_response("fase_2_recogida_datos", "route_scheduling")
    ai_resp["captured_fields"].update({
        "tax_id": "79371045",
        "clinic_name": None,
        "pickup_address": None,
    })
    client = {
        "id": "client-corrected-nit",
        "clinic_name": "Clínica San Marcos",
        "address": "Carrera 10 # 20-30",
    }

    with patch("app.services.db.get_or_create_session", return_value=session), \
         patch("app.services.db.get_recent_messages", return_value=_HISTORY_WITH_CONTEXT), \
         patch("app.services.db.get_catalog_context", return_value=""), \
         patch("app.services.ai.generate_turn", return_value=ai_resp), \
         patch("app.services.db.identify_client", return_value=client) as mock_identify, \
         patch("app.services.db.link_client_to_session") as mock_link, \
         patch("app.services.db.save_message"), \
         patch("app.services.db.update_session") as mock_update, \
         patch("app.services.db.create_request") as mock_create:

        from app.agent import process_turn
        reply = process_turn("test-chat-1", "Me equivoqué, es 79371045")

        assert "Carrera 10 # 20-30" in reply
        assert "cliente nuevo" not in reply.lower()
        mock_identify.assert_called_once_with(name=None, tax_id="79371045")
        mock_link.assert_called_once_with("test-chat-1", "client-corrected-nit")
        update_payload = mock_update.call_args[0][1]
        assert update_payload["requires_handoff"] is False
        assert update_payload["captured_fields"].get("_client_found") is True
        assert update_payload["captured_fields"].get("_client_not_found") is False
        mock_create.assert_not_called()


@pytest.mark.parametrize(
    "user_message, expected_name, expected_tax_id",
    [
        ("Canes y cia", "Canes y cia", None),
        ("NIT 79371045", None, "79371045"),
    ],
)
def test_retry_after_poisoned_client_not_found_uses_new_identifier(user_message, expected_name, expected_tax_id):
    session = _make_session(
        phase="fase_7_escalado",
        intent="new_client",
        captured={
            "clinic_name": "Dr Sandoval",
            "tax_id": None,
            "_asked_if_new_client": True,
            "_handoff_announced": True,
            "_client_not_found": True,
            "_pending_intents": ["route_scheduling"],
        },
    )
    ai_resp = _make_ai_response("fase_2_recogida_datos", "route_scheduling")
    ai_resp["captured_fields"].update({
        "clinic_name": "Dr Sandoval",
        "tax_id": None,
        "pickup_address": None,
    })
    client = {
        "id": "client-retry-identifier",
        "clinic_name": "Canes y Cia",
        "address": "Calle 12 # 34-56",
    }

    with patch("app.services.db.get_or_create_session", return_value=session), \
         patch("app.services.db.get_recent_messages", return_value=_HISTORY_WITH_CONTEXT), \
         patch("app.services.ai.generate_turn", return_value=ai_resp), \
         patch("app.services.db.identify_client", return_value=client) as mock_identify, \
         patch("app.services.db.link_client_to_session") as mock_link, \
         patch("app.services.db.save_message"), \
         patch("app.services.db.update_session") as mock_update, \
         patch("app.services.db.create_request") as mock_create:

        from app.agent import process_turn
        reply = process_turn("test-chat-poisoned-client", user_message)

        assert "Canes y Cia" in reply
        assert "Calle 12 # 34-56" in reply
        mock_identify.assert_called_once_with(name=expected_name, tax_id=expected_tax_id)
        mock_link.assert_called_once_with("test-chat-poisoned-client", "client-retry-identifier")
        update_payload = mock_update.call_args[0][1]
        assert update_payload["captured_fields"].get("_client_found") is True
        assert update_payload["captured_fields"].get("_client_not_found") is False
        mock_create.assert_not_called()


def test_approximate_clinic_name_can_identify_client_when_user_lacks_nit():
    session = _make_session(phase="fase_2_recogida_datos", intent="route_scheduling")
    ai_resp = _make_ai_response("fase_2_recogida_datos", "route_scheduling")
    ai_resp["captured_fields"].update({
        "tax_id": None,
        "clinic_name": "Agromascotas",
        "pickup_address": None,
    })
    client = {
        "id": "client-approx-name",
        "clinic_name": "Centro Veterinario Agromascotas SAS",
        "address": "Calle 80 # 12-34",
    }

    with patch("app.services.db.get_or_create_session", return_value=session), \
         patch("app.services.db.get_recent_messages", return_value=_HISTORY_WITH_CONTEXT), \
         patch("app.services.db.get_catalog_context", return_value=""), \
         patch("app.services.ai.generate_turn", return_value=ai_resp), \
         patch("app.services.db.identify_client", return_value=client) as mock_identify, \
         patch("app.services.db.link_client_to_session"), \
         patch("app.services.db.save_message"), \
         patch("app.services.db.update_session") as mock_update, \
         patch("app.services.db.create_request") as mock_create:

        from app.agent import process_turn
        reply = process_turn("test-chat-1", "No tengo el NIT, creo que es Agromascotas")

        assert "Centro Veterinario Agromascotas SAS" in reply
        assert "Calle 80 # 12-34" in reply
        mock_identify.assert_called_once_with(name="Agromascotas", tax_id=None)
        update_payload = mock_update.call_args[0][1]
        assert update_payload["captured_fields"]["clinic_name"] == "Agromascotas"
        assert update_payload["captured_fields"].get("_client_display_name") == "Centro Veterinario Agromascotas SAS"
        mock_create.assert_not_called()


def test_user_denies_new_client_keeps_identification_open():
    session = _make_session(
        phase="fase_2_recogida_datos",
        intent="route_scheduling",
        captured={
            "tax_id": "900296338",
            "clinic_name": None,
            "_asked_if_new_client": True,
            "_client_not_found": True,
        },
    )
    ai_resp = _make_ai_response("fase_2_recogida_datos", "route_scheduling")
    ai_resp["captured_fields"].update({
        "tax_id": None,
        "clinic_name": "Veterinaria Mis Perritos",
    })

    with patch("app.services.db.get_or_create_session", return_value=session), \
         patch("app.services.db.get_recent_messages", return_value=_HISTORY_WITH_CONTEXT), \
         patch("app.services.db.get_catalog_context", return_value=""), \
         patch("app.services.ai.generate_turn", return_value=ai_resp), \
         patch("app.services.db.identify_client", return_value=None), \
         patch("app.services.db.save_message"), \
         patch("app.services.db.update_session") as mock_update, \
         patch("app.services.db.create_request") as mock_create:

        from app.agent import process_turn
        reply = process_turn("test-chat-1", "No, ya somos clientes. Es Veterinaria Mis Perritos")

        assert "cliente nuevo" in reply.lower()
        assert "confirm" in reply.lower()
        update_payload = mock_update.call_args[0][1]
        assert update_payload["phase"] == "fase_2_recogida_datos"
        assert update_payload["requires_handoff"] is False
        assert update_payload["captured_fields"].get("_handoff_announced") is not True
        mock_create.assert_not_called()


def test_affirmation_plus_new_nit_is_not_treated_as_new_client_confirmation():
    session = _make_session(
        phase="fase_2_recogida_datos",
        intent="route_scheduling",
        captured={
            "tax_id": "900296338",
            "clinic_name": None,
            "_asked_if_new_client": True,
            "_client_not_found": True,
        },
    )
    ai_resp = _make_ai_response("fase_2_recogida_datos", "route_scheduling")
    ai_resp["captured_fields"].update({
        "tax_id": "53090826",
        "clinic_name": None,
    })

    with patch("app.services.db.get_or_create_session", return_value=session), \
         patch("app.services.db.get_recent_messages", return_value=_HISTORY_WITH_CONTEXT), \
         patch("app.services.db.get_catalog_context", return_value=""), \
         patch("app.services.ai.generate_turn", return_value=ai_resp), \
         patch("app.services.db.identify_client", return_value=None), \
         patch("app.services.db.save_message"), \
         patch("app.services.db.update_session") as mock_update, \
         patch("app.services.db.create_request") as mock_create:

        from app.agent import process_turn
        reply = process_turn("test-chat-1", "Sí, prueba con 53090826")

        assert "cliente nuevo" in reply.lower()
        update_payload = mock_update.call_args[0][1]
        assert update_payload["phase"] == "fase_2_recogida_datos"
        assert update_payload["requires_handoff"] is False
        assert update_payload["captured_fields"].get("_handoff_announced") is not True
        mock_create.assert_not_called()


def test_route_closure_requires_payment_question_before_finish():
    session = _make_session(phase="fase_2_recogida_datos", intent="route_scheduling", client_id="client-uuid-9")
    ai_resp = _make_ai_response("fase_6_cierre", "route_scheduling")
    ai_resp["captured_fields"].update({
        "clinic_name": "Clínica Test",
        "pickup_address": "Calle 1",
        "exam_type": "hemograma",
        "patient_name": "Toby",
        "species": "canino",
        "payment_method": None,
    })

    with patch("app.services.db.get_or_create_session", return_value=session), \
         patch("app.services.db.get_recent_messages", return_value=_HISTORY_WITH_CONTEXT), \
         patch("app.services.db.get_catalog_context", return_value=""), \
         patch("app.services.ai.generate_turn", return_value=ai_resp), \
         patch("app.services.db.identify_client", return_value=None), \
         patch("app.services.db.save_message"), \
         patch("app.services.db.update_session") as mock_update, \
         patch("app.services.db.create_request") as mock_create:

        from app.agent import process_turn
        reply = process_turn("test-chat-1", "Todo bien")

        assert "contado" in reply.lower()
        assert "contraentrega" in reply.lower()
        update_payload = mock_update.call_args[0][1]
        assert update_payload["phase"] == "fase_2_recogida_datos"
        assert update_payload["captured_fields"].get("payment_method") is None
        mock_create.assert_not_called()


def test_route_with_contado_sets_accounting_handoff_and_creates_request():
    session = _make_session(phase="fase_2_recogida_datos", intent="route_scheduling", client_id="client-uuid-10")
    ai_resp = _make_ai_response("fase_6_cierre", "route_scheduling", requires_handoff=True, handoff_area=None)
    ai_resp["reply"] = "Perfecto, dejamos pago de contado. ¿Algo más?"
    ai_resp["captured_fields"].update({
        "clinic_name": "Clínica Test",
        "pickup_address": "Calle 1",
        "exam_type": "hemograma",
        "patient_name": "Toby",
        "species": "canino",
        "payment_method": "contado",
    })

    with patch("app.services.db.get_or_create_session", return_value=session), \
         patch("app.services.db.get_recent_messages", return_value=_HISTORY_WITH_CONTEXT), \
         patch("app.services.db.get_catalog_context", return_value=""), \
         patch("app.services.ai.generate_turn", return_value=ai_resp), \
         patch("app.services.db.identify_client", return_value=None), \
         patch("app.services.db.get_courier_for_client", return_value=None), \
         patch("app.services.db.save_message"), \
         patch("app.services.db.update_session") as mock_update, \
         patch("app.services.db.create_request", return_value="req-uuid-pay-1") as mock_create:

        from app.agent import process_turn
        reply = process_turn("test-chat-1", "Pago de contado")

        assert "?" not in reply
        update_payload = mock_update.call_args[0][1]
        assert update_payload["phase"] == "fase_7_escalado"
        assert update_payload["handoff_area"] == "contabilidad"
        mock_create.assert_called_once()
        request_payload = mock_create.call_args[0][2]
        assert request_payload["captured_fields"].get("payment_method") == "contado"


def test_route_with_contraentrega_closes_without_handoff():
    session = _make_session(phase="fase_2_recogida_datos", intent="route_scheduling", client_id="client-uuid-11")
    ai_resp = _make_ai_response("fase_6_cierre", "route_scheduling")
    ai_resp["captured_fields"].update({
        "clinic_name": "Clínica Test",
        "pickup_address": "Calle 1",
        "exam_type": "hemograma",
        "patient_name": "Toby",
        "species": "canino",
        "payment_method": "contraentrega",
    })

    with patch("app.services.db.get_or_create_session", return_value=session), \
         patch("app.services.db.get_recent_messages", return_value=_HISTORY_WITH_CONTEXT), \
         patch("app.services.db.get_catalog_context", return_value=""), \
         patch("app.services.ai.generate_turn", return_value=ai_resp), \
         patch("app.services.db.identify_client", return_value=None), \
         patch("app.services.db.get_courier_for_client", return_value=None), \
         patch("app.services.db.save_message"), \
         patch("app.services.db.update_session") as mock_update, \
         patch("app.services.db.create_request", return_value="req-uuid-pay-2") as mock_create:

        from app.agent import process_turn
        process_turn("test-chat-1", "Pago contraentrega")

        update_payload = mock_update.call_args[0][1]
        assert update_payload["phase"] == "fase_6_cierre"
        assert update_payload["requires_handoff"] is False
        mock_create.assert_called_once()
        request_payload = mock_create.call_args[0][2]
        assert request_payload["captured_fields"].get("payment_method") == "contraentrega"


def test_corrected_patient_name_is_used_when_closing_route():
    session = _make_session(
        phase="fase_2_recogida_datos",
        intent="route_scheduling",
        client_id="client-uuid-correction-1",
        captured={
            "clinic_name": "Clínica Test",
            "pickup_address": "Calle 1",
            "exam_type": "hemograma",
            "patient_name": "Toby",
            "species": "canino",
            "payment_method": "contraentrega",
            "_client_found": True,
        },
    )
    ai_resp = _make_ai_response("fase_6_cierre", "route_scheduling")
    ai_resp["captured_fields"].update({
        "clinic_name": "Clínica Test",
        "pickup_address": "Calle 1",
        "exam_type": "hemograma",
        "patient_name": "Luna",
        "species": "canino",
        "payment_method": "contraentrega",
    })

    with patch("app.services.db.get_or_create_session", return_value=session), \
         patch("app.services.db.get_recent_messages", return_value=_HISTORY_WITH_CONTEXT), \
         patch("app.services.db.get_catalog_context", return_value=""), \
         patch("app.services.ai.generate_turn", return_value=ai_resp), \
         patch("app.services.db.identify_client", return_value=None), \
         patch("app.services.db.get_courier_for_client", return_value=None), \
         patch("app.services.db.save_message"), \
         patch("app.services.db.update_session"), \
         patch("app.services.db.create_request", return_value="req-correction-1") as mock_create:

        from app.agent import process_turn
        reply = process_turn("test-chat-1", "Me equivoqué, el paciente es Luna")

        assert "Luna" in reply
        assert "Toby" not in reply
        request_payload = mock_create.call_args[0][2]
        assert request_payload["captured_fields"]["patient_name"] == "Luna"


def test_corrected_pickup_address_is_used_when_closing_route():
    session = _make_session(
        phase="fase_2_recogida_datos",
        intent="route_scheduling",
        client_id="client-uuid-correction-2",
        captured={
            "clinic_name": "Clínica Test",
            "pickup_address": "Calle vieja",
            "exam_type": "hemograma",
            "patient_name": "Toby",
            "species": "canino",
            "payment_method": "contraentrega",
            "_client_found": True,
        },
    )
    ai_resp = _make_ai_response("fase_6_cierre", "route_scheduling")
    ai_resp["captured_fields"].update({
        "clinic_name": "Clínica Test",
        "pickup_address": "Calle nueva # 12-34",
        "exam_type": "hemograma",
        "patient_name": "Toby",
        "species": "canino",
        "payment_method": "contraentrega",
    })

    with patch("app.services.db.get_or_create_session", return_value=session), \
         patch("app.services.db.get_recent_messages", return_value=_HISTORY_WITH_CONTEXT), \
         patch("app.services.db.get_catalog_context", return_value=""), \
         patch("app.services.ai.generate_turn", return_value=ai_resp), \
         patch("app.services.db.identify_client", return_value=None), \
         patch("app.services.db.get_courier_for_client", return_value=None), \
         patch("app.services.db.save_message"), \
         patch("app.services.db.update_session"), \
         patch("app.services.db.create_request", return_value="req-correction-2") as mock_create:

        from app.agent import process_turn
        reply = process_turn("test-chat-1", "No, la dirección correcta es Calle nueva # 12-34")

        assert "Calle nueva # 12-34" in reply
        assert "Calle vieja" not in reply
        request_payload = mock_create.call_args[0][2]
        assert request_payload["captured_fields"]["pickup_address"] == "Calle nueva # 12-34"


def test_payment_correction_to_contraentrega_avoids_accounting_handoff():
    session = _make_session(
        phase="fase_2_recogida_datos",
        intent="route_scheduling",
        client_id="client-uuid-correction-3",
        captured={
            "clinic_name": "Clínica Test",
            "pickup_address": "Calle 1",
            "exam_type": "hemograma",
            "patient_name": "Toby",
            "species": "canino",
            "payment_method": "contado",
            "_client_found": True,
        },
    )
    ai_resp = _make_ai_response("fase_6_cierre", "route_scheduling")
    ai_resp["captured_fields"].update({
        "clinic_name": "Clínica Test",
        "pickup_address": "Calle 1",
        "exam_type": "hemograma",
        "patient_name": "Toby",
        "species": "canino",
        "payment_method": "contraentrega",
    })

    with patch("app.services.db.get_or_create_session", return_value=session), \
         patch("app.services.db.get_recent_messages", return_value=_HISTORY_WITH_CONTEXT), \
         patch("app.services.db.get_catalog_context", return_value=""), \
         patch("app.services.ai.generate_turn", return_value=ai_resp), \
         patch("app.services.db.identify_client", return_value=None), \
         patch("app.services.db.get_courier_for_client", return_value=None), \
         patch("app.services.db.save_message"), \
         patch("app.services.db.update_session") as mock_update, \
         patch("app.services.db.create_request", return_value="req-correction-3") as mock_create:

        from app.agent import process_turn
        process_turn("test-chat-1", "Mejor contraentrega")

        update_payload = mock_update.call_args[0][1]
        assert update_payload["requires_handoff"] is False
        assert update_payload["handoff_area"] is None
        request_payload = mock_create.call_args[0][2]
        assert request_payload["captured_fields"]["payment_method"] == "contraentrega"


def test_repeated_analysis_question_is_rephrased_with_catalog_option():
    repeated_question = "¿Qué tipo de análisis o perfil necesitás?"
    history = [
        {"role": "user", "content": "Necesito una ruta"},
        {"role": "bot", "content": repeated_question},
        {"role": "user", "content": "No sé cuál pedir"},
    ]
    session = _make_session(phase="fase_2_recogida_datos", intent="route_scheduling", client_id="client-uuid-analysis")
    ai_resp = _make_ai_response("fase_2_recogida_datos", "route_scheduling")
    ai_resp["reply"] = repeated_question
    ai_resp["captured_fields"].update({"exam_type": None})

    with patch("app.services.db.get_or_create_session", return_value=session), \
         patch("app.services.db.get_recent_messages", return_value=history), \
         patch("app.services.db.get_catalog_context", return_value=""), \
         patch("app.services.ai.generate_turn", return_value=ai_resp), \
         patch("app.services.db.identify_client", return_value=None), \
         patch("app.services.db.save_message"), \
         patch("app.services.db.update_session") as mock_update, \
         patch("app.services.db.create_request") as mock_create:

        from app.agent import process_turn
        reply = process_turn("test-chat-1", "No sé cuál pedir")

        assert reply != repeated_question
        assert "análisis" in reply.lower() or "analisis" in reply.lower()
        assert "catálogo" in reply.lower() or "catalogo" in reply.lower()
        assert mock_update.call_args[0][1]["reply"] == reply
        mock_create.assert_not_called()


def test_ambiguous_analysis_choice_cannot_close_route_without_exam_type():
    session = _make_session(
        phase="fase_2_recogida_datos",
        intent="route_scheduling",
        client_id="client-ambiguous-analysis",
        captured={
            "clinic_name": "Clínica Test",
            "pickup_address": "Calle 1",
            "_client_found": True,
        },
    )
    ai_resp = _make_ai_response("fase_6_cierre", "route_scheduling")
    ai_resp["reply"] = "Listo, dejamos el mismo análisis."
    ai_resp["captured_fields"].update({
        "clinic_name": "Clínica Test",
        "pickup_address": "Calle 1",
        "exam_type": None,
        "patient_name": "Toby",
        "species": "canino",
        "payment_method": "contraentrega",
    })

    with patch("app.services.db.get_or_create_session", return_value=session), \
         patch("app.services.db.get_recent_messages", return_value=_HISTORY_WITH_CONTEXT), \
         patch("app.services.db.get_catalog_context", return_value=""), \
         patch("app.services.ai.generate_turn", return_value=ai_resp), \
         patch("app.services.db.identify_client", return_value=None), \
         patch("app.services.db.get_courier_for_client", return_value=None), \
         patch("app.services.db.save_message"), \
         patch("app.services.db.update_session") as mock_update, \
         patch("app.services.db.create_request") as mock_create:

        from app.agent import process_turn
        reply = process_turn("test-chat-ambiguous-analysis", "El mismo")

        assert "análisis" in reply.lower() or "analisis" in reply.lower()
        update_payload = mock_update.call_args[0][1]
        assert update_payload["phase"] == "fase_2_recogida_datos"
        assert update_payload["captured_fields"].get("exam_type") is None
        mock_create.assert_not_called()


def test_out_of_order_route_details_trigger_payment_question():
    session = _make_session(
        phase="fase_2_recogida_datos",
        intent="route_scheduling",
        client_id="client-out-of-order",
        captured={
            "clinic_name": "Clínica Test",
            "pickup_address": "Calle 1",
            "_client_found": True,
        },
    )
    ai_resp = _make_ai_response("fase_2_recogida_datos", "route_scheduling")
    ai_resp["reply"] = "¿Cuál es el nombre del paciente?"
    ai_resp["captured_fields"].update({
        "clinic_name": "Clínica Test",
        "pickup_address": "Calle 1",
        "exam_type": "hemograma",
        "patient_name": "Luna",
        "species": "felino",
        "payment_method": None,
    })

    with patch("app.services.db.get_or_create_session", return_value=session), \
         patch("app.services.db.get_recent_messages", return_value=_HISTORY_WITH_CONTEXT), \
         patch("app.services.db.get_catalog_context", return_value=""), \
         patch("app.services.ai.generate_turn", return_value=ai_resp), \
         patch("app.services.db.identify_client", return_value=None), \
         patch("app.services.db.save_message"), \
         patch("app.services.db.update_session") as mock_update, \
         patch("app.services.db.create_request") as mock_create:

        from app.agent import process_turn
        reply = process_turn("test-chat-out-of-order", "Hemograma para Luna, felino")

        assert "contado" in reply.lower()
        assert "contraentrega" in reply.lower()
        assert "nombre del paciente" not in reply.lower()
        update_payload = mock_update.call_args[0][1]
        assert update_payload["captured_fields"]["patient_name"] == "Luna"
        assert update_payload["captured_fields"]["species"] == "felino"
        mock_create.assert_not_called()


def test_side_question_in_middle_keeps_flow_open_and_preserves_fields():
    session = _make_session(
        phase="fase_2_recogida_datos",
        intent="route_scheduling",
        client_id="client-side-question",
        captured={
            "clinic_name": "Clínica Test",
            "pickup_address": "Calle 1",
            "exam_type": "hemograma",
            "_client_found": True,
        },
    )
    ai_resp = _make_ai_response("fase_2_recogida_datos", "route_scheduling")
    ai_resp["message_mode"] = "side_question"
    ai_resp["reply"] = "El hemograma está disponible. ¿Cuál es el nombre del paciente?"
    ai_resp["captured_fields"].update({
        "clinic_name": "Clínica Test",
        "pickup_address": "Calle 1",
        "exam_type": "hemograma",
        "patient_name": None,
        "species": None,
        "payment_method": None,
    })

    with patch("app.services.db.get_or_create_session", return_value=session), \
         patch("app.services.db.get_recent_messages", return_value=_HISTORY_WITH_CONTEXT), \
         patch("app.services.db.get_catalog_context", return_value=""), \
         patch("app.services.ai.generate_turn", return_value=ai_resp), \
         patch("app.services.db.identify_client", return_value=None), \
         patch("app.services.db.save_message"), \
         patch("app.services.db.update_session") as mock_update, \
         patch("app.services.db.create_request") as mock_create:

        from app.agent import process_turn
        reply = process_turn("test-chat-side-question", "¿Ese hemograma sí lo hacen?")

        assert "hemograma" in reply.lower()
        update_payload = mock_update.call_args[0][1]
        assert update_payload["phase"] == "fase_2_recogida_datos"
        assert update_payload["captured_fields"]["exam_type"] == "hemograma"
        mock_create.assert_not_called()


def test_terminal_route_missing_patient_is_reopened_instead_of_creating_request():
    session = _make_session(
        phase="fase_2_recogida_datos",
        intent="route_scheduling",
        client_id="client-missing-patient",
        captured={
            "clinic_name": "Clínica Test",
            "pickup_address": "Calle 1",
            "exam_type": "hemograma",
            "_client_found": True,
        },
    )
    ai_resp = _make_ai_response("fase_6_cierre", "route_scheduling")
    ai_resp["reply"] = "Listo, queda programada la ruta."
    ai_resp["captured_fields"].update({
        "clinic_name": "Clínica Test",
        "pickup_address": "Calle 1",
        "exam_type": "hemograma",
        "patient_name": None,
        "species": "canino",
        "payment_method": "contraentrega",
    })

    with patch("app.services.db.get_or_create_session", return_value=session), \
         patch("app.services.db.get_recent_messages", return_value=_HISTORY_WITH_CONTEXT), \
         patch("app.services.db.get_catalog_context", return_value=""), \
         patch("app.services.ai.generate_turn", return_value=ai_resp), \
         patch("app.services.db.identify_client", return_value=None), \
         patch("app.services.db.get_courier_for_client", return_value=None), \
         patch("app.services.db.save_message"), \
         patch("app.services.db.update_session") as mock_update, \
         patch("app.services.db.create_request") as mock_create:

        from app.agent import process_turn
        reply = process_turn("test-chat-missing-patient", "Como siempre")

        assert "paciente" in reply.lower()
        update_payload = mock_update.call_args[0][1]
        assert update_payload["phase"] == "fase_2_recogida_datos"
        assert update_payload["captured_fields"].get("patient_name") is None
        mock_create.assert_not_called()


def test_forbidden_city_question_is_replaced_with_next_route_question():
    session = _make_session(
        phase="fase_2_recogida_datos",
        intent="route_scheduling",
        client_id="client-forbidden-city",
        captured={
            "clinic_name": "Clínica Test",
            "pickup_address": "Calle 1",
            "_client_found": True,
        },
    )
    ai_resp = _make_ai_response("fase_2_recogida_datos", "route_scheduling")
    ai_resp["reply"] = "¿En qué ciudad y país debemos recoger la muestra?"
    ai_resp["captured_fields"].update({
        "clinic_name": "Clínica Test",
        "pickup_address": "Calle 1",
        "exam_type": None,
        "patient_name": None,
        "species": None,
        "payment_method": None,
    })

    with patch("app.services.db.get_or_create_session", return_value=session), \
         patch("app.services.db.get_recent_messages", return_value=_HISTORY_WITH_CONTEXT), \
         patch("app.services.db.get_catalog_context", return_value=""), \
         patch("app.services.ai.generate_turn", return_value=ai_resp), \
         patch("app.services.db.identify_client", return_value=None), \
         patch("app.services.db.save_message"), \
         patch("app.services.db.update_session") as mock_update, \
         patch("app.services.db.create_request") as mock_create:

        from app.agent import process_turn
        reply = process_turn("test-chat-forbidden-city", "La ciudad es Bogotá")

        assert "ciudad" not in reply.lower()
        assert "país" not in reply.lower() and "pais" not in reply.lower()
        assert "análisis" in reply.lower() or "analisis" in reply.lower()
        assert mock_update.call_args[0][1]["reply"] == reply
        mock_create.assert_not_called()


def test_forbidden_priority_question_is_replaced_with_next_route_question():
    session = _make_session(
        phase="fase_2_recogida_datos",
        intent="route_scheduling",
        client_id="client-forbidden-priority",
        captured={
            "clinic_name": "Clínica Test",
            "pickup_address": "Calle 1",
            "exam_type": "hemograma",
            "patient_name": "Toby",
            "species": "canino",
            "_client_found": True,
        },
    )
    ai_resp = _make_ai_response("fase_2_recogida_datos", "route_scheduling")
    ai_resp["reply"] = "¿La recogida es urgente o normal?"
    ai_resp["captured_fields"].update({
        "clinic_name": "Clínica Test",
        "pickup_address": "Calle 1",
        "exam_type": "hemograma",
        "patient_name": "Toby",
        "species": "canino",
        "payment_method": None,
    })

    with patch("app.services.db.get_or_create_session", return_value=session), \
         patch("app.services.db.get_recent_messages", return_value=_HISTORY_WITH_CONTEXT), \
         patch("app.services.db.get_catalog_context", return_value=""), \
         patch("app.services.ai.generate_turn", return_value=ai_resp), \
         patch("app.services.db.identify_client", return_value=None), \
         patch("app.services.db.save_message"), \
         patch("app.services.db.update_session") as mock_update, \
         patch("app.services.db.create_request") as mock_create:

        from app.agent import process_turn
        reply = process_turn("test-chat-forbidden-priority", "Es urgente")

        assert "urgente" not in reply.lower()
        assert "normal" not in reply.lower()
        assert "contado" in reply.lower()
        assert "contraentrega" in reply.lower()
        assert mock_update.call_args[0][1]["reply"] == reply
        mock_create.assert_not_called()


def test_ai_cannot_invent_courier_when_no_courier_is_returned():
    session = _make_session(
        phase="fase_2_recogida_datos",
        intent="route_scheduling",
        client_id="client-no-courier-invented",
        captured={"_client_found": True},
    )
    ai_resp = _make_ai_response("fase_6_cierre", "route_scheduling")
    ai_resp["reply"] = "Listo. Motorizado asignado: Luis Inventado (3000000000)."
    ai_resp["captured_fields"].update({
        "clinic_name": "Clínica Test",
        "pickup_address": "Calle 1",
        "exam_type": "hemograma",
        "patient_name": "Toby",
        "species": "canino",
        "payment_method": "contraentrega",
    })

    with patch("app.services.db.get_or_create_session", return_value=session), \
         patch("app.services.db.get_recent_messages", return_value=_HISTORY_WITH_CONTEXT), \
         patch("app.services.db.get_catalog_context", return_value=""), \
         patch("app.services.ai.generate_turn", return_value=ai_resp), \
         patch("app.services.db.identify_client", return_value=None), \
         patch("app.services.db.get_courier_for_client", return_value=None), \
         patch("app.services.db.save_message"), \
         patch("app.services.db.update_session"), \
         patch("app.services.db.create_request", return_value="req-no-courier-invented") as mock_create:

        from app.agent import process_turn
        reply = process_turn("test-chat-no-courier-invented", "Listo")

        assert "Luis Inventado" not in reply
        assert "3000000000" not in reply
        assert "Quedó registrado" in reply
        mock_create.assert_called_once()


def test_route_cannot_close_without_real_session_client_id():
    session = _make_session(
        phase="fase_2_recogida_datos",
        intent="route_scheduling",
        client_id=None,
        captured={"_client_found": True},
    )
    ai_resp = _make_ai_response("fase_6_cierre", "route_scheduling")
    ai_resp["captured_fields"].update({
        "clinic_name": "Clínica Fantasma",
        "pickup_address": "Calle 1",
        "exam_type": "hemograma",
        "patient_name": "Toby",
        "species": "canino",
        "payment_method": "contraentrega",
    })

    with patch("app.services.db.get_or_create_session", return_value=session), \
         patch("app.services.db.get_recent_messages", return_value=_HISTORY_WITH_CONTEXT), \
         patch("app.services.db.get_catalog_context", return_value=""), \
         patch("app.services.ai.generate_turn", return_value=ai_resp), \
         patch("app.services.db.identify_client", return_value=None), \
         patch("app.services.db.get_courier_for_client", return_value=None), \
         patch("app.services.db.save_message"), \
         patch("app.services.db.update_session") as mock_update, \
         patch("app.services.db.create_request") as mock_create:

        from app.agent import process_turn
        reply = process_turn("test-chat-no-real-client", "Listo")

        assert "nit" in reply.lower() or "veterinaria" in reply.lower()
        update_payload = mock_update.call_args[0][1]
        assert update_payload["phase"] == "fase_2_recogida_datos"
        mock_create.assert_not_called()


def test_route_with_contraentrega_ignores_spurious_handoff():
    session = _make_session(
        phase="fase_2_recogida_datos",
        intent="route_scheduling",
        client_id="client-spurious-handoff",
        captured={"_client_found": True},
    )
    ai_resp = _make_ai_response("fase_6_cierre", "route_scheduling", requires_handoff=True, handoff_area="operaciones")
    ai_resp["captured_fields"].update({
        "clinic_name": "Clínica Test",
        "pickup_address": "Calle 1",
        "exam_type": "hemograma",
        "patient_name": "Toby",
        "species": "canino",
        "payment_method": "contraentrega",
    })

    with patch("app.services.db.get_or_create_session", return_value=session), \
         patch("app.services.db.get_recent_messages", return_value=_HISTORY_WITH_CONTEXT), \
         patch("app.services.db.get_catalog_context", return_value=""), \
         patch("app.services.ai.generate_turn", return_value=ai_resp), \
         patch("app.services.db.identify_client", return_value=None), \
         patch("app.services.db.get_courier_for_client", return_value=None), \
         patch("app.services.db.save_message"), \
         patch("app.services.db.update_session") as mock_update, \
         patch("app.services.db.create_request", return_value="req-spurious-handoff") as mock_create:

        from app.agent import process_turn
        process_turn("test-chat-spurious-handoff", "Pago contraentrega")

        update_payload = mock_update.call_args[0][1]
        assert update_payload["phase"] == "fase_6_cierre"
        assert update_payload["requires_handoff"] is False
        assert update_payload["handoff_area"] is None
        mock_create.assert_called_once()


def test_second_order_keeps_identified_client_and_resets_order_fields():
    session = _make_session(
        phase="fase_6_cierre",
        intent="route_scheduling",
        client_id="client-uuid-12",
        captured={
            "clinic_name": "Clinica Test",
            "pickup_address": "Calle anterior",
            "exam_type": "hemograma",
            "patient_name": "Toby",
            "species": "canino",
            "payment_method": "contraentrega",
            "selected_tests": ["ALT"],
            "_client_found": True,
        },
    )
    ai_resp = _make_ai_response("fase_2_recogida_datos", "route_scheduling")
    seen_session = {}

    def fake_generate_turn(*args, **kwargs):
        seen_session.update(kwargs.get("session") if kwargs else args[0])
        return ai_resp

    with patch("app.services.db.get_or_create_session", return_value=session), \
         patch("app.services.db.get_recent_messages", return_value=_HISTORY_WITH_CONTEXT), \
         patch("app.services.ai.generate_turn", side_effect=fake_generate_turn), \
         patch("app.services.db.identify_client", return_value=None), \
         patch("app.services.db.save_message"), \
         patch("app.services.db.update_session"), \
         patch("app.services.db.create_request") as mock_create:

        from app.agent import process_turn
        process_turn("test-chat-1", "Necesito otra ruta")

        assert seen_session["client_id"] == "client-uuid-12"
        assert seen_session["phase_current"] == "fase_1_clasificacion"
        assert seen_session["intent_current"] == "unknown"
        captured = seen_session["captured_fields"]
        assert captured.get("_client_found") is True
        assert "exam_type" not in captured
        assert "patient_name" not in captured
        assert "payment_method" not in captured
        assert "selected_tests" not in captured
        mock_create.assert_not_called()


def test_greeting_after_terminal_phase_does_not_restart_identification_flow():
    session = _make_session(
        phase="fase_6_cierre",
        intent="route_scheduling",
        client_id="client-uuid-12",
        captured={
            "clinic_name": "Clínica Test",
            "pickup_address": "Calle anterior",
            "exam_type": "hemograma",
            "patient_name": "Toby",
            "species": "canino",
            "payment_method": "contraentrega",
            "_client_found": True,
        },
    )
    ai_resp = _make_ai_response("fase_2_recogida_datos", "route_scheduling")
    ai_resp["reply"] = "¿Me indicás el NIT o el nombre de la veterinaria?"

    with patch("app.services.db.get_or_create_session", return_value=session), \
         patch("app.services.db.get_recent_messages", return_value=_HISTORY_WITH_CONTEXT), \
         patch("app.services.ai.generate_turn", return_value=ai_resp) as mock_ai, \
         patch("app.services.db.save_message") as mock_save, \
         patch("app.services.db.update_session") as mock_update, \
         patch("app.services.db.create_request") as mock_create:

        from app.agent import process_turn
        reply = process_turn("test-chat-1", "Hola")

        assert "¿En qué podemos ayudarte" in reply
        mock_ai.assert_not_called()
        assert mock_save.call_count == 2
        mock_update.assert_not_called()
        mock_create.assert_not_called()


def test_custom_profile_selection_adds_calculated_summary_to_ai_context():
    session = _make_session(
        phase="fase_2_recogida_datos",
        intent="route_scheduling",
        client_id="client-uuid-13",
        captured={
            "species": "canino",
            "selected_tests": ["ALT", "CREA"],
            "_client_found": True,
        },
    )
    ai_resp = _make_ai_response("fase_2_recogida_datos", "route_scheduling")
    seen = {}

    def fake_generate_turn(*args, **kwargs):
        seen["session"] = kwargs.get("session") if kwargs else args[0]
        seen["catalog_context"] = kwargs.get("catalog_context")
        return ai_resp

    with patch("app.services.db.get_or_create_session", return_value=session), \
         patch("app.services.db.get_recent_messages", return_value=_HISTORY_WITH_CONTEXT), \
         patch("app.services.db.get_individual_tests_context", return_value="catalogo individual") as mock_catalog, \
         patch("app.services.db.get_tests_by_codes", return_value=[
             {"code": "ALT", "name": "ALT", "price": 30000},
             {"code": "CREA", "name": "Creatinina", "price": 40000},
         ]) as mock_tests, \
         patch("app.services.ai.generate_turn", side_effect=fake_generate_turn), \
         patch("app.services.db.identify_client", return_value=None), \
         patch("app.services.db.save_message"), \
         patch("app.services.db.update_session"), \
         patch("app.services.db.create_request") as mock_create:

        from app.agent import process_turn
        process_turn("test-chat-1", "Agrega ALT y CREA")

        mock_catalog.assert_called_once_with("canino")
        mock_tests.assert_called_once_with(["ALT", "CREA"])
        assert seen["catalog_context"] == "catalogo individual"
        summary = seen["session"].get("_custom_profile_summary", "")
        assert "Subtotal $70,000 COP" in summary
        assert "Total $70,000 COP" in summary
        mock_create.assert_not_called()


def test_selected_catalog_profile_returns_detail_before_continuing_flow():
    session = _make_session(
        phase="fase_2_recogida_datos",
        intent="route_scheduling",
        client_id="client-profile-1",
        captured={"_client_found": True},
    )
    ai_resp = _make_ai_response("fase_2_recogida_datos", "route_scheduling")
    ai_resp["reply"] = "Perfecto, sigo con ese perfil. ¿Cuál es el nombre del paciente?"
    ai_resp["captured_fields"].update({
        "exam_type": "Perfil Renal I",
        "species": "canino",
    })
    profile = {
        "code": "501",
        "name": "Perfil Renal I",
        "category": "Renal",
        "species": "ambos",
        "description": "Cuadro Hemático, Parcial de Orina, BUN/UREA, Creatinina",
        "price": 34000,
    }

    with patch("app.services.db.get_or_create_session", return_value=session), \
         patch("app.services.db.get_recent_messages", return_value=_HISTORY_WITH_CONTEXT), \
         patch("app.services.db.get_catalog_context", return_value=""), \
         patch("app.services.ai.generate_turn", return_value=ai_resp), \
         patch("app.services.db.find_catalog_profile", return_value=profile, create=True) as mock_find, \
         patch("app.services.db.identify_client", return_value=None), \
         patch("app.services.db.save_message"), \
         patch("app.services.db.update_session") as mock_update, \
         patch("app.services.db.create_request") as mock_create:

        from app.agent import process_turn
        reply = process_turn("test-chat-profile-1", "Quiero el Perfil Renal I")

        assert "Perfil Renal I" in reply
        assert "Cuadro Hemático" in reply
        assert "Parcial de Orina" in reply
        assert "BUN/UREA" in reply
        assert "Creatinina" in reply
        assert "$34,000 COP" in reply
        assert "personalizar" in reply.lower()
        assert "agregar" in reply.lower()
        assert "quitar" in reply.lower()
        mock_find.assert_called_once()
        update_payload = mock_update.call_args[0][1]
        fields = update_payload["captured_fields"]
        assert fields["_profile_detail_offered"] is True
        assert fields["_selected_profile_code"] == "501"
        assert fields["_selected_profile_price"] == 34000
        mock_create.assert_not_called()


def test_profile_personalization_request_activates_custom_mode():
    session = _make_session(
        phase="fase_2_recogida_datos",
        intent="route_scheduling",
        client_id="client-profile-2",
        captured={
            "exam_type": "Perfil Renal I",
            "species": "canino",
            "_client_found": True,
            "_profile_detail_offered": True,
            "_selected_profile_code": "501",
            "_selected_profile_name": "Perfil Renal I",
            "_selected_profile_price": 34000,
        },
    )
    ai_resp = _make_ai_response("fase_2_recogida_datos", "route_scheduling")
    ai_resp["reply"] = "Perfecto, lo ajustamos."
    ai_resp["captured_fields"].update(session["captured_fields"])

    with patch("app.services.db.get_or_create_session", return_value=session), \
         patch("app.services.db.get_recent_messages", return_value=_HISTORY_WITH_CONTEXT), \
         patch("app.services.ai.generate_turn", return_value=ai_resp), \
         patch("app.services.db.identify_client", return_value=None), \
         patch("app.services.db.save_message"), \
         patch("app.services.db.update_session") as mock_update, \
         patch("app.services.db.create_request") as mock_create:

        from app.agent import process_turn
        reply = process_turn("test-chat-profile-2", "Quiero personalizarlo")

        assert "Perfil Renal I" in reply
        assert "agregar" in reply.lower()
        assert "quitar" in reply.lower()
        assert "$34,000 COP" in reply
        update_payload = mock_update.call_args[0][1]
        fields = update_payload["captured_fields"]
        assert fields["_profile_customizing"] is True
        assert fields["selected_tests"] == []
        assert fields["removed_tests"] == []
        mock_create.assert_not_called()


def test_profile_customization_summary_uses_base_price_with_adjustments():
    session = _make_session(
        phase="fase_2_recogida_datos",
        intent="route_scheduling",
        client_id="client-profile-3",
        captured={
            "exam_type": "Perfil Renal I",
            "species": "canino",
            "selected_tests": ["1302"],
            "removed_tests": ["1309"],
            "_client_found": True,
            "_profile_detail_offered": True,
            "_profile_customizing": True,
            "_selected_profile_code": "501",
            "_selected_profile_name": "Perfil Renal I",
            "_selected_profile_price": 34000,
        },
    )
    ai_resp = _make_ai_response("fase_2_recogida_datos", "route_scheduling")
    seen = {}

    def fake_generate_turn(*args, **kwargs):
        seen["session"] = kwargs.get("session") if kwargs else args[0]
        seen["catalog_context"] = kwargs.get("catalog_context")
        return ai_resp

    def fake_tests(items):
        if items == ["1302"]:
            return [{"code": "1302", "name": "ALT", "price": 12000}]
        if items == ["1309"]:
            return [{"code": "1309", "name": "Creatinina", "price": 12000}]
        return []

    with patch("app.services.db.get_or_create_session", return_value=session), \
         patch("app.services.db.get_recent_messages", return_value=_HISTORY_WITH_CONTEXT), \
         patch("app.services.db.get_individual_tests_context", return_value="catalogo individual"), \
         patch("app.services.db.get_tests_by_codes", side_effect=fake_tests), \
         patch("app.services.db.get_tests_by_codes_or_names", side_effect=fake_tests, create=True), \
         patch("app.services.ai.generate_turn", side_effect=fake_generate_turn), \
         patch("app.services.db.identify_client", return_value=None), \
         patch("app.services.db.save_message"), \
         patch("app.services.db.update_session"), \
         patch("app.services.db.create_request") as mock_create:

        from app.agent import process_turn
        process_turn("test-chat-profile-3", "Agrega ALT y quita creatinina")

        assert seen["catalog_context"] == "catalogo individual"
        summary = seen["session"].get("_custom_profile_summary", "")
        assert "Perfil Renal I" in summary
        assert "Base $34,000 COP" in summary
        assert "Agregados: 1302-ALT $12k" in summary
        assert "Quitados: 1309-Creatinina $12k" in summary
        assert "Total $34,000 COP" in summary
        mock_create.assert_not_called()


def test_profile_customization_ambiguous_change_asks_for_exact_test():
    session = _make_session(
        phase="fase_2_recogida_datos",
        intent="route_scheduling",
        client_id="client-profile-ambiguous",
        captured={
            "exam_type": "Perfil Renal I",
            "species": "canino",
            "selected_tests": [],
            "removed_tests": [],
            "_client_found": True,
            "_profile_detail_offered": True,
            "_profile_customizing": True,
            "_selected_profile_code": "501",
            "_selected_profile_name": "Perfil Renal I",
            "_selected_profile_price": 34000,
        },
    )
    ai_resp = _make_ai_response("fase_2_recogida_datos", "route_scheduling")
    ai_resp["reply"] = "Listo, lo quito."
    ai_resp["captured_fields"].update(session["captured_fields"])

    with patch("app.services.db.get_or_create_session", return_value=session), \
         patch("app.services.db.get_recent_messages", return_value=_HISTORY_WITH_CONTEXT), \
         patch("app.services.db.get_individual_tests_context", return_value="catalogo individual"), \
         patch("app.services.db.get_tests_by_codes_or_names", return_value=[], create=True), \
         patch("app.services.ai.generate_turn", return_value=ai_resp), \
         patch("app.services.db.identify_client", return_value=None), \
         patch("app.services.db.save_message"), \
         patch("app.services.db.update_session") as mock_update, \
         patch("app.services.db.create_request") as mock_create:

        from app.agent import process_turn
        reply = process_turn("test-chat-profile-ambiguous", "quita ese")

        assert "nombre o código exacto" in reply
        assert "agregar o quitar" in reply.lower()
        update_payload = mock_update.call_args[0][1]
        assert update_payload["phase"] == "fase_2_recogida_datos"
        mock_create.assert_not_called()


def test_profile_customization_unknown_test_is_not_persisted():
    session = _make_session(
        phase="fase_2_recogida_datos",
        intent="route_scheduling",
        client_id="client-profile-unknown",
        captured={
            "exam_type": "Perfil Renal I",
            "species": "canino",
            "selected_tests": [],
            "removed_tests": [],
            "_client_found": True,
            "_profile_detail_offered": True,
            "_profile_customizing": True,
            "_selected_profile_code": "501",
            "_selected_profile_name": "Perfil Renal I",
            "_selected_profile_price": 34000,
        },
    )
    ai_resp = _make_ai_response("fase_2_recogida_datos", "route_scheduling")
    ai_resp["reply"] = "Agrego Dilution X."
    ai_resp["captured_fields"].update(session["captured_fields"])
    ai_resp["captured_fields"]["selected_tests"] = ["Dilution X"]

    with patch("app.services.db.get_or_create_session", return_value=session), \
         patch("app.services.db.get_recent_messages", return_value=_HISTORY_WITH_CONTEXT), \
         patch("app.services.db.get_individual_tests_context", return_value="catalogo individual"), \
         patch("app.services.db.get_tests_by_codes_or_names", return_value=[], create=True), \
         patch("app.services.ai.generate_turn", return_value=ai_resp), \
         patch("app.services.db.identify_client", return_value=None), \
         patch("app.services.db.save_message"), \
         patch("app.services.db.update_session") as mock_update, \
         patch("app.services.db.create_request") as mock_create:

        from app.agent import process_turn
        reply = process_turn("test-chat-profile-unknown", "Agrega Dilution X")

        assert "No encuentro" in reply
        assert "Dilution X" in reply
        fields = mock_update.call_args[0][1]["captured_fields"]
        assert fields["selected_tests"] == []
        mock_create.assert_not_called()


def test_route_closure_profile_summary_includes_adjusted_value():
    session = _make_session(
        phase="fase_2_recogida_datos",
        intent="route_scheduling",
        client_id="client-profile-close",
        captured={
            "species": "canino",
            "selected_tests": ["1302"],
            "removed_tests": ["1309"],
            "_client_found": True,
            "_profile_detail_offered": True,
            "_profile_customizing": True,
            "_selected_profile_code": "501",
            "_selected_profile_name": "Perfil Renal I",
            "_selected_profile_price": 34000,
        },
    )
    ai_resp = _make_ai_response("fase_6_cierre", "route_scheduling")
    ai_resp["reply"] = "Listo, quedó registrado."
    ai_resp["captured_fields"].update(session["captured_fields"])
    ai_resp["captured_fields"].update({
        "clinic_name": "Clínica Test",
        "pickup_address": "Calle 1",
        "exam_type": "Perfil Renal I",
        "patient_name": "Toby",
        "species": "canino",
        "payment_method": "contraentrega",
    })

    def fake_tests(items):
        if items == ["1302"]:
            return [{"code": "1302", "name": "ALT", "price": 12000}]
        if items == ["1309"]:
            return [{"code": "1309", "name": "Creatinina", "price": 12000}]
        return []

    with patch("app.services.db.get_or_create_session", return_value=session), \
         patch("app.services.db.get_recent_messages", return_value=_HISTORY_WITH_CONTEXT), \
         patch("app.services.db.get_individual_tests_context", return_value="catalogo individual"), \
         patch("app.services.db.get_tests_by_codes_or_names", side_effect=fake_tests, create=True), \
         patch("app.services.ai.generate_turn", return_value=ai_resp), \
         patch("app.services.db.identify_client", return_value=None), \
         patch("app.services.db.get_courier_for_client", return_value=None), \
         patch("app.services.db.save_message"), \
         patch("app.services.db.update_session"), \
         patch("app.services.db.create_request", return_value="req-profile-close") as mock_create:

        from app.agent import process_turn
        reply = process_turn("test-chat-profile-close", "Lo cerramos así")

        assert "Quedó registrado" in reply
        assert "Perfil Renal I" in reply
        assert "Agregados: 1302-ALT $12k" in reply
        assert "Quitados: 1309-Creatinina $12k" in reply
        assert "Valor estimado: $34,000 COP" in reply
        mock_create.assert_called_once()


def test_profile_description_items_keep_parenthetical_commas_together():
    from app.agent import _profile_description_items

    assert _profile_description_items(
        "Cuadro Hemático, Snap 4DX (Anaplasma, Ehrlichia, Borrelia, Dirofilaria) ELISA SNAP"
    ) == [
        "Cuadro Hemático",
        "Snap 4DX (Anaplasma, Ehrlichia, Borrelia, Dirofilaria) ELISA SNAP",
    ]


def test_route_closure_reply_includes_assigned_courier_notification():
    session = _make_session(phase="fase_2_recogida_datos", intent="route_scheduling", client_id="client-uuid-14")
    ai_resp = _make_ai_response("fase_6_cierre", "route_scheduling")
    ai_resp["reply"] = "Listo, la recogida queda programada."
    ai_resp["captured_fields"].update({
        "clinic_name": "Clinica Test",
        "pickup_address": "Calle 1",
        "exam_type": "hemograma",
        "patient_name": "Toby",
        "species": "canino",
        "payment_method": "contraentrega",
    })
    courier = {"id": "courier-14", "name": "Luis Moto", "phone": "3001234567"}

    with patch("app.services.db.get_or_create_session", return_value=session), \
         patch("app.services.db.get_recent_messages", return_value=_HISTORY_WITH_CONTEXT), \
         patch("app.services.db.get_catalog_context", return_value=""), \
         patch("app.services.ai.generate_turn", return_value=ai_resp), \
         patch("app.services.db.identify_client", return_value=None), \
         patch("app.services.db.get_courier_for_client", return_value=courier), \
         patch("app.services.db.save_message") as mock_save, \
         patch("app.services.db.update_session") as mock_update, \
         patch("app.services.db.create_request", return_value="req-uuid-courier") as mock_create:

        from app.agent import process_turn
        reply = process_turn("test-chat-1", "Pago contraentrega")

        assert "Luis Moto" in reply
        assert "3001234567" in reply
        assert "motorizado" in reply.lower()
        assert mock_save.call_args_list[1][0][1] == reply
        assert mock_update.call_args[0][1]["reply"] == reply
        mock_create.assert_called_once()


def test_agent_static_messages_are_readable_spanish():
    from app.agent import (
        WELCOME_MESSAGE,
        CLIENT_NOT_FOUND_MESSAGE,
        CLIENT_SEARCH_FAILED_MESSAGE,
        FAREWELL_REPLY,
        PAYMENT_METHOD_QUESTION,
    )

    combined = "\n".join([
        WELCOME_MESSAGE,
        CLIENT_NOT_FOUND_MESSAGE,
        CLIENT_SEARCH_FAILED_MESSAGE,
        FAREWELL_REPLY,
        PAYMENT_METHOD_QUESTION,
    ])

    assert "Buen día" in WELCOME_MESSAGE
    assert "laboratorio clínico veterinario" in WELCOME_MESSAGE
    assert "¿En qué podemos ayudarte?" in WELCOME_MESSAGE
    assert "¿Sos cliente nuevo?" in CLIENT_SEARCH_FAILED_MESSAGE
    assert "¿preferís pagar ahora" in PAYMENT_METHOD_QUESTION

    for mojibake in ("\u00c3", "\u00c2", "\u00f0\u0178", "\u00e2\u2020"):
        assert mojibake not in combined


def test_agent_tokenizer_preserves_spanish_accents():
    from app.agent import _tokenize

    assert _tokenize("Sí, súper. También necesito información.") == [
        "sí",
        "súper",
        "también",
        "necesito",
        "información",
    ]


def test_updated_agent_integration_smoke_profile_adjustment_and_request_creation():
    session = _make_session(
        phase="fase_2_recogida_datos",
        intent="route_scheduling",
        client_id="client-smoke-profile",
        captured={
            "species": "canino",
            "selected_tests": ["1302"],
            "removed_tests": ["1309"],
            "_client_found": True,
            "_profile_detail_offered": True,
            "_profile_customizing": True,
            "_selected_profile_code": "501",
            "_selected_profile_name": "Perfil Renal I",
            "_selected_profile_price": 34000,
        },
    )
    ai_resp = _make_ai_response("fase_6_cierre", "route_scheduling")
    ai_resp["captured_fields"].update(session["captured_fields"])
    ai_resp["captured_fields"].update({
        "clinic_name": "Clinica Smoke",
        "pickup_address": "Calle 123",
        "exam_type": "Perfil Renal I",
        "patient_name": "Luna",
        "species": "canino",
        "payment_method": "contraentrega",
    })

    def fake_tests(items):
        if items == ["1302"]:
            return [{"code": "1302", "name": "ALT", "price": 12000}]
        if items == ["1309"]:
            return [{"code": "1309", "name": "Creatinina", "price": 12000}]
        return []

    with patch("app.services.db.get_or_create_session", return_value=session), \
         patch("app.services.db.get_recent_messages", return_value=_HISTORY_WITH_CONTEXT), \
         patch("app.services.db.get_individual_tests_context", return_value="catalogo individual"), \
         patch("app.services.db.get_tests_by_codes_or_names", side_effect=fake_tests, create=True), \
         patch("app.services.ai.generate_turn", return_value=ai_resp), \
         patch("app.services.db.identify_client", return_value=None), \
         patch("app.services.db.get_courier_for_client", return_value={"id": "courier-1", "name": "Luis", "phone": "3001234567"}), \
         patch("app.services.db.save_message"), \
         patch("app.services.db.update_session") as mock_update, \
         patch("app.services.db.create_request", return_value="req-smoke") as mock_create:

        from app.agent import process_turn
        reply = process_turn("test-chat-smoke-profile", "Lo cerramos así")

    assert "Perfil Renal I" in reply
    assert "Agregados: 1302-ALT $12k" in reply
    assert "Quitados: 1309-Creatinina $12k" in reply
    assert "Valor estimado: $34,000 COP" in reply
    assert "Luis" in reply
    assert mock_update.call_args[0][1]["phase"] == "fase_6_cierre"
    mock_create.assert_called_once()
