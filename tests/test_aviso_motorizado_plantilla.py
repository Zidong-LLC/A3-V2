"""Aviso automático al motorizado con plantilla de WhatsApp (informe de A3 del 25/11, punto 6).

A3: el aviso «debería ser automático». Solo llegaba si el motorizado había escrito en las
últimas 24 h (regla de WhatsApp): ninguno de los 9 motorizados reales lo recibía. Con la
plantilla `recogida_asignada` aprobada en Meta le llega igual; sin ella, todo como antes.
"""
from unittest.mock import MagicMock, patch

import pytest

from app import courier_notify
from app.services import chatwoot_plantillas

PLANTILLA = {"inbox_id": 1, "idioma": "es"}


@pytest.fixture
def mundo():
    courier = {"id": "m1", "name": "Alexander", "phone": "3001234567", "chatwoot_conversation_id": None}
    fake_db, cw, pl = MagicMock(), MagicMock(), MagicMock()
    fake_db.get_courier.return_value = courier
    pl.plantilla_aprobada.return_value = PLANTILLA
    pl.puede_responder.return_value = False
    pl.abrir_conversacion.return_value = "77"
    with patch("app.services.db", fake_db), patch("app.services.chatwoot", cw), \
         patch("app.services.chatwoot_plantillas", pl):
        yield {"courier": courier, "db": fake_db, "cw": cw, "pl": pl}


def _avisar():
    return courier_notify.notify_assignment("m1", order_number="A3-2026-040", clinic="Lacliv",
                                            address="CR 2 8-56", fecha="27/11/2026")


def test_sin_conversacion_abre_una_con_la_plantilla_y_la_vincula(mundo):
    assert _avisar() is True
    args = mundo["pl"].abrir_conversacion.call_args[0]
    assert args[0] == "+573001234567" and args[3] == "recogida_asignada"
    assert args[5] == ["A3-2026-040", "Lacliv", "CR 2 8-56", "27/11/2026"] and args[6] == 1
    mundo["db"].update_courier.assert_called_once_with("m1", {"chatwoot_conversation_id": "77"})


def test_con_conversacion_y_ventana_cerrada_va_la_plantilla(mundo):
    mundo["courier"]["chatwoot_conversation_id"] = "5"
    assert _avisar() is True
    mundo["pl"].enviar.assert_called_once()
    mundo["cw"].send_message.assert_not_called()


def test_con_la_ventana_abierta_va_un_mensaje_normal(mundo):
    """Dentro de las 24 h no se usa la plantilla (es la que cobra Meta)."""
    mundo["courier"]["chatwoot_conversation_id"] = "5"
    mundo["pl"].puede_responder.return_value = True
    assert _avisar() is True
    mundo["cw"].send_message.assert_called_once()
    assert "Nueva recogida asignada" in mundo["cw"].send_message.call_args[0][1]
    mundo["pl"].enviar.assert_not_called()


def test_sin_plantilla_aprobada_todo_sigue_como_antes(mundo):
    mundo["pl"].plantilla_aprobada.return_value = None
    assert _avisar() is False  # sin vínculo: alguien le avisa a mano
    mundo["courier"]["chatwoot_conversation_id"] = "5"
    assert _avisar() is True and mundo["cw"].send_message.called
    mundo["pl"].abrir_conversacion.assert_not_called()


@pytest.mark.parametrize("telefono, esperado", [("3001234567", "+573001234567"), ("+57 300 123 4567", "+573001234567"),
                                                ("573001234567", "+573001234567"), ("6011234567", None), ("", None)])
def test_celular_colombiano(telefono, esperado):
    assert courier_notify._celular(telefono) == esperado


def test_sin_celular_valido_no_abre_nada(mundo):
    mundo["courier"]["phone"] = "601 123"
    assert _avisar() is False
    mundo["pl"].abrir_conversacion.assert_not_called()


def test_si_no_se_puede_consultar_la_plantilla_el_aviso_sale_como_antes(mundo):
    mundo["courier"]["chatwoot_conversation_id"] = "5"
    mundo["pl"].plantilla_aprobada.side_effect = RuntimeError("chatwoot lento")
    assert _avisar() is True
    mundo["cw"].send_message.assert_called_once()


def test_si_chatwoot_falla_la_asignacion_sigue(mundo):
    mundo["pl"].abrir_conversacion.side_effect = RuntimeError("chatwoot caído")
    assert _avisar() is False


# ── El mensaje a Chatwoot (formato de Chatwoot 4.11) ─────────────────────────

def test_la_plantilla_va_con_los_parametros_del_cuerpo_y_sin_vacios():
    cuerpo = chatwoot_plantillas._plantilla("texto", "recogida_asignada", "es", ["A3-1", "", "CR 2", "27/11"])
    assert cuerpo["template_params"] == {"name": "recogida_asignada", "category": "UTILITY", "language": "es",
                                         "processed_params": {"body": {"1": "A3-1", "2": "-", "3": "CR 2", "4": "27/11"}}}


def test_solo_cuenta_una_plantilla_aprobada_del_canal_de_whatsapp(monkeypatch):
    inboxes = {"payload": [
        {"id": 2, "channel_type": "Channel::Telegram", "message_templates": []},
        {"id": 1, "channel_type": "Channel::Whatsapp", "message_templates": [
            {"name": "recogida_asignada", "status": "PENDING", "language": "es"}]}]}
    monkeypatch.setattr(chatwoot_plantillas, "_pedir", lambda *a, **k: inboxes)
    assert chatwoot_plantillas.plantilla_aprobada("recogida_asignada") is None
    inboxes["payload"][1]["message_templates"][0]["status"] = "approved"
    assert chatwoot_plantillas.plantilla_aprobada("recogida_asignada") == {"inbox_id": 1, "idioma": "es"}


def test_abrir_conversacion_reusa_el_contacto_que_ya_existe(monkeypatch):
    llamadas = []

    def pedir(metodo, ruta, cuerpo=None):
        llamadas.append((metodo, ruta, cuerpo))
        if ruta.startswith("/contacts/search"):
            return {"payload": [{"id": 9, "phone_number": "+573001234567",
                                 "contact_inboxes": [{"inbox": {"id": 1}, "source_id": "573001234567"}]}]}
        return {"id": 88}

    monkeypatch.setattr(chatwoot_plantillas, "_pedir", pedir)
    nueva = chatwoot_plantillas.abrir_conversacion("+573001234567", "Alexander", "t", "recogida_asignada", "es",
                                                   ["A3-1"], 1)
    assert nueva == "88"
    crear = [c for c in llamadas if c[1] == "/conversations"][0][2]
    assert crear["source_id"] == "573001234567" and crear["contact_id"] == 9 and crear["status"] == "pending"
    assert not any(c[1] == "/contacts" for c in llamadas)  # no duplica el contacto
