"""Tests de la facturación en Alegra (app/billing.py + hook en app/agent.py).

No tocan la red: la API de Alegra y Supabase se mockean. La validación real contra una
cuenta Alegra de Colombia se hace con scripts (ver tasks/todo.md), no aquí.
"""
import pytest

from app import billing, agent
from app.services import alegra


# ----------------------------- build_invoice_lines -----------------------------

def test_lineas_perfil_ajustado_cuadran_con_total():
    """base (100000) - removido (8000) + agregado (12000) = 104000."""
    profile = {
        "base_profile": {"code": "PERF-01", "name": "Perfil Prequirúrgico", "price": 100000},
        "added_tests": [{"code": "T-12", "name": "Creatinina", "price": 12000}],
        "removed_tests": [{"code": "T-08", "name": "TP", "price": 8000}],
    }
    lines = billing.build_invoice_lines(profile)
    assert sum(l["price"] for l in lines) == 104000
    assert lines[0]["price"] == 92000  # base ajustado por la prueba removida
    assert lines[0]["reference"] == "PERF-01"
    assert all(l["quantity"] == 1 for l in lines)


def test_sin_profile_no_genera_lineas():
    assert billing.build_invoice_lines(None) == []


def test_profile_sin_precio_no_genera_lineas():
    profile = {"base_profile": {"name": "Sin precio", "price": 0}, "added_tests": [], "removed_tests": []}
    assert billing.build_invoice_lines(profile) == []


def test_reference_se_deriva_del_nombre_cuando_falta_codigo():
    profile = {"base_profile": {"name": "Hemograma Completo", "price": 35000},
               "added_tests": [], "removed_tests": []}
    lines = billing.build_invoice_lines(profile)
    assert lines[0]["reference"].startswith("A3-")


# ----------------------------- hook _try_invoice_in_alegra -----------------------------

def _order_and_response():
    order_info = {
        "request_id": "req-1",
        "event_payload": {"profile": {
            "base_profile": {"code": "PERF-01", "name": "Perfil", "price": 50000},
            "added_tests": [], "removed_tests": [],
        }},
    }
    ai_response = {"intent": "route_scheduling",
                   "captured_fields": {"tax_id": "900123456", "clinic_name": "Vet Demo"}}
    return order_info, ai_response


def test_hook_factura_y_guarda_evento(monkeypatch):
    captured = {}
    monkeypatch.setattr(billing, "invoice_order",
                        lambda *a, **k: {"invoice_id": "9", "contact_id": "2", "number": "1", "total": 50000})
    monkeypatch.setattr(agent.db, "create_request_event",
                        lambda rid, etype, payload: captured.update({"rid": rid, "etype": etype, "payload": payload}))
    order_info, ai_response = _order_and_response()
    agent._try_invoice_in_alegra(order_info, ai_response)
    assert captured["rid"] == "req-1"
    assert captured["etype"] == "alegra_invoiced"
    assert captured["payload"]["invoice_id"] == "9"


def test_hook_no_rompe_si_alegra_falla(monkeypatch):
    eventos = []
    def boom(*a, **k):
        raise alegra.AlegraError("Alegra POST /invoices -> HTTP 400")
    monkeypatch.setattr(billing, "invoice_order", boom)
    monkeypatch.setattr(agent.db, "create_request_event", lambda *a, **k: eventos.append(a))
    order_info, ai_response = _order_and_response()
    agent._try_invoice_in_alegra(order_info, ai_response)  # no debe lanzar
    assert eventos == []  # no se guarda evento si falló


def test_hook_no_factura_orden_sin_perfil(monkeypatch):
    llamadas = []
    monkeypatch.setattr(billing, "invoice_order", lambda *a, **k: llamadas.append(a))
    monkeypatch.setattr(agent.db, "create_request_event", lambda *a, **k: None)
    order_info = {"request_id": "req-2", "event_payload": {}}  # sin profile
    ai_response = {"intent": "route_scheduling", "captured_fields": {"tax_id": "900"}}
    agent._try_invoice_in_alegra(order_info, ai_response)
    assert llamadas == []  # sin líneas no se intenta facturar


def test_contact_lookup_retries_without_dv_before_create(monkeypatch):
    llamadas = []

    def fake_request(method, path, body=None):
        llamadas.append((method, path, body))
        if method == "GET" and "53115419-1" in path:
            return []
        if method == "GET" and "53115419" in path:
            return [{"id": "3", "name": "Animal Pets", "identification": "53115419"}]
        raise AssertionError("no debe crear un contacto duplicado")

    monkeypatch.setattr(alegra, "_request", fake_request)

    contact = alegra.get_or_create_contact("53115419-1", "Animal Pets")

    assert contact["id"] == "3"
    assert [call[0] for call in llamadas] == ["GET", "GET"]
