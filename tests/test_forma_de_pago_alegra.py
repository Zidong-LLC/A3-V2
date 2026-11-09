"""ERR-199 (2026-11-09): Alegra rechazaba el borrador del pedido con «La forma de pago es
obligatoria». Ahora el borrador lleva la forma de pago que eligió el cliente. Decisión del
usuario: contraentrega es efectivo; «en línea» es el link de Wompi. Los valores son los que
la cuenta real devuelve en sus propias facturas (`paymentMethod` contado/crédito,
`paymentForm` el medio)."""
import pytest

from app import billing, facturar_pedido
from app.services import alegra

EFECTIVO = {"paymentMethod": "CASH", "paymentForm": "CASH"}
EN_LINEA = {"paymentMethod": "CASH", "paymentForm": "DEBIT_TRANSFER"}
SIN_DEFINIR = {"paymentMethod": "CASH", "paymentForm": "INSTRUMENT_NOT_DEFINED"}


@pytest.mark.parametrize("elegido,esperado", [
    ("contraentrega", EFECTIVO), ("Contra entrega", EFECTIVO), ("efectivo", EFECTIVO),
    ("pago_linea", EN_LINEA), ("pago en línea", EN_LINEA), ("transferencia", EN_LINEA),
    (None, SIN_DEFINIR), ("", SIN_DEFINIR), ("a convenir", SIN_DEFINIR),
])
def test_cada_forma_de_pago_tiene_su_par_en_alegra(elegido, esperado):
    assert billing.invoice_payment(elegido) == esperado


def test_el_borrador_viaja_con_forma_de_pago_y_sigue_siendo_borrador(monkeypatch):
    cuerpos = []
    monkeypatch.setattr(alegra, "_request", lambda m, p, body=None: cuerpos.append((m, p, body)) or {"id": 9})
    monkeypatch.setattr(alegra, "ALEGRA_PRODUCTION", False)
    alegra.create_invoice(7, [{"id": 1, "quantity": 1, "price": 16000}], "2026-11-09", pago=EN_LINEA)
    metodo, ruta, cuerpo = cuerpos[0]
    assert (metodo, ruta) == ("POST", "/invoices")
    assert cuerpo["paymentMethod"] == "CASH" and cuerpo["paymentForm"] == "DEBIT_TRANSFER"
    assert cuerpo["status"] == "draft", "nunca se emite: la forma de pago no cambia el guardrail"


def test_sin_forma_de_pago_el_cuerpo_queda_como_antes(monkeypatch):
    cuerpos = []
    monkeypatch.setattr(alegra, "_request", lambda m, p, body=None: cuerpos.append(body) or {"id": 9})
    alegra.create_invoice(7, [], "2026-11-09")
    assert "paymentMethod" not in cuerpos[0] and "paymentForm" not in cuerpos[0]


def _facturar(monkeypatch, pedido):
    visto = {}
    monkeypatch.setattr(facturar_pedido.db, "list_pedido_requests",
                        lambda pid: [{"id": "r1", "patient_name": "Ignacio"}])
    monkeypatch.setattr(facturar_pedido.db, "get_pedido_profiles", lambda pid, con_request_id=False: [
        ("r1", {"base_profile": {"code": None, "name": "Perfil personalizado (1 análisis)", "price": 0},
                "added_tests": [{"code": "1101", "name": "Cuadro Hemático Completo", "price": 16000}],
                "removed_tests": []})])
    monkeypatch.setattr(facturar_pedido.db, "get_client_by_id",
                        lambda cid: {"id": cid, "tax_id": "900123456", "clinic_name": "Vet Demo"})
    monkeypatch.setattr(facturar_pedido.db, "mark_pedido_invoiced", lambda *a: visto.setdefault("marcado", a))
    monkeypatch.setattr(alegra, "get_or_create_contact", lambda *a, **k: {"id": "7"})
    monkeypatch.setattr(alegra, "get_or_create_item", lambda ref, name, price: {"id": f"i-{ref}"})
    monkeypatch.setattr(alegra, "create_invoice",
                        lambda cid, items, date, **kw: visto.update(pago=kw.get("pago")) or {"id": "55"})
    return facturar_pedido.facturar(pedido), visto


def test_el_pedido_pagado_en_linea_se_factura_como_transferencia(monkeypatch):
    resultado, visto = _facturar(monkeypatch, {"id": "p1", "client_id": "c1", "payment_method": "pago_linea"})
    assert resultado["status"] == "facturado" and visto["pago"] == EN_LINEA
    assert visto["marcado"] == ("p1", "55")


def test_el_pedido_contraentrega_se_factura_en_efectivo(monkeypatch):
    _, visto = _facturar(monkeypatch, {"id": "p1", "client_id": "c1", "payment_method": "contraentrega"})
    assert visto["pago"] == EFECTIVO


def test_un_pedido_sin_forma_de_pago_igual_se_factura(monkeypatch):
    """Un pedido abandonado se cierra solo y no tiene forma de pago: antes Alegra lo rechazaba."""
    resultado, visto = _facturar(monkeypatch, {"id": "p1", "client_id": "c1", "payment_method": None})
    assert resultado["status"] == "facturado" and visto["pago"] == SIN_DEFINIR


# ── El cierre por el chat ───────────────────────────────────────────────────

def test_el_cierre_del_chat_factura_con_la_forma_de_pago_que_contesto_el_cliente(monkeypatch):
    """La forma de pago se contesta al cerrar el pedido y no vive en el estado de la orden."""
    from app import agent

    visto = {}
    monkeypatch.setattr(agent.db, "close_pedido", lambda pid, pago: None)
    monkeypatch.setattr(agent.db, "list_pedido_requests", lambda pid: [{"id": "r-1"}])
    monkeypatch.setattr(agent.db, "mark_pedido_invoiced", lambda *a, **k: None)
    monkeypatch.setattr(agent, "ALEGRA_ENABLED", True)
    monkeypatch.setattr(agent.pagos, "link_para_pedido", lambda *a, **k: None)
    monkeypatch.setattr(agent.billing, "build_invoice_lines", lambda perfil, paciente=None: [{"price": 16000}])
    monkeypatch.setattr(agent.billing, "invoice_order",
                        lambda nit, *a, **k: visto.update(pago=k.get("payment_method")) or {"invoice_id": "55"})
    campos = {"_pedido_id": "ped-1", "tax_id": "900123456", "clinic_name": "Vet Demo",
              "_pedido_profiles": [{"total_estimated": 16000}],
              "_pedido_ordenes": [{"patient_name": "Ignacio", "total": 16000}]}
    agent._close_pedido_turn({"client_id": "c1"}, campos, "pago_linea")
    assert visto["pago"] == "pago_linea"
    assert billing.invoice_payment(visto["pago"]) == EN_LINEA
    assert "payment_method" not in campos, "el estado de la conversación no cambia por facturar"
