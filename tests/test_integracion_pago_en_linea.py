"""Prueba integrada del pago en línea, de punta a punta (2026-11-16, Wompi ya en producción).

Las pruebas por pieza ya existen (`test_pagos_wompi.py`, `test_cobro_pedidos.py`). Esta las
encadena con el código real de cada capa y una sola memoria compartida, sin red ni modelo:
la orden nace → se pide el link a Wompi → Wompi avisa el pago firmado → Pedidos lo muestra.
Lo único simulado es el transporte: la respuesta HTTP de Wompi, la base y el envío al chat.
"""
import hashlib
import json
from unittest.mock import MagicMock, patch
from urllib.parse import unquote_plus

import pytest

from app import agent, pagos, pedido_directo
from app.main import app
from app.services import db, pagos_db, wompi
from tests.test_dashboard_new_request import CLIENTE, PERFIL, _form

SECRETO = "prod_events_solo_para_el_test"


def _cliente_web(sesion=True):
    app.config["TESTING"] = True
    c = app.test_client()
    if sesion:
        with c.session_transaction() as s:
            s.update({"dashboard_authenticated": True, "dashboard_username": "ana", "dashboard_role": "recepcion"})
    return c


def _evento(link, centavos, estado="APPROVED"):
    tx = {"id": "tx-9", "status": estado, "amount_in_cents": centavos, "payment_link_id": link}
    cadena = f"{tx['id']}{estado}{centavos}1700000000{SECRETO}"
    return {"event": "transaction.updated", "data": {"transaction": tx}, "timestamp": 1700000000,
            "signature": {"properties": ["transaction.id", "transaction.status", "transaction.amount_in_cents"],
                          "checksum": hashlib.sha256(cadena.encode()).hexdigest()}}


@pytest.fixture
def mundo(monkeypatch):
    m = {"pedidos": {}, "pagos": [], "wompi": [], "chat": [], "notas": []}

    # Wompi como en producción: encendido, sin candado por NIT, contra la URL real.
    monkeypatch.setattr(pagos, "WOMPI_ENABLED", True)
    monkeypatch.setattr(pagos, "WOMPI_ONLY_NITS", set())
    monkeypatch.setattr(wompi, "WOMPI_PRIVATE_KEY", "prv_prod_solo_para_el_test")
    monkeypatch.setattr(wompi, "WOMPI_BASE_URL", "https://production.wompi.co/v1")
    monkeypatch.setattr(wompi, "WOMPI_EVENTS_SECRET", SECRETO)

    def _wompi_responde(req, timeout=None):
        m["wompi"].append({"url": req.full_url, "cuerpo": json.loads(req.data), "llave": req.get_header("Authorization")})
        cuerpo = json.dumps({"data": {"id": f"LINK{len(m['wompi'])}"}}).encode()
        return MagicMock(__enter__=lambda s: MagicMock(read=lambda: cuerpo), __exit__=lambda *a: False)
    monkeypatch.setattr(wompi.urllib.request, "urlopen", _wompi_responde)

    # Pagos y pedidos en memoria, con la misma forma que las tablas.
    def _crear_pago(pedido_id, link, centavos, url):
        m["pagos"].append({"id": f"pg-{len(m['pagos']) + 1}", "pedido_id": pedido_id, "payment_link_id": link,
                           "amount_in_cents": centavos, "url": url, "status": "pending"})
    monkeypatch.setattr(pagos_db, "crear", _crear_pago)
    monkeypatch.setattr(pagos_db, "por_link", lambda link: next((p for p in m["pagos"] if p["payment_link_id"] == link), None))
    monkeypatch.setattr(pagos_db, "actualizar", lambda pid, estado, tx, crudo: next(
        p for p in m["pagos"] if p["id"] == pid).update(status=estado, transaction_id=tx))
    monkeypatch.setattr(pagos_db, "por_pedidos", lambda ids: {p["pedido_id"]: p for p in m["pagos"] if p["pedido_id"] in ids})

    def _abrir(client_id, chat_id, entry_channel=None):
        pid = f"ped-{len(m['pedidos']) + 1}"
        m["pedidos"][pid] = {"id": pid, "pedido_number": f"P-2026-90{len(m['pedidos']) + 1}", "client_id": client_id,
                             "external_chat_id": chat_id, "entry_channel": entry_channel, "status": "abierto",
                             "payment_method": None, "alegra_invoice_id": None, "created_at": "2026-11-16T10:00:00"}
        return {"id": pid, "pedido_number": m["pedidos"][pid]["pedido_number"]}
    monkeypatch.setattr(db, "create_pedido", _abrir)
    monkeypatch.setattr(db, "close_pedido", lambda pid, pago=None: m["pedidos"][pid].update(status="cerrado", payment_method=pago))
    monkeypatch.setattr(db, "get_pedido", lambda pid: dict(m["pedidos"][pid]) if pid in m["pedidos"] else None)
    monkeypatch.setattr(db, "list_pedido_requests", lambda pid: [{}])
    monkeypatch.setattr(db, "create_request", lambda **k: {
        "request_id": "req-1", "order_number": "A3-2026-900",
        "event_payload": {"profile": {"total_estimated": 90000}}})
    monkeypatch.setattr(db, "get_client_by_id", lambda cid: dict(CLIENTE))
    monkeypatch.setattr(db, "list_clients_with_assignment", lambda *a, **k: [dict(CLIENTE)])
    monkeypatch.setattr(db, "list_catalog_profiles", lambda *a, **k: [dict(PERFIL)])
    monkeypatch.setattr(db, "list_catalog_tests", lambda *a, **k: [])
    monkeypatch.setattr(db, "list_couriers", lambda *a, **k: [])
    monkeypatch.setattr(db, "find_catalog_profile", lambda code: dict(PERFIL))
    monkeypatch.setattr(db, "get_tests_by_codes_or_names", lambda codes: [])
    monkeypatch.setattr(db, "save_message", lambda *a, **k: None)
    monkeypatch.setattr(pedido_directo.config, "ALEGRA_ENABLED", False)
    monkeypatch.setattr(agent, "ALEGRA_ENABLED", False)
    monkeypatch.setattr(pagos.chatwoot, "send_message", lambda chat, texto: m["chat"].append((chat, texto)))
    monkeypatch.setattr(pagos.chatwoot, "send_private_note", lambda chat, texto: m["notas"].append((chat, texto)))
    return m


def _pantalla_pedidos(mundo):
    from tests.test_dashboard import _base_context

    pedidos = [{**p, "client_name": CLIENTE["clinic_name"], "orders": [], "orders_count": 1}
               for p in mundo["pedidos"].values()]
    with patch("app.dashboard.build_dashboard_context",
               return_value=_base_context(requests=[], couriers_options=[], request_status_options=[])), \
         patch("app.dashboard.db.list_pedidos_for_dashboard", return_value=pedidos), \
         patch("app.dashboard.db.facturas_de_pedidos", return_value={}):
        return _cliente_web().get("/pedidos").get_data(as_text=True)


def test_una_orden_cargada_en_recepcion_se_cobra_en_linea_de_punta_a_punta(mundo):
    # 1. Recepción carga la orden con «pago en línea».
    r = _cliente_web().post("/solicitudes/nueva", data=_form(payment_method="pago_linea"))
    assert r.status_code in (301, 302)

    # 2. Se pidió UN link a Wompi producción: un solo uso, en pesos, por el total exacto.
    assert len(mundo["wompi"]) == 1
    pedido = mundo["wompi"][0]
    assert pedido["url"] == "https://production.wompi.co/v1/payment_links"
    assert pedido["llave"] == "Bearer prv_prod_solo_para_el_test"
    assert pedido["cuerpo"]["amount_in_cents"] == 9000000 and pedido["cuerpo"]["currency"] == "COP"
    assert pedido["cuerpo"]["single_use"] is True

    # 3. El link vuelve a quien cargó la orden, y queda guardado como pendiente.
    assert "https://checkout.wompi.co/l/LINK1" in unquote_plus(r.headers["Location"])
    assert [(p["status"], p["amount_in_cents"]) for p in mundo["pagos"]] == [("pending", 9000000)]

    # 4. Pedidos lo muestra sin pagar y deja copiar el link.
    html = _pantalla_pedidos(mundo)
    assert "Link enviado, sin pagar" in html and "$90.000" in html and "Copiar link de pago" in html

    # 5. Wompi avisa el pago aprobado, firmado con el secreto de eventos.
    r = _cliente_web(sesion=False).post("/webhooks/wompi", json=_evento("LINK1", 9000000))
    assert r.status_code == 200 and r.get_json()["resultado"] == "approved"

    # 6. Pedidos lo muestra pagado y ya no ofrece el link.
    html = _pantalla_pedidos(mundo)
    assert "Pagado en línea" in html and "data-pago-link=" not in html

    # 7. Wompi reintenta el mismo aviso: no cambia nada ni se pide otro link.
    r = _cliente_web(sesion=False).post("/webhooks/wompi", json=_evento("LINK1", 9000000))
    assert r.get_json()["resultado"] == "repetido" and len(mundo["wompi"]) == 1


def test_un_pedido_del_chat_recibe_el_link_al_cerrar_y_la_confirmacion_al_pagar(mundo):
    """El camino que nunca se llegó a ver en vivo: el link sale solo en el mensaje de cierre."""
    abierto = db.create_pedido("cli-1", "77", "whatsapp")
    campos = {"_pedido_id": abierto["id"], "clinic_name": CLIENTE["clinic_name"],
              "_pedido_ordenes": [{"patient_name": "Lola", "total": 16000}, {"patient_name": "Toby", "total": 24000}]}

    salida = agent._close_pedido_turn({"client_id": "cli-1"}, campos, "pago_linea")

    assert "https://checkout.wompi.co/l/LINK1" in salida["reply"], "el link va en el mismo mensaje del cierre"
    assert mundo["wompi"][0]["cuerpo"]["amount_in_cents"] == 4000000, "por el total de las dos órdenes"
    assert mundo["pedidos"][abierto["id"]]["status"] == "cerrado"

    r = _cliente_web(sesion=False).post("/webhooks/wompi", json=_evento("LINK1", 4000000))
    assert r.get_json()["resultado"] == "approved"
    assert mundo["chat"] and mundo["chat"][0][0] == "77" and "Recibimos tu pago" in mundo["chat"][0][1]
    assert "$40.000" in mundo["chat"][0][1]
    assert mundo["notas"] and "APROBADO" in mundo["notas"][0][1], "Contabilidad lo ve en la conversación"


def test_un_aviso_falsificado_no_marca_el_pedido_como_pagado(mundo):
    _cliente_web().post("/solicitudes/nueva", data=_form(payment_method="pago_linea"))
    falso = _evento("LINK1", 9000000)
    falso["signature"]["checksum"] = "0" * 64

    r = _cliente_web(sesion=False).post("/webhooks/wompi", json=falso)

    assert r.status_code == 401 and mundo["pagos"][0]["status"] == "pending"
    assert "Link enviado, sin pagar" in _pantalla_pedidos(mundo)


def test_si_pagan_otro_monto_no_se_da_por_pagado(mundo):
    _cliente_web().post("/solicitudes/nueva", data=_form(payment_method="pago_linea"))
    with patch("app.pagos.notify_error") as alerta:
        r = _cliente_web(sesion=False).post("/webhooks/wompi", json=_evento("LINK1", 100000))
    assert r.get_json()["resultado"] == "monto_distinto" and alerta.called
    assert mundo["pagos"][0]["status"] == "mismatch"
    assert "Pagó un monto distinto" in _pantalla_pedidos(mundo)


def test_contraentrega_no_toca_wompi(mundo):
    _cliente_web().post("/solicitudes/nueva", data=_form(payment_method="contraentrega"))
    assert mundo["wompi"] == [] and mundo["pagos"] == []
    assert "data-pago-estado=" not in _pantalla_pedidos(mundo)
