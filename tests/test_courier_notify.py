"""Aviso al motorizado por Chatwoot (decision 2026-08-31; pedido de A3, llamadas 1-4).

El vinculo es la conversacion de Chatwoot del motorizado: Chatwoot la entrega por el
canal que tenga esa conversacion (WhatsApp cuando se conecte el numero, Telegram, etc.).
Sin vinculo no se avisa, y el fallo del aviso jamas frena la asignacion.
"""
from unittest.mock import patch

from app.courier_notify import notify_assignment


def test_con_vinculo_el_aviso_sale_por_chatwoot():
    with patch("app.services.db.get_courier",
               return_value={"id": "c-1", "chatwoot_conversation_id": "42"}), \
         patch("app.services.chatwoot.send_message") as enviar:
        ok = notify_assignment("c-1", order_number="A3-2026-009", clinic="Vet Prueba",
                               address="CL 1 # 2-3", fecha="2026-09-01")
    assert ok
    conversacion, texto = enviar.call_args.args
    assert conversacion == "42"
    assert "A3-2026-009" in texto and "Vet Prueba" in texto and "CL 1 # 2-3" in texto
    assert "Nueva recogida" in texto


def test_la_reasignacion_lo_dice():
    with patch("app.services.db.get_courier",
               return_value={"id": "c-1", "chatwoot_conversation_id": "42"}), \
         patch("app.services.chatwoot.send_message") as enviar:
        notify_assignment("c-1", order_number="A3-1", reasignada=True)
    assert "reasignada" in enviar.call_args.args[1]


def test_sin_vinculo_no_se_avisa_y_no_es_error():
    with patch("app.services.db.get_courier", return_value={"id": "c-1"}), \
         patch("app.services.chatwoot.send_message") as enviar:
        assert notify_assignment("c-1", order_number="A3-1") is False
    enviar.assert_not_called()


def test_el_fallo_del_aviso_no_explota():
    with patch("app.services.db.get_courier", side_effect=RuntimeError("base caida")):
        assert notify_assignment("c-1") is False


def test_sin_courier_no_hace_nada():
    assert notify_assignment(None) is False


def test_el_endpoint_guarda_el_vinculo_y_valida_que_sea_numero():
    from app.main import app

    app.config["TESTING"] = True
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["dashboard_authenticated"] = True
    with patch("app.dashboard.db.update_courier", return_value=True) as editar:
        ok = client.post("/api/dashboard/courier",
                         json={"courier_id": "c-1", "chatwoot_conversation_id": "42"})
        mal = client.post("/api/dashboard/courier",
                          json={"courier_id": "c-1", "chatwoot_conversation_id": "no-numero"})
    assert ok.status_code == 200
    editar.assert_called_once_with("c-1", {"chatwoot_conversation_id": "42"})
    assert mal.status_code == 400
