"""El bot no habla encima de un asesor (prueba de A3 del 12/11, ERR-204).

Caso real: el bot derivó a un cliente nuevo, la asesora lo tomó y le preguntó «¿Médico
veterinario o Clínica o centro veterinario?». El cliente contestó «Médico veterinario» y el bot
repitió la derivación: el buscador devolvía «Centro Medico Veterinario…» y lo tomó por una
identificación. A3 preguntó cada cuánto retoma el bot: no había ninguna regla.

Regla (OK del usuario, 2026-11-16): calla mientras un asesor atiende; vuelve cuando la
conversación se resuelve o a las 12 h sin que nadie de A3 la mire.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from app import agent, asesor
from app.messages import WELCOME_MESSAGE

AHORA = 1_794_505_537.0  # «Médico veterinario», 12/11 12:45 Bogotá


def _conversacion(estado="open", asesor_id=2, visto=AHORA - 75, **extra):
    """El bloque `conversation` del webhook de Chatwoot, como llegó en la prueba real."""
    meta = {"sender": {"phone_number": "+573015462202"}}
    if asesor_id:
        meta["assignee"] = {"id": asesor_id, "name": "Johan"}
    return {"id": 2, "status": estado, "meta": meta, "agent_last_seen_at": visto, **extra}


# ── La compuerta: ¿hay un asesor atendiendo? ─────────────────────────────────

def test_abierta_asignada_y_vista_hace_un_minuto_el_bot_calla():
    assert asesor.atendiendo(_conversacion(), AHORA) is True


def test_en_pendiente_atiende_el_bot():
    assert asesor.atendiendo(_conversacion(estado="pending", asesor_id=None, visto=0), AHORA) is False


def test_derivada_a_un_equipo_pero_sin_asesor_todavia_no_silencia():
    """`assign_team` la deja «open» con equipo; hasta que alguien la toma, nadie atiende."""
    sin_asesor = _conversacion(asesor_id=None)
    sin_asesor["meta"]["team"] = {"id": 1, "name": "operaciones"}
    assert asesor.atendiendo(sin_asesor, AHORA) is False


def test_a_las_doce_horas_sin_que_nadie_la_mire_el_bot_vuelve():
    assert asesor.atendiendo(_conversacion(visto=AHORA - 11 * 3600), AHORA) is True
    assert asesor.atendiendo(_conversacion(visto=AHORA - 13 * 3600), AHORA) is False


def test_asignada_pero_nunca_abierta_por_un_asesor_no_silencia():
    assert asesor.atendiendo(_conversacion(visto=0), AHORA) is False
    assert asesor.atendiendo(_conversacion(visto=None), AHORA) is False


@pytest.mark.parametrize("basura", [None, {}, {"status": "open"}, {"status": "open", "meta": "x"},
                                    {"status": "open", "meta": {"assignee": None}},
                                    {"status": "open", "meta": {"assignee": {"id": 2}}, "agent_last_seen_at": "ayer"}])
def test_sin_datos_claros_el_bot_sigue_como_siempre(basura):
    assert asesor.atendiendo(basura, AHORA) is False


# ── main: con asesor no hay autorización de datos ni agente ──────────────────

def test_con_asesor_el_bot_no_pregunta_ni_responde():
    from app import main

    with patch("app.main.motorizado_chat.atender", return_value=False), \
         patch("app.main.privacidad.atender") as privacidad, \
         patch("app.main.process_turn") as agente, \
         patch("app.main.chatwoot.send_message") as enviar:
        main._process_chatwoot("2", "Médico veterinario", "whatsapp", "+573015462202", True)
    privacidad.assert_not_called()
    agente.assert_not_called()
    enviar.assert_not_called()


def test_el_motorizado_recibe_su_lista_aunque_un_asesor_tenga_abierta_su_conversacion():
    from app import main

    with patch("app.main.motorizado_chat.atender", return_value=True) as motorizado, \
         patch("app.main.process_turn") as agente:
        main._process_chatwoot("3", "hola", "whatsapp", "+573503297922", True)
    motorizado.assert_called_once()
    agente.assert_not_called()


def test_el_webhook_lee_la_senal_del_asesor_del_mismo_aviso(monkeypatch):
    from app import main

    monkeypatch.setattr("app.main.CHATWOOT_WEBHOOK_SECRET", "s3creto")
    main.app.config["TESTING"] = True
    cuerpo = {"event": "message_created", "message_type": "incoming", "content": "Médico veterinario",
              "conversation": {**_conversacion(visto=datetime.now(timezone.utc).timestamp() - 60),
                               "channel": "Channel::Whatsapp"}}
    with patch("app.main._debouncer.submit") as encolar, patch("app.main._process_chatwoot") as procesar:
        assert main.app.test_client().post("/chatwoot/webhook?token=s3creto", json=cuerpo).status_code == 200
        encolar.call_args[0][2]("Médico veterinario")
    assert procesar.call_args[0] == ("2", "Médico veterinario", "whatsapp", "+573015462202", True, False)


# ── Informe de A3 del 25/11: «si la atención humana se demora, el bot se activa» ──

def test_el_cliente_esperando_mas_de_una_hora_al_asesor_es_demora():
    conv = _conversacion(visto=AHORA - 60, waiting_since=AHORA - 61 * 60)
    assert asesor.demorado(conv, AHORA) is True
    assert asesor.atendiendo(conv, AHORA) is False  # el bot deja de callar


def test_esperando_menos_de_una_hora_el_bot_sigue_callado():
    conv = _conversacion(visto=AHORA - 60, waiting_since=AHORA - 30 * 60)
    assert asesor.demorado(conv, AHORA) is False
    assert asesor.atendiendo(conv, AHORA) is True


def test_si_el_asesor_ya_contesto_no_hay_demora():
    """Chatwoot borra `waiting_since` cuando el asesor responde."""
    assert asesor.demorado(_conversacion(waiting_since=0), AHORA) is False
    assert asesor.demorado(_conversacion(waiting_since=None), AHORA) is False


def test_sin_asesor_asignado_no_es_demora_del_asesor():
    conv = _conversacion(asesor_id=None, waiting_since=AHORA - 5 * 3600)
    assert asesor.demorado(conv, AHORA) is False


def test_con_demora_el_bot_retoma_y_le_devuelve_la_conversacion():
    from app import main

    with patch("app.main.motorizado_chat.atender", return_value=False), \
         patch("app.main.privacidad.atender", return_value=False), \
         patch("app.main.retomar_tras_demora", return_value="Perdón la demora…") as retomar, \
         patch("app.main.chatwoot") as cw, \
         patch("app.main.process_turn") as agente:
        main._process_chatwoot("2", "hola?", "whatsapp", "+573015462202", False, True)
    retomar.assert_called_once_with("2", "hola?", "whatsapp")
    cw.send_message.assert_called_once_with("2", "Perdón la demora…")
    cw.liberar_asesor.assert_called_once()
    assert "vuelve a asignártela" in cw.liberar_asesor.call_args[0][1]
    agente.assert_not_called()


def test_retomar_saluda_con_disculpas_y_el_menu_desde_cero():
    fake_db = MagicMock()
    fake_db.get_or_create_session.return_value = {"external_chat_id": "2", "captured_fields": {"_handoff_announced": True}}
    with patch.object(agent, "db", fake_db):
        reply = agent.retomar_tras_demora("2", "hola?", "whatsapp")
    assert reply.startswith("Perdón la demora") and WELCOME_MESSAGE in reply
    guardado = fake_db.update_session.call_args[0][1]
    assert guardado["phase"] == "fase_0_bienvenida" and guardado["requires_handoff"] is False
    fake_db.clear_client_from_session.assert_called_once_with("2")


# ── Las frases de cualquiera no despiertan al bot ────────────────────────────

CLINICAS = [{"id": "c1", "clinic_name": "Centro Medico Veterinario"},
            {"id": "c2", "clinic_name": "PetVet Centro Medico Veterinario"},
            {"id": "c3", "clinic_name": "Centro Medico Veterinario La Uribe"},
            {"id": "c4", "clinic_name": "Varvet Emergencias Veterinarias SAS"}]


@pytest.fixture
def base_real(monkeypatch):
    """El buscador devuelve lo que devolvió con la base real: cualquier clínica que comparta
    una palabra, también las genéricas."""
    def _buscar(texto, limit=6):
        palabras = set(agent._tokenize(texto))
        return [c for c in CLINICAS if palabras & set(agent._tokenize(c["clinic_name"]))][:limit]

    monkeypatch.setattr(agent.db, "find_client_matches", _buscar)
    monkeypatch.setattr(agent.db, "find_clients_by_tax_id", lambda t: [])


@pytest.mark.parametrize("frase", ["Médico veterinario", "Clínica o centro veterinario", "soy veterinario",
                                   "un consultorio veterinario"])
def test_la_respuesta_a_la_pregunta_de_la_asesora_no_reabre_al_bot(base_real, frase):
    assert agent._reidentifies_after_escalation(frase) is False


@pytest.mark.parametrize("frase", ["somos Varvet", "Centro Medico Veterinario La Uribe", "es PetVet"])
def test_nombrar_una_clinica_registrada_sigue_reabriendo(base_real, frase):
    assert agent._reidentifies_after_escalation(frase) is True


def test_el_nombre_exacto_de_una_clinica_de_palabras_genericas_tambien_vale(base_real):
    assert agent._reidentifies_after_escalation("Centro Médico Veterinario") is True


# ── La derivación vieja deja de silenciar ────────────────────────────────────

def _turno_derivado(mensaje, ultimo_mensaje_hace_horas):
    session = {"external_chat_id": "2", "client_id": None, "channel": "whatsapp",
               "phase_current": "fase_7_escalado", "intent_current": "new_client", "status": "in_progress",
               "captured_fields": {"_handoff_announced": True, "_escalated_unfound_client": True}}
    fake_db = MagicMock()
    fake_db.get_or_create_session.return_value = session
    fake_db.get_recent_messages.return_value = [
        {"role": "user", "content": "Vet Fantasma"},
        {"role": "bot", "content": "No encuentro ningún cliente registrado con ese dato."}]
    fake_db.last_message_at.return_value = (
        datetime.now(timezone.utc) - timedelta(hours=ultimo_mensaje_hace_horas)).isoformat()
    fake_db.find_client_matches.return_value = []
    fake_db.find_clients_by_tax_id.return_value = []
    with patch.object(agent, "db", fake_db), patch.object(agent, "PEDIDOS_ENABLED", False), \
         patch.object(agent.ai, "generate_turn") as modelo:
        reply = agent.process_turn("2", mensaje, channel="whatsapp")
    modelo.assert_not_called()
    return reply, fake_db


def test_un_hola_nueve_dias_despues_de_la_derivacion_recibe_el_saludo():
    reply, fake_db = _turno_derivado("Hola", ultimo_mensaje_hace_horas=9 * 24)
    assert reply == WELCOME_MESSAGE
    guardado = fake_db.update_session.call_args[0][1]
    assert guardado["phase"] == "fase_0_bienvenida"
    assert guardado["requires_handoff"] is False
    assert "_escalated_unfound_client" not in guardado["captured_fields"]


def test_recien_derivado_el_bot_sigue_callado():
    reply, fake_db = _turno_derivado("Hola", ultimo_mensaje_hace_horas=1)
    assert reply is None
    fake_db.update_session.assert_not_called()


def test_si_no_se_puede_leer_la_fecha_sigue_el_silencio():
    with patch.object(agent.db, "last_message_at", side_effect=RuntimeError("caída")):
        assert agent._conversacion_vencida("2") is False
    with patch.object(agent.db, "last_message_at", return_value=None):
        assert agent._conversacion_vencida("2") is False
