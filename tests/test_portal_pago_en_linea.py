"""Pago en línea desde el portal con un clic (pedido de A3, 2026-11-25).

A3: el link de Wompi «funciona, pero copiando y pegando el link en otra ventana, lo que no es
fácil para el usuario». Ahora: ventanita con «Pagar ahora con Wompi» al registrar la orden,
columna «Pago» en Solicitudes y botón en Notificaciones.
"""
from unittest.mock import patch

import pytest

from app.main import app

CLIENTE = "11111111-1111-1111-1111-111111111111"
LINK = "https://checkout.wompi.co/l/SAuzgN"
ORDENES = [
    {"id": "r1", "order_number": "A3-2026-040", "pedido_id": "p1", "status": "assigned", "patient_name": "Leon"},
    {"id": "r2", "order_number": "A3-2026-041", "pedido_id": "p2", "status": "assigned", "patient_name": "Roku"},
    {"id": "r3", "order_number": "A3-2026-042", "pedido_id": None, "status": "assigned", "patient_name": "Yommy"},
]
PAGOS = {"p1": {"status": "pending", "url": LINK}, "p2": {"status": "approved", "url": "https://x/l/OK"}}


@pytest.fixture
def client():
    app.config["TESTING"] = True
    c = app.test_client()
    with c.session_transaction() as s:
        s["portal_user_id"], s["portal_role"], s["portal_client_id"] = "u1", "client", CLIENTE
    return c


def _lista(client, ordenes=ORDENES, pagos=PAGOS):
    with patch("app.portal.client_requests.portal_db.list_client_requests", return_value=ordenes), \
         patch("app.portal.client_requests.pagos_db.por_pedidos", return_value=pagos), \
         patch("app.services.portal_db.count_unread_notifications", return_value=0):
        return client.get("/portal/mis/solicitudes").get_data(as_text=True)


def test_al_registrar_con_pago_en_linea_sale_la_ventanita_con_el_boton(client):
    with client.session_transaction() as s:
        s["portal_pago"] = {"url": LINK, "orden": "A3-2026-040", "total": 12000}
    html = _lista(client)
    assert 'id="pago-modal"' in html
    assert f'href="{LINK}" target="_blank"' in html
    assert "Pagar ahora con Wompi" in html and "$12.000" in html
    assert "Pagar después" in html


def test_la_ventanita_sale_una_sola_vez(client):
    with client.session_transaction() as s:
        s["portal_pago"] = {"url": LINK, "orden": "A3-2026-040", "total": 12000}
    _lista(client)
    assert 'id="pago-modal"' not in _lista(client)


def test_la_columna_pago_deja_pagar_lo_pendiente_y_marca_lo_pagado(client):
    html = _lista(client)
    assert 'id="pago-modal"' not in html
    assert html.count(f'href="{LINK}" target="_blank"') == 1  # solo la orden pendiente
    assert "Pagado" in html


def test_si_falla_leer_los_pagos_la_lista_sale_igual(client):
    with patch("app.portal.client_requests.portal_db.list_client_requests", return_value=ORDENES), \
         patch("app.portal.client_requests.pagos_db.por_pedidos", side_effect=RuntimeError("caída")), \
         patch("app.services.portal_db.count_unread_notifications", return_value=0):
        r = client.get("/portal/mis/solicitudes")
    assert r.status_code == 200 and "A3-2026-040" in r.get_data(as_text=True)


def test_en_notificaciones_el_link_es_un_boton(client):
    avisos = [{"id": "n1", "title": "Paga en línea tu orden A3-2026-040", "body": LINK,
               "created_at": "2026-11-25T15:00:00+00:00", "read_at": None, "result_id": None},
              {"id": "n2", "title": "Solicitud registrada", "body": "Paciente Leon — Hemoparásitos",
               "created_at": "2026-11-25T15:00:00+00:00", "read_at": None, "result_id": None}]
    with patch("app.portal.client_results.portal_db.list_notifications", return_value=avisos), \
         patch("app.services.portal_db.count_unread_notifications", return_value=2):
        html = client.get("/portal/mis/notificaciones").get_data(as_text=True)
    assert f'href="{LINK}" target="_blank"' in html and "Pagar en línea" in html
    assert "Paciente Leon — Hemoparásitos" in html
