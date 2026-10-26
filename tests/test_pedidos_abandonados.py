"""Anexo 2026-10-26 de la decisión 011: el pedido abandonado se cierra con lo confirmado,
se le avisa al cliente por su canal y la sesión queda limpia para el pedido siguiente."""
from unittest.mock import MagicMock

import pytest

from app import agent, pedidos_abandonados
from app.services import db

PEDIDO = {"id": "ped-1", "pedido_number": "P-2026-001", "status": "abierto",
          "external_chat_id": "chat-9", "payment_method": None, "entry_channel": "telegram"}


@pytest.fixture
def base(monkeypatch):
    registro = {"cerrados": [], "limpiados": [], "telegram": [], "chatwoot": [], "historial": []}
    monkeypatch.setattr(db, "list_stale_pedidos", lambda horas=1, limit=20: [PEDIDO])
    monkeypatch.setattr(db, "list_pedido_requests", lambda pid: [{"order_number": "A3-1"}, {"order_number": "A3-2"}])
    monkeypatch.setattr(db, "close_pedido", lambda pid, pago=None: registro["cerrados"].append(pid))
    monkeypatch.setattr(db, "limpiar_pedido_de_sesion", lambda chat: registro["limpiados"].append(chat) or True)
    monkeypatch.setattr(db, "save_message", lambda chat, texto, rol: registro["historial"].append((chat, rol, texto)))
    monkeypatch.setattr(pedidos_abandonados.telegram, "send_message", lambda chat, texto: registro["telegram"].append((chat, texto)))
    monkeypatch.setattr(pedidos_abandonados.chatwoot, "send_message", lambda chat, texto: registro["chatwoot"].append((chat, texto)))
    return registro


def test_cierra_limpia_la_sesion_y_avisa_por_telegram(base):
    resultado = pedidos_abandonados.cerrar_abandonados()
    assert resultado == {"cerrados": 1, "avisados": 1, "fallidos": 0}
    assert base["cerrados"] == ["ped-1"] and base["limpiados"] == ["chat-9"]
    chat, texto = base["telegram"][0]
    assert chat == "chat-9" and "más de una hora" in texto and "2 órdenes" in texto and "quedan programadas" in texto
    assert base["historial"] == [("chat-9", "bot", texto)]  # el aviso queda en el historial del chat
    assert base["chatwoot"] == []


def test_por_whatsapp_el_aviso_viaja_por_chatwoot(base, monkeypatch):
    monkeypatch.setattr(db, "list_stale_pedidos", lambda horas=1, limit=20: [dict(PEDIDO, entry_channel="whatsapp")])
    pedidos_abandonados.cerrar_abandonados()
    assert base["chatwoot"][0][0] == "chat-9" and base["telegram"] == []


def test_una_sola_orden_habla_en_singular():
    assert "la orden que ya confirmaste; esa recogida queda programada" in pedidos_abandonados.texto_aviso(1)


def test_sin_ordenes_cierra_sin_avisar(base, monkeypatch):
    monkeypatch.setattr(db, "list_pedido_requests", lambda pid: [])
    assert pedidos_abandonados.cerrar_abandonados() == {"cerrados": 1, "avisados": 0, "fallidos": 0}
    assert base["telegram"] == [] and base["limpiados"] == ["chat-9"]


def test_si_el_aviso_falla_el_pedido_queda_cerrado_igual(base, monkeypatch):
    def explota(*_a):
        raise RuntimeError("telegram caído")
    monkeypatch.setattr(pedidos_abandonados.telegram, "send_message", explota)
    assert pedidos_abandonados.cerrar_abandonados() == {"cerrados": 1, "avisados": 0, "fallidos": 0}


def test_limpiar_pedido_de_sesion_saca_solo_las_claves_del_pedido(monkeypatch):
    guardado = {}
    tabla = MagicMock()
    tabla.select.return_value.eq.return_value.execute.return_value.data = [{"captured_fields": {
        "clinic_name": "Norte", "_pedido_id": "ped-1", "_pedido_profiles": [{"x": 1}],
        "_pedido_ordenes": [{}], "_pedido_awaiting_payment": True, "_pedido_offer_pending": True}}]
    tabla.update.side_effect = lambda payload: guardado.update(payload) or tabla
    tabla.eq.return_value.execute.return_value = None
    monkeypatch.setattr(db._client, "table", lambda nombre: tabla)
    assert db.limpiar_pedido_de_sesion("chat-9") is True
    assert guardado["captured_fields"] == {"clinic_name": "Norte"}


def test_un_pedido_nuevo_no_arrastra_los_perfiles_del_viejo(monkeypatch):
    """El cliente vuelve después del cierre por inactividad y abre otra orden: el resumen y la
    factura del pedido nuevo no pueden traer los análisis del pedido anterior."""
    campos = {"_pedido_id": "ped-viejo", "_pedido_profiles": [{"viejo": 1}], "_pedido_ordenes": [{"n": "A3-1"}],
              "patient_name": "Luna"}
    ai_response = {"intent": "route_scheduling", "phase": "fase_6_cierre", "reply": "Listo",
                   "captured_fields": campos, "message_mode": "normal"}
    session = {"client_id": "c1", "captured_fields": {}, "phase_current": "fase_5_confirmacion"}
    monkeypatch.setattr(agent, "PEDIDOS_ENABLED", True)
    monkeypatch.setattr(agent, "ALEGRA_ENABLED", False)
    monkeypatch.setattr(agent, "_current_pedido_id", lambda chat, s: "ped-nuevo")
    monkeypatch.setattr(agent.db, "create_request", lambda *a, **k: {
        "id": "r1", "order_number": "A3-9", "event_payload": {"profile": {"nuevo": 1, "total_estimated": 1000}}})
    monkeypatch.setattr(agent.db, "get_courier_for_client", lambda cid: {"name": "Javier", "phone": "1"})
    monkeypatch.setattr(agent, "_record_favorite_profile", lambda *a, **k: None)
    salida = agent._finalize_request("chat-9", session, ai_response, False, "fase_5_confirmacion")
    fields = salida["captured_fields"]
    assert fields["_pedido_id"] == "ped-nuevo"
    assert fields["_pedido_profiles"] == [{"nuevo": 1, "total_estimated": 1000}]
    assert [o["order_number"] for o in fields["_pedido_ordenes"]] == ["A3-9"]


def test_el_cron_cierra_por_la_api_con_token(monkeypatch):
    from app.main import app

    app.config["TESTING"] = True
    monkeypatch.setattr(pedidos_abandonados, "cerrar_abandonados", lambda horas=1: {"cerrados": 2, "avisados": 2, "fallidos": 0})
    c = app.test_client()
    assert c.post("/api/platform/pedidos/barrido").status_code == 401
    r = c.post("/api/platform/pedidos/barrido", headers={"X-Platform-Token": "test-platform-token"})
    assert r.status_code == 200 and r.get_json()["cerrados"] == 2
