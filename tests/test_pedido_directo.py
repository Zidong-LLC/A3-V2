"""Órdenes del portal y de «Nueva Orden»: abren su pedido y dejan el borrador (ERR-194).

Antes quedaban sueltas: no aparecían en Pedidos y nada les armaba la factura. Decisión del
usuario (2026-10-29): que generen su borrador igual que el bot. El pedido se abre, recibe la
orden, se cierra y se factura en el mismo momento; nunca queda «abierto».
"""
from unittest.mock import MagicMock, patch

import pytest

from app import pedido_directo

CREADA = {"request_id": "r1", "order_number": "A3-2026-101", "event_payload": {}}


@pytest.fixture
def base(monkeypatch):
    llamadas = []
    monkeypatch.setattr("app.pedido_directo.db.create_pedido",
                        lambda cid, chat, entry_channel: llamadas.append(("abre", cid, chat, entry_channel))
                        or {"id": "ped-1", "pedido_number": "P-2026-007"})
    monkeypatch.setattr("app.pedido_directo.db.close_pedido",
                        lambda pid, pago: llamadas.append(("cierra", pid, pago)))
    monkeypatch.setattr("app.pedido_directo.db.get_pedido", lambda pid: {"id": pid, "client_id": "c1"})
    monkeypatch.setattr("app.pedido_directo.config.ALEGRA_ENABLED", True)
    return llamadas


def _registrar(**extra):
    return pedido_directo.registrar(client_id="c1", chat_id="portal:c1", canal_pedido="portal",
                                    session={"client_id": "c1", "channel": "portal"},
                                    fields={"payment_method": "transferencia", **extra})


def test_abre_crea_la_orden_dentro_cierra_y_factura(base):
    with patch("app.pedido_directo.db.create_request", return_value=dict(CREADA)) as crear, \
         patch("app.pedido_directo.facturar_pedido.facturar",
               return_value={"status": "facturado", "invoice": "B-55", "warning": None}) as facturar:
        r = _registrar()

    assert crear.call_args.kwargs["pedido_id"] == "ped-1"
    assert base == [("abre", "c1", "portal:c1", "portal"), ("cierra", "ped-1", "transferencia")]
    facturar.assert_called_once_with({"id": "ped-1", "client_id": "c1"})
    assert r["pedido_number"] == "P-2026-007" and r["factura"]["invoice"] == "B-55"


def test_si_la_orden_falla_el_pedido_no_queda_abierto(base):
    with patch("app.pedido_directo.db.create_request", side_effect=RuntimeError("caída")), \
         pytest.raises(RuntimeError):
        _registrar()

    assert ("cierra", "ped-1", "transferencia") in base


def test_sin_alegra_queda_cerrado_con_aviso(base, monkeypatch):
    monkeypatch.setattr("app.pedido_directo.config.ALEGRA_ENABLED", False)
    with patch("app.pedido_directo.db.create_request", return_value=dict(CREADA)), \
         patch("app.pedido_directo.facturar_pedido.facturar") as facturar:
        r = _registrar()

    facturar.assert_not_called()
    assert r["factura"]["status"] == "cerrado" and "desactivado" in r["factura"]["warning"]


def test_si_no_se_puede_abrir_el_pedido_la_orden_entra_suelta(monkeypatch):
    monkeypatch.setattr("app.pedido_directo.db.create_pedido", MagicMock(side_effect=RuntimeError("x")))
    cerrar = MagicMock()
    monkeypatch.setattr("app.pedido_directo.db.close_pedido", cerrar)
    with patch("app.pedido_directo.db.create_request", return_value=dict(CREADA)) as crear:
        r = _registrar()

    assert crear.call_args.kwargs["pedido_id"] is None
    cerrar.assert_not_called()
    assert r["pedido_number"] is None and r["factura"] is None


def test_facturar_usa_las_lineas_de_cada_orden_y_marca_el_pedido(monkeypatch):
    from app import facturar_pedido

    monkeypatch.setattr("app.facturar_pedido.db.list_pedido_requests", lambda pid: [{"id": "r1", "patient_name": "Luna"}])
    monkeypatch.setattr("app.facturar_pedido.db.get_pedido_profiles", lambda pid, con_request_id: [("r1", {"code": "952"})])
    monkeypatch.setattr("app.facturar_pedido.db.get_client_by_id", lambda cid: {"tax_id": "900", "clinic_name": "Vet"})
    monkeypatch.setattr("app.facturar_pedido.billing.build_invoice_lines", lambda perfil, paciente: [{"paciente": paciente}])
    marcar = MagicMock()
    monkeypatch.setattr("app.facturar_pedido.db.mark_pedido_invoiced", marcar)
    with patch("app.facturar_pedido.billing.invoice_order", return_value={"invoice_id": 9, "number": "B-9"}) as alegra:
        r = facturar_pedido.facturar({"id": "ped-1", "client_id": "c1"})

    assert alegra.call_args.args[2] == [{"paciente": "Luna"}]
    marcar.assert_called_once_with("ped-1", "9")
    assert r == {"status": "facturado", "invoice": "B-9", "warning": None}


def test_el_aviso_de_resultados_no_usa_pedidos_del_portal():
    from app.services import portal_db

    consulta = MagicMock()
    for m in ("select", "eq", "order", "limit", "not_", "is_", "in_"):
        getattr(consulta, m).return_value = consulta
    consulta.not_ = consulta
    consulta.execute.return_value.data = []
    cliente = MagicMock()
    cliente.table.return_value = consulta
    with patch.object(portal_db, "_client", cliente):
        portal_db.chat_for_client("c1")

    consulta.in_.assert_called_once_with("entry_channel", ["telegram", "chatwoot", "whatsapp"])


def test_nueva_orden_avisa_el_pedido_y_el_borrador(monkeypatch):
    from app.main import app

    monkeypatch.setattr("app.dashboard.DASHBOARD_ADMIN_USER", "admin")
    monkeypatch.setattr("app.dashboard.DASHBOARD_ADMIN_PASSWORD", "secret")
    creada = {**CREADA, "pedido_number": "P-2026-007",
              "factura": {"status": "facturado", "invoice": "B-55", "warning": None}}
    cliente = {"id": "c1", "clinic_name": "Vet A", "address": "Calle 1", "phone": "300"}
    with patch("app.dashboard.db.get_client_by_id", return_value=cliente), \
         patch("app.dashboard.db.list_clients_with_assignment", return_value=[cliente]), \
         patch("app.dashboard.db.list_catalog_profiles", return_value=[]), \
         patch("app.dashboard.db.list_catalog_tests", return_value=[]), \
         patch("app.dashboard.orders.resolve_catalog_selection", return_value={"exam_type": "Hemograma"}), \
         patch("app.dashboard.pedido_directo.registrar", return_value=creada) as registrar:
        app.config["TESTING"] = True
        c = app.test_client()
        c.post("/login", data={"username": "admin", "password": "secret"})
        r = c.post("/solicitudes/nueva", data={"client_id": "c1", "patient_name": "Luna", "test_codes": ["1903"]})

    assert registrar.call_args.kwargs["canal_pedido"] == "manual"
    assert "/pedidos" in r.headers["Location"]
    assert "P-2026-007" in r.headers["Location"] and "B-55" in r.headers["Location"]
