"""
Pedidos en la plataforma: listado y cierre manual.

El pedido solo existía dentro del agente — el dashboard no conocía la palabra. Eso dejaba sin
respaldo humano al barrido automático: como corre de forma oportunista (sin scheduler), un
pedido abandonado sin tráfico posterior quedaba abierto e **invisible**. El comentario del
código llegaba a decir que "queda visible en el dashboard igual, que es la red" — una red que
no estaba construida.

Lo que estos tests protegen es el DINERO del cierre manual: que no se facture dos veces, que
cerrar y facturar sigan siendo pasos separados, y que un fallo de Alegra deje el pedido
'cerrado' y no 'facturado' — esa diferencia es lo único que después permite encontrar los
pedidos sin factura.
"""
import pytest

from app import dashboard as dash


PEDIDO_ABIERTO = {"id": "ped-1", "pedido_number": "P-2026-001", "status": "abierto",
                  "client_id": "cli-1", "payment_method": None}
PEDIDO_CERRADO = dict(PEDIDO_ABIERTO, id="ped-2", pedido_number="P-2026-002", status="cerrado")
PEDIDO_FACTURADO = dict(PEDIDO_ABIERTO, id="ped-3", status="facturado")

PEDIDOS = {p["id"]: p for p in (PEDIDO_ABIERTO, PEDIDO_CERRADO, PEDIDO_FACTURADO)}


@pytest.fixture
def cliente(monkeypatch):
    from app.main import app

    reg = {"cerrados": [], "facturados": [], "invoice_calls": []}
    monkeypatch.setattr(dash.db, "get_pedido", lambda pid: PEDIDOS.get(pid))
    monkeypatch.setattr(dash.db, "close_pedido",
                        lambda pid, pago=None: reg["cerrados"].append((pid, pago)))
    monkeypatch.setattr(dash.db, "mark_pedido_invoiced",
                        lambda pid, inv: reg["facturados"].append((pid, inv)))
    # Devuelve (request_id, profile): cada línea de la factura lleva el paciente de SU orden.
    monkeypatch.setattr(dash.db, "get_pedido_profiles",
                        lambda pid, con_request_id=False: [
                            ("req-1", {"base_profile": {"code": "1101", "name": "Hemo", "price": 14000},
                                       "added_tests": [], "total_estimated": 14000})])
    monkeypatch.setattr(dash.db, "list_pedido_requests",
                        lambda pid: [{"id": "req-1", "patient_name": "Firulais"}])
    monkeypatch.setattr(dash.db, "get_client_by_id",
                        lambda cid: {"tax_id": "900123456", "clinic_name": "Animal Pets"})
    monkeypatch.setattr(dash.billing, "build_invoice_lines",
                        lambda perfil, paciente=None: [{"code": "1101", "name": "Hemo", "price": 14000,
                                                        "quantity": 1, "description": paciente}])
    monkeypatch.setattr(dash.billing, "invoice_order",
                        lambda *a, **k: reg["invoice_calls"].append(a) or {"invoice_id": "inv-9", "number": "FE-1"})
    monkeypatch.setattr(dash, "ALEGRA_ENABLED", True)

    app.config["WTF_CSRF_ENABLED"] = False
    with app.test_client() as c:
        with c.session_transaction() as s:
            s["dashboard_authenticated"] = True
            s["dashboard_username"] = "tester"
        c.reg = reg
        yield c


def _cerrar(cliente, **payload):
    return cliente.post("/api/dashboard/pedido-close", json=payload)


def test_cierra_y_factura_un_pedido_abierto(cliente):
    r = _cerrar(cliente, pedido_id="ped-1", invoice=True)
    assert r.status_code == 200
    assert r.get_json()["status"] == "facturado"
    assert cliente.reg["cerrados"] == [("ped-1", None)]
    assert cliente.reg["facturados"] == [("ped-1", "inv-9")]


def test_un_pedido_ya_cerrado_se_factura_sin_volver_a_cerrarlo(cliente):
    r = _cerrar(cliente, pedido_id="ped-2", invoice=True)
    assert r.status_code == 200
    assert cliente.reg["cerrados"] == [], "no debe re-cerrar lo que ya estaba cerrado"
    assert cliente.reg["facturados"] == [("ped-2", "inv-9")]


def test_no_factura_dos_veces(cliente):
    """El guard que evita cobrarle de nuevo al cliente."""
    r = _cerrar(cliente, pedido_id="ped-3", invoice=True)
    assert r.status_code == 400
    assert not cliente.reg["invoice_calls"]


def test_cerrar_sin_facturar_no_llama_a_alegra(cliente):
    """Cerrar y facturar son pasos separados, igual que en el agente."""
    r = _cerrar(cliente, pedido_id="ped-1", invoice=False)
    assert r.get_json()["status"] == "cerrado"
    assert cliente.reg["cerrados"] == [("ped-1", None)]
    assert not cliente.reg["invoice_calls"]


def test_si_alegra_falla_queda_cerrado_pero_no_facturado(cliente, monkeypatch):
    """Esa diferencia es lo único que después permite encontrar los pedidos sin factura."""
    def _explota(*_a, **_k):
        raise RuntimeError("Alegra caído")

    monkeypatch.setattr(dash.billing, "invoice_order", _explota)
    r = _cerrar(cliente, pedido_id="ped-1", invoice=True)
    assert r.status_code == 200
    data = r.get_json()
    assert data["status"] == "cerrado" and "warning" in data
    assert cliente.reg["cerrados"] == [("ped-1", None)]
    assert not cliente.reg["facturados"]


def test_cliente_sin_nit_no_rompe_el_cierre(cliente, monkeypatch):
    monkeypatch.setattr(dash.db, "get_client_by_id", lambda cid: {"clinic_name": "Sin NIT"})
    data = _cerrar(cliente, pedido_id="ped-1", invoice=True).get_json()
    assert data["status"] == "cerrado" and "NIT" in data["warning"]
    assert not cliente.reg["facturados"]


def test_pedido_inexistente_da_404(cliente):
    assert _cerrar(cliente, pedido_id="no-existe", invoice=True).status_code == 404


def test_exige_pedido_id(cliente):
    assert _cerrar(cliente, invoice=True).status_code == 400


def test_exige_sesion():
    from app.main import app

    app.config["WTF_CSRF_ENABLED"] = False
    with app.test_client() as c:
        r = c.post("/api/dashboard/pedido-close", json={"pedido_id": "ped-1"})
    assert r.status_code in (302, 401, 403)
