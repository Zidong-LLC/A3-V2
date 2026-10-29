"""Pedidos y Solicitudes en UNA página: cada pedido con sus órdenes adentro (ERR-194).

El usuario no entendía qué era cada pantalla: eran la misma tabla `requests` con tres
nombres y sin un número en común. Ahora el pedido (lo que se factura) encabeza sus órdenes
(cada recogida, editable como en Solicitudes) y lo que no tiene pedido va en su grupo.
"""
import time
from unittest.mock import patch

from app import pedidos_vista

PEDIDOS = [
    {"id": "p-viejo", "pedido_number": "P-2026-001", "status": "facturado", "created_at": "2026-10-20",
     "client_name": "Vet Viejo", "orders": [], "orders_count": 0, "entry_channel": "telegram"},
    {"id": "p-nuevo", "pedido_number": "P-2026-007", "status": "cerrado", "created_at": "2026-10-29",
     "client_name": "Vet A", "orders": [{"id": "r1"}], "orders_count": 1, "entry_channel": "portal",
     "payment_method": "transferencia"},
    {"id": "p-abierto", "pedido_number": "P-2026-005", "status": "abierto", "created_at": "2026-10-25",
     "client_name": "Vet B", "orders": [], "orders_count": 0, "entry_channel": "telegram"},
]
FILAS = [
    {"id": "r1", "pedido_id": "p-nuevo", "order_number": "A3-2026-101", "patient_name": "Luna",
     "service_area": "route_scheduling", "status": "received", "requested_at": "2026-10-29T10:00",
     "clients": {"clinic_name": "Vet A"}, "exam_type": "Hemograma"},
    {"id": "r2", "pedido_id": None, "order_number": "A3-2026-090", "patient_name": "Toby",
     "service_area": "route_scheduling", "status": "assigned", "requested_at": "2026-10-28T10:00",
     "clients": {"clinic_name": "Vet C"}},
    {"id": "r3", "pedido_id": None, "service_area": "new_client", "status": "received",
     "requested_at": "2026-10-28T09:00", "clients": None},
]


def test_agrupa_por_pedido_deja_sueltas_y_saca_lo_que_no_es_recogida():
    vista = pedidos_vista.agrupar([dict(p) for p in PEDIDOS], FILAS)

    assert [p["id"] for p in vista["pedidos"]] == ["p-abierto", "p-nuevo", "p-viejo"]
    nuevo = vista["pedidos"][1]
    assert [f["id"] for f in nuevo["filas"]] == ["r1"]
    assert nuevo["canal"] == "Portal del cliente" and nuevo["estado"] == "Cerrado sin facturar"
    assert [f["id"] for f in vista["sueltas"]] == ["r2"]  # r3 es un alta de cliente, no una orden
    assert (vista["abiertos"], vista["sin_facturar"]) == (1, 1)


def _pagina(rol):
    from app.main import app
    from tests.test_dashboard import _base_context

    app.config["TESTING"] = True
    c = app.test_client()
    with c.session_transaction() as s:
        s.update({"dashboard_authenticated": True, "dashboard_username": "u", "dashboard_user_id": None,
                  "dashboard_role": rol, "dashboard_full_name": "U", "dashboard_role_checked": time.time() + 3600})
    contexto = _base_context(requests=FILAS, couriers_options=[{"id": "m1", "name": "César"}],
                             request_status_options=[{"value": "received", "label": "Recibida"},
                                                     {"value": "assigned", "label": "Asignada"}])
    with patch("app.dashboard.build_dashboard_context", return_value=contexto), \
         patch("app.dashboard.db.list_pedidos_for_dashboard", return_value=[dict(p) for p in PEDIDOS]):
        return c.get("/pedidos").get_data(as_text=True)


def test_la_pagina_muestra_cada_pedido_con_sus_ordenes_editables():
    html = _pagina("administrador")

    assert "Pedido P-2026-007" in html and "A3-2026-101" in html and "Luna" in html
    assert 'class="cell-select request-courier-select" data-request-id="r1"' in html
    assert "Órdenes sin pedido" in html and "A3-2026-090" in html
    assert 'data-request-id="r3"' not in html
    assert '<i data-lucide="clipboard-plus"></i>Nueva Orden</a>' in html
    assert html.index("P-2026-005") < html.index("P-2026-007")  # el abierto primero


def test_quien_solo_consulta_ve_las_ordenes_sin_poder_editarlas():
    html = _pagina("procesamiento")  # Solicitudes y Pedidos en consulta

    assert "A3-2026-101" in html and "Luna" in html
    assert 'class="cell-select request-courier-select"' not in html
    assert '<i data-lucide="clipboard-plus"></i>Nueva Orden</a>' not in html
    assert 'data-pedido-close="' not in html


def test_la_auxiliar_administrativa_ve_pedidos_aunque_no_tenga_solicitudes():
    html = _pagina("auxiliar_administrativa")  # Pedidos consulta, Facturación gestión

    assert "Pedido P-2026-007" in html
    assert 'data-pedido-close="p-nuevo"' in html  # factura desde acá, como antes
    assert 'class="cell-select request-courier-select"' not in html
