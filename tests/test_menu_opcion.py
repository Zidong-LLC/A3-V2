"""«Programar rita» (por «ruta») al menú de bienvenida terminó con un asesor (prueba real del
29/10). La opción 1 no tiene regla: la clasifica el modelo, y esa vez no la entendió.

La red solo actúa cuando el modelo devolvió `unknown`, en el punto del menú y sin cliente
identificado. Lo que el modelo entendió —otra opción, un cliente nuevo, una pregunta— manda.
"""
from unittest.mock import MagicMock, patch

import pytest

from app import agent, menu_opcion
from app.messages import CLIENT_IDENTIFICATION_REQUIRED_MESSAGE, WELCOME_MESSAGE


@pytest.mark.parametrize("texto", ["Programar rita", "programar ruta", "progrmar ruta", "Agendar recojida",
                                   "la ruta", "recoger muestras", "programr", "PROGRAMAR"])
def test_la_opcion_uno_se_reconoce_bien_escrita_o_casi(texto):
    assert menu_opcion.parece_programar(texto) is True


@pytest.mark.parametrize("texto", ["rita", "hola", "otro", "pagos", "resultados", "necesito hablar con alguien",
                                   "quiero programar una recogida pero soy cliente nuevo y no tengo nit", "", "4"])
def test_lo_que_no_es_la_opcion_uno_no_se_fuerza(texto):
    assert menu_opcion.parece_programar(texto) is False


def _turno(mensaje, respuesta_modelo, sesion=None, historial=None):
    session = {"external_chat_id": "c9", "client_id": None, "channel": "whatsapp",
               "phase_current": "fase_0_bienvenida", "intent_current": "unknown",
               "captured_fields": {}, "status": "in_progress", **(sesion or {})}
    fake_db = MagicMock()
    fake_db.get_or_create_session.return_value = session
    fake_db.get_recent_messages.return_value = historial or [
        {"role": "user", "content": "hola"}, {"role": "bot", "content": WELCOME_MESSAGE}]
    for nombre in ("find_client", "get_client_memory", "find_client_exact", "identify_client", "find_diagnostic_label"):
        getattr(fake_db, nombre).return_value = None
    fake_db.find_clients_matching.return_value = []
    fake_db.list_catalog_tests.return_value = []
    fake_db.find_tests_by_area.return_value = (None, [])
    base = {"intent": "unknown", "service_area": "unknown", "phase": "fase_7_escalado", "requires_handoff": True,
            "handoff_area": "operaciones", "captured_fields": {}, "missing_fields": [],
            "user_intent_signal": "unclear", "reply": "Te comunico con un asesor del equipo."}
    with patch.object(agent, "db", fake_db), \
         patch.object(agent.ai, "generate_turn", return_value={**base, **respuesta_modelo}):
        reply = agent.process_turn("c9", mensaje)
    guardado = fake_db.update_session.call_args[0][1] if fake_db.update_session.call_args else {}
    return reply or "", guardado


def test_programar_rita_ya_no_deriva_a_un_asesor():
    reply, guardado = _turno("Programar rita", {})
    assert "asesor" not in reply.lower()
    assert reply.startswith(CLIENT_IDENTIFICATION_REQUIRED_MESSAGE[:60]), reply
    assert guardado.get("requires_handoff") is not True
    assert guardado.get("intent") == "route_scheduling"


def test_si_el_modelo_entendio_otra_cosa_manda_el_modelo():
    """«Programar» puede venir en un mensaje de cliente nuevo: eso sigue escalando a recepción."""
    reply, guardado = _turno("programar, soy nuevo", {"intent": "new_client", "user_intent_signal": "new_or_unregistered_client"})
    assert guardado.get("requires_handoff") is True


def test_la_opcion_cuatro_sigue_derivando():
    reply, guardado = _turno("otro", {})
    assert guardado.get("requires_handoff") is True


def test_lo_que_no_se_parece_a_ninguna_opcion_sigue_como_lo_dejo_el_modelo():
    reply, guardado = _turno("necesito algo distinto", {})
    assert guardado.get("requires_handoff") is True and "asesor" in reply.lower()
