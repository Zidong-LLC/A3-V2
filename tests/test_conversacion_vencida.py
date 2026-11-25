"""Una conversación vieja arranca de cero, en el estado que sea (ERR-206).

Caso real (prueba de A3 del 21/11): el 17/11 el bot cerró solo un pedido por inactividad y la
sesión quedó en fase de cierre con restos de la última orden. Cuatro días después el cliente
escribió «hola»: el bot lo leyó como «recién cerré una orden y esto no encaja», lo derivó a un
asesor, lo dejó mudo y creó una solicitud fantasma (A3-2026-033) con los restos.

Regla (OK del usuario, 2026-11-25): más de 12 h sin mensajes → saludo con el menú, sin restos
ni cliente, sin llamar al modelo. Con menos de 12 h todo sigue igual.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from app import agent
from app.messages import WELCOME_MESSAGE


class _LlegoAlModelo(Exception):
    pass


def _sesion_del_21_11(**extra_campos):
    """La sesión del chat 5 como estaba el 21/11 (resumida a lo que importa)."""
    return {"external_chat_id": "5", "client_id": "12fc3a48", "channel": "whatsapp",
            "phase_current": "fase_6_cierre", "intent_current": "route_scheduling",
            "status": "in_progress",
            "captured_fields": {"exam_type": "1701 Coprológico", "selected_tests": ["1701"],
                                "_client_found": True, "_last_order_number": "A3-2026-025",
                                "_resultados_pide": "nit", "_resultados_intentos": 1,
                                **extra_campos}}


def _turno(session, mensaje="hola", hace_horas=4 * 24, historia=True):
    fake_db = MagicMock()
    fake_db.get_or_create_session.return_value = session
    fake_db.get_recent_messages.return_value = [
        {"role": "bot", "content": "Hola, como pasó más de una hora sin respuesta cerré tu pedido…"},
    ] if historia else []
    fake_db.last_message_at.return_value = (
        datetime.now(timezone.utc) - timedelta(hours=hace_horas)).isoformat()
    with patch.object(agent, "db", fake_db), patch.object(agent, "PEDIDOS_ENABLED", False), \
         patch.object(agent.ai, "generate_turn", side_effect=_LlegoAlModelo) as modelo:
        try:
            reply = agent.process_turn("5", mensaje, channel="whatsapp")
        except _LlegoAlModelo:
            reply = _LlegoAlModelo
    return reply, fake_db, modelo


def test_el_hola_del_21_11_recibe_el_saludo_y_arranca_limpio():
    reply, fake_db, modelo = _turno(_sesion_del_21_11())
    assert reply == WELCOME_MESSAGE
    modelo.assert_not_called()
    guardado = fake_db.update_session.call_args[0][1]
    assert guardado["phase"] == "fase_0_bienvenida"
    assert guardado["requires_handoff"] is False
    assert not {k: v for k, v in guardado["captured_fields"].items() if v}  # ni un resto
    fake_db.clear_client_from_session.assert_called_once_with("5")


def test_no_crea_ninguna_solicitud_con_los_restos():
    _, fake_db, _ = _turno(_sesion_del_21_11())
    fake_db.create_request.assert_not_called()
    fake_db.add_request_event.assert_not_called()


@pytest.mark.parametrize("fase, campos", [
    ("fase_7_escalado", {"_handoff_announced": True}),          # derivación por intención desconocida
    ("fase_7_escalado", {"_escalated_unfound_client": True}),   # derivación de ERR-204
    ("fase_2_recoleccion", {"patient_name": "Roku"}),           # orden a medio cargar
])
def test_cualquier_estado_viejo_arranca_de_cero(fase, campos):
    session = _sesion_del_21_11(**campos)
    session["phase_current"] = fase
    reply, _, modelo = _turno(session, hace_horas=13)
    assert reply == WELCOME_MESSAGE
    modelo.assert_not_called()


def test_con_menos_de_12_horas_sigue_donde_estaba():
    reply, fake_db, modelo = _turno(_sesion_del_21_11(), hace_horas=2)
    assert reply is _LlegoAlModelo  # el turno siguió su camino normal, hasta el modelo
    fake_db.clear_client_from_session.assert_not_called()


def test_el_cliente_final_bloqueado_sigue_callado_aunque_pasen_dias():
    reply, fake_db, modelo = _turno(_sesion_del_21_11(_blocked=True))
    assert reply is None
    fake_db.update_session.assert_not_called()


def test_chat_sin_historia_no_consulta_la_fecha():
    reply, fake_db, _ = _turno(_sesion_del_21_11(), historia=False)
    assert reply == WELCOME_MESSAGE
    fake_db.last_message_at.assert_not_called()
