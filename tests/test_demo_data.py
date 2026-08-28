"""Vista de ejemplo (?demo=1): datos en memoria que NO tocan la base."""
from unittest.mock import patch

from app import demo_data


def _get_test_client():
    from app.main import app

    app.config["TESTING"] = True
    return app.test_client()


def _login(client):
    with client.session_transaction() as sess:
        sess["dashboard_authenticated"] = True
        sess["dashboard_username"] = "admin"


def _contexto():
    from tests.test_dashboard import _base_context

    return _base_context(client_type_options={}, vat_regime_options={},
                         couriers_options=[{"id": "c-1", "name": "Javier"}])


# ── Los datos ────────────────────────────────────────────────────────────────

def test_las_solicitudes_de_ejemplo_traen_lo_que_la_tabla_pinta():
    filas = demo_data.requests()
    assert len(filas) == 10
    for fila in filas:
        for campo in ("id", "requested_at", "clients", "pickup_address", "sample_count",
                      "exam_type", "priority", "status", "assigned_courier_id"):
            assert campo in fila, campo
        assert fila["id"].startswith("demo-")


def test_usa_los_motorizados_reales_para_que_el_desplegable_los_muestre():
    filas = demo_data.requests(couriers=[{"id": "real-1", "name": "Javier"}])
    asignados = {f["assigned_courier_id"] for f in filas if f["assigned_courier_id"]}
    assert asignados == {"real-1"}


def test_hay_una_solicitud_sin_motorizado_para_ver_ese_estado():
    filas = demo_data.requests()
    sin_asignar = [f for f in filas if f["status"] == "error_pending_assignment"]
    assert sin_asignar and sin_asignar[0]["assigned_courier_id"] is None
    assert sin_asignar[0]["scheduled_pickup_date"] is None


def test_los_pedidos_de_ejemplo_cubren_los_tres_estados():
    pedidos = demo_data.pedidos()
    assert {p["status"] for p in pedidos} == {"abierto", "cerrado", "facturado"}
    assert all(p["orders_count"] == len(p["orders"]) for p in pedidos)
    assert all(p["id"].startswith("demo-") for p in pedidos)


def test_solo_los_facturados_tienen_factura():
    for pedido in demo_data.pedidos():
        tiene = bool(pedido["alegra_invoice_id"])
        assert tiene == (pedido["status"] == "facturado")


def test_el_conteo_por_estado_suma_todas_las_filas():
    filas = demo_data.requests()
    assert sum(demo_data.request_status_counts(filas).values()) == len(filas)


# ── La pantalla ──────────────────────────────────────────────────────────────

def test_solicitudes_con_demo_no_consulta_la_base():
    client = _get_test_client()
    _login(client)
    with patch("app.dashboard.build_dashboard_context", return_value=_contexto()), \
         patch("app.dashboard.db.list_pedidos_for_dashboard") as consulta:
        cuerpo = client.get("/solicitudes?demo=1").get_data(as_text=True)
    consulta.assert_not_called()
    assert "Vista de ejemplo" in cuerpo
    assert "Veterinaria Piscis" in cuerpo


def test_pedidos_con_demo_no_consulta_la_base():
    client = _get_test_client()
    _login(client)
    with patch("app.dashboard.build_dashboard_context", return_value=_contexto()), \
         patch("app.dashboard.db.list_pedidos_for_dashboard") as consulta:
        cuerpo = client.get("/pedidos?demo=1").get_data(as_text=True)
    consulta.assert_not_called()
    assert "PED-2026-100" in cuerpo


def test_sin_demo_las_pantallas_siguen_con_los_datos_reales():
    client = _get_test_client()
    _login(client)
    with patch("app.dashboard.build_dashboard_context", return_value=_contexto()), \
         patch("app.dashboard.db.list_pedidos_for_dashboard", return_value=[]) as consulta:
        cuerpo = client.get("/pedidos").get_data(as_text=True)
    consulta.assert_called_once()
    assert "PED-2026-100" not in cuerpo
    assert "Ver con datos de ejemplo" in cuerpo
