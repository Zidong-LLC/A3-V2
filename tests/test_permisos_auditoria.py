"""Huecos de permisos cerrados en la auditoría del 2026-10-19 (docx de perfiles)."""
import pytest

from app import dashboard
from app.main import app


def _cliente(perfil):
    app.config["TESTING"] = True
    c = app.test_client()
    with c.session_transaction() as s:
        s["dashboard_authenticated"] = True
        s["dashboard_username"] = "prueba"
        s["dashboard_role"] = perfil
    return c


@pytest.fixture
def sin_pedido(monkeypatch):
    leidos = []
    monkeypatch.setattr("app.dashboard.db.get_pedido", lambda pid: leidos.append(pid))
    return leidos


def test_recepcion_no_puede_facturar_un_pedido(sin_pedido):
    r = _cliente("recepcion").post("/api/dashboard/pedido-close", json={"pedido_id": "p1", "invoice": True})
    assert r.status_code == 403
    assert sin_pedido == []  # ni siquiera se lee el pedido


def test_recepcion_puede_cerrar_sin_facturar(sin_pedido):
    r = _cliente("recepcion").post("/api/dashboard/pedido-close", json={"pedido_id": "p1"})
    assert r.status_code == 404 and sin_pedido == ["p1"]  # pasó el permiso; el pedido no existe


def test_auxiliar_administrativa_si_factura(sin_pedido):
    r = _cliente("auxiliar_administrativa").post("/api/dashboard/pedido-close",
                                                 json={"pedido_id": "p1", "invoice": True})
    assert r.status_code == 404 and sin_pedido == ["p1"]
    cerrar = _cliente("auxiliar_administrativa").post("/api/dashboard/pedido-close", json={"pedido_id": "p1"})
    assert cerrar.status_code == 403  # Pedidos es solo consulta para ese perfil


def test_doble_clic_no_crea_dos_facturas(sin_pedido):
    dashboard._PEDIDOS_EN_CURSO.add("p1")
    try:
        r = _cliente("administrador").post("/api/dashboard/pedido-close", json={"pedido_id": "p1", "invoice": True})
    finally:
        dashboard._PEDIDOS_EN_CURSO.discard("p1")
    assert r.status_code == 409 and sin_pedido == []


@pytest.fixture
def ficha(monkeypatch):
    cartera = []
    monkeypatch.setattr("app.services.maestros_db.get_client_any",
                        lambda cid: {"id": cid, "clinic_name": "Norte", "tax_id": "900123456-1", "is_active": True})
    monkeypatch.setattr("app.services.maestros_db.courier_de_cliente", lambda cid: None)
    monkeypatch.setattr("app.services.db.list_active_couriers", lambda *a, **k: [])
    monkeypatch.setattr("app.services.audit_db.listar", lambda *a, **k: [])
    monkeypatch.setattr("app.services.portal_db.list_client_requests", lambda *a, **k: [])
    monkeypatch.setattr("app.services.portal_db.list_lab_results", lambda *a, **k: [])
    monkeypatch.setattr("app.services.db.list_cartera", lambda **k: cartera.append(k) or [])
    return cartera


def test_ficha_sin_facturacion_no_muestra_la_cartera(ficha):
    r = _cliente("recepcion").get("/clientes/00000000-0000-0000-0000-000000000001")
    html = r.get_data(as_text=True)
    assert r.status_code == 200
    assert "Estado de cuenta" not in html and "Por cobrar" not in html
    assert ficha == []


def test_ficha_con_facturacion_muestra_la_cartera(ficha):
    r = _cliente("auxiliar_administrativa").get("/clientes/00000000-0000-0000-0000-000000000001")
    assert "Estado de cuenta" in r.get_data(as_text=True)
    assert ficha == [{"client_nit": "900123456-1"}]


def test_historial_de_usuarios_solo_para_el_administrador(monkeypatch):
    monkeypatch.setattr("app.services.audit_db.listar", lambda *a, **k: [{"action": "update"}])
    assert _cliente("recepcion").get("/api/dashboard/historial?entidad=user&id=u1").status_code == 403
    assert _cliente("recepcion").get("/api/dashboard/historial?entidad=courier&id=m1").status_code == 200
    assert _cliente("administrador").get("/api/dashboard/historial?entidad=user&id=u1").status_code == 200
