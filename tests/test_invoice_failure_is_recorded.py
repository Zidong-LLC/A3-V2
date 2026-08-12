"""Ninguna orden puede quedar sin facturar sin dejar rastro.

Antes un fallo de Alegra solo escribía un warning en el log; si el cliente no
tenía NIT ni siquiera eso. Nadie podía saber después qué órdenes quedaron sin
factura. Ahora todo camino que termine sin factura escribe `alegra_failed`.
"""
from unittest.mock import patch

from app.agent import _try_invoice_in_alegra
from app.services import alegra

ORDER = {"request_id": "req-1", "event_payload": {"profile": {"name": "Perfil X"}}}
LINES = [{"reference": "A1", "name": "Hemograma", "price": 30000, "quantity": 1}]


def _run(ai_response, lines=LINES, invoice_result=None, invoice_side_effect=None):
    with patch("app.agent.billing.build_invoice_lines", return_value=lines), \
         patch("app.agent.billing.invoice_order",
               return_value=invoice_result, side_effect=invoice_side_effect), \
         patch("app.agent.db.create_request_event") as mock_event:
        _try_invoice_in_alegra(ORDER, ai_response)
    return mock_event


def test_client_without_nit_is_recorded():
    """El caso que antes no dejaba ni un log."""
    mock_event = _run({"captured_fields": {"clinic_name": "Vet Uno"}})

    mock_event.assert_called_once()
    request_id, event_type, payload = mock_event.call_args[0]
    assert request_id == "req-1"
    assert event_type == "alegra_failed"
    assert payload["reason"] == "cliente_sin_nit"


def test_no_billable_lines_is_recorded():
    mock_event = _run({"captured_fields": {"tax_id": "900123456"}}, lines=[])

    assert mock_event.call_args[0][1] == "alegra_failed"
    assert mock_event.call_args[0][2]["reason"] == "sin_lineas_facturables"


def test_alegra_error_is_recorded():
    mock_event = _run(
        {"captured_fields": {"tax_id": "900123456"}},
        invoice_side_effect=alegra.AlegraError("503 service unavailable"),
    )

    assert mock_event.call_args[0][1] == "alegra_failed"
    payload = mock_event.call_args[0][2]
    assert payload["reason"] == "error_alegra"
    assert "503" in payload["detail"]


def test_successful_invoice_is_recorded_as_invoiced():
    mock_event = _run(
        {"captured_fields": {"tax_id": "900123456"}},
        invoice_result={"invoice_id": 42, "number": "FV-1", "total": 30000},
    )

    assert mock_event.call_args[0][1] == "alegra_invoiced"


def test_failure_to_record_never_breaks_the_order_closing():
    """Si ni siquiera se puede escribir el evento, el cierre sigue adelante."""
    with patch("app.agent.billing.build_invoice_lines", return_value=LINES), \
         patch("app.agent.billing.invoice_order", side_effect=alegra.AlegraError("boom")), \
         patch("app.agent.db.create_request_event", side_effect=RuntimeError("db caída")):
        _try_invoice_in_alegra(ORDER, {"captured_fields": {"tax_id": "900123456"}})
