"""
Regresión ERR-086 (QA en vivo, 2026-07-22, chat 4): el cliente respondió al pedido de
identificación con "Agrocol estamos registrados si no me equivoco" y el bot lo mandó de
vuelta al menú de bienvenida ("Tranquilo, sin problema 🙂...") — descartando el nombre
"Agrocol" que venía en el mismo mensaje.

Causa: `_wants_to_reconsider_option` disparaba con el token "equivoco" sin mirar que
estaba NEGADO ("si NO me equivoco" es una muletilla de duda, no un "me confundí de
opción"). Misma clase que ERR-073: atajo pre-LLM decidiendo por palabras sueltas.
"""
from unittest.mock import MagicMock, patch

from app import agent
from app.detectors import _wants_to_reconsider_option
from app.messages import OPTION_RECONSIDER_MESSAGE

AGROCOL = {"id": "cli-AGRO", "clinic_name": "AgrocolombiaSA", "address": "",
           "tax_id": None, "phone": "", "email": ""}


def test_muletillas_de_duda_no_disparan_el_menu():
    for msg in (
        "Agrocol estamos registrados si no me equivoco",
        "si no me equivoco ya estamos registrados",
        "no me equivoco de opción",
        "creo que no me confundí",
    ):
        assert not _wants_to_reconsider_option(msg), msg


def test_equivocarse_de_verdad_sigue_reconduciendo():
    for msg in (
        "perdón, me confundí de opción",
        "me equivoqué",
        "uy me equivoque de opcion",
        "quiero cambiar de opción",
    ):
        assert _wants_to_reconsider_option(msg), msg


def test_turno_real_busca_agrocol_en_vez_de_resetear():
    """El turno completo del chat 4: con 'si no me equivoco' el bot debe buscar el
    cliente, no volver al menú."""
    session = {
        "external_chat_id": "c1", "client_id": None, "channel": "telegram",
        "phase_current": "fase_1_clasificacion", "intent_current": "route_scheduling",
        "captured_fields": {}, "status": "in_progress",
    }
    fake_db = MagicMock()
    fake_db.get_or_create_session.return_value = session
    fake_db.get_recent_messages.return_value = [
        {"role": "user", "content": "1"},
        {"role": "bot", "content": "Claro, con gusto. ¿Me compartes el NIT o el nombre de la "
                                   "veterinaria o médico veterinario para ver si está registrado?"},
    ]
    fake_db.get_client_memory.return_value = None
    fake_db.list_catalog_tests.return_value = []
    fake_db.find_tests_by_area.return_value = (None, [])
    fake_db.get_tests_by_codes_or_names.return_value = []
    fake_db.find_client_exact.return_value = None
    fake_db.find_clients_by_tax_id.return_value = []
    fake_db.find_client_matches.return_value = [AGROCOL]
    ai = {
        "reply": "ok", "phase": "fase_1_identificacion", "intent": "route_scheduling",
        "service_area": "route_scheduling", "requires_handoff": False, "handoff_area": None,
        "captured_fields": {"clinic_name": "Agrocol"}, "confidence": 0.9,
        "message_mode": "flow_progress", "pending_intents": [],
        "user_intent_signal": "provides_client_identifier", "resume_prompt": "",
    }
    with patch.object(agent, "db", fake_db), \
         patch.object(agent.ai, "generate_turn", return_value=ai):
        reply = agent.process_turn("c1", "Agrocol estamos registrados si no me equivoco")

    assert OPTION_RECONSIDER_MESSAGE.splitlines()[0] not in (reply or ""), \
        "volvió a resetear al menú con la muletilla 'si no me equivoco'"
    assert "AgrocolombiaSA" in (reply or ""), "no buscó/ofreció el cliente Agrocol"
