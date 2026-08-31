"""Los 3 tapones de WhatsApp (auditoría de lanzamiento, llamada 9).

El canal de origen deja de mentir (migración 031), el aviso de resultados sale por el
canal real del cliente, y el webhook de Chatwoot exige su secreto.
"""
from unittest.mock import MagicMock, patch


def _get_test_client():
    from app.main import app

    app.config["TESTING"] = True
    return app.test_client()


# ── Tapón 1: entry_channel ya no reetiqueta chatwoot/whatsapp ────────────────

def _entry_channel_de(canal):
    from app.services import db as dbs

    cliente = MagicMock()
    with patch.object(dbs, "_client", cliente):
        dbs.create_request("chat-1", {"client_id": "c-1", "channel": canal},
                           {"intent": "route_scheduling", "captured_fields": {}})
    # create_request inserta varias filas (orden, eventos): se busca la de la orden.
    for llamada in cliente.table.return_value.insert.call_args_list:
        payload = llamada.args[0]
        if isinstance(payload, dict) and "entry_channel" in payload:
            return payload["entry_channel"]
    raise AssertionError("ningun insert llevo entry_channel")


def test_la_orden_conserva_su_canal_real():
    assert _entry_channel_de("telegram") == "telegram"
    assert _entry_channel_de("chatwoot") == "chatwoot"
    assert _entry_channel_de("whatsapp") == "whatsapp"


def test_un_canal_desconocido_cae_a_telegram_y_no_rompe_el_insert():
    assert _entry_channel_de("liveconnect") == "telegram"
    assert _entry_channel_de(None) == "telegram"


# ── Tapón 2: el aviso de resultados sale por el canal del cliente ────────────

def _notificar(canal):
    from app.dashboard_results import _publish_and_notify

    with patch("app.dashboard_results.portal_db.publish_lab_result", return_value={"id": "r-1"}), \
         patch("app.dashboard_results.portal_db.insert_notification"), \
         patch("app.dashboard_results.portal_db.chat_for_client",
               return_value=("chat-9", canal)), \
         patch("app.dashboard_results.telegram.send_message") as tg, \
         patch("app.dashboard_results.chatwoot.send_message") as cw:
        _publish_and_notify({"id": "r-1", "client_id": "c-1", "patient_name": "Rocky",
                             "order_number": "A3-1", "exam_name": "Hemograma"})
    return tg, cw


def test_cliente_de_telegram_recibe_el_aviso_por_telegram():
    tg, cw = _notificar("telegram")
    tg.assert_called_once()
    cw.assert_not_called()


def test_cliente_de_whatsapp_recibe_el_aviso_por_chatwoot():
    """Antes el aviso filtraba channel=telegram: el cliente de WhatsApp no recibía NADA."""
    tg, cw = _notificar("whatsapp")
    cw.assert_called_once()
    tg.assert_not_called()


def test_cliente_de_chatwoot_web_tambien_recibe_por_chatwoot():
    tg, cw = _notificar("chatwoot")
    cw.assert_called_once()
    tg.assert_not_called()


# ── Tapón 3: el webhook de Chatwoot exige su secreto ─────────────────────────

def _post_chatwoot(client, token=None):
    url = "/chatwoot/webhook" + (f"?token={token}" if token else "")
    return client.post(url, json={"event": "message_created", "message_type": "incoming",
                                  "content": "hola", "conversation": {"id": 7}})


def test_sin_el_secreto_el_webhook_rechaza(monkeypatch):
    monkeypatch.setattr("app.main.CHATWOOT_WEBHOOK_SECRET", "s3creto")
    assert _post_chatwoot(_get_test_client()).status_code == 403
    assert _post_chatwoot(_get_test_client(), token="malo").status_code == 403


def test_con_el_secreto_correcto_el_webhook_procesa(monkeypatch):
    monkeypatch.setattr("app.main.CHATWOOT_WEBHOOK_SECRET", "s3creto")
    with patch("app.main._debouncer.submit") as sub:
        r = _post_chatwoot(_get_test_client(), token="s3creto")
    assert r.status_code == 200
    sub.assert_called_once()


def test_setup_webhook_exige_el_secreto_de_telegram(monkeypatch):
    monkeypatch.setattr("app.main.TELEGRAM_WEBHOOK_SECRET", "tg-secreto")
    client = _get_test_client()
    assert client.post("/setup-webhook").status_code == 403


# ── La detección de WhatsApp en el payload ───────────────────────────────────

def test_un_inbox_whatsapp_marca_el_canal_whatsapp(monkeypatch):
    monkeypatch.setattr("app.main.CHATWOOT_WEBHOOK_SECRET", "")
    client = _get_test_client()
    with patch("app.main._debouncer.submit") as sub:
        client.post("/chatwoot/webhook", json={
            "event": "message_created", "message_type": "incoming", "content": "hola",
            "conversation": {"id": 7, "channel": "Channel::Whatsapp"}})
    # el canal viaja en el closure del flush: se verifica ejecutándolo
    flush = sub.call_args.args[2]
    with patch("app.main._process_chatwoot") as proc:
        flush("hola")
    assert proc.call_args.args[2] == "whatsapp"


def test_un_inbox_web_queda_como_chatwoot(monkeypatch):
    monkeypatch.setattr("app.main.CHATWOOT_WEBHOOK_SECRET", "")
    client = _get_test_client()
    with patch("app.main._debouncer.submit") as sub:
        client.post("/chatwoot/webhook", json={
            "event": "message_created", "message_type": "incoming", "content": "hola",
            "conversation": {"id": 7, "channel": "Channel::WebWidget"}})
    flush = sub.call_args.args[2]
    with patch("app.main._process_chatwoot") as proc:
        flush("hola")
    assert proc.call_args.args[2] == "chatwoot"
