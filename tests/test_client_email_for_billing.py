"""El correo del cliente tiene que llegar a Alegra: es por donde la DIAN entrega la factura.

Antes de `clients.email`, `_client_email` estaba declarado en state.py pero nadie lo escribía,
así que TODO contacto creado en Alegra iba sin correo. Estos tests fijan el cable completo:
la columna llega a `_store_client_context` y de ahí al `extra` de `get_or_create_contact`.
"""
from unittest.mock import patch

import pytest

from app import agent


def test_client_context_carries_the_email():
    fields = {}
    agent._store_client_context(fields, {
        "clinic_name": "Veterinaria San Roque", "address": "Calle 45 # 12-34",
        "phone": "3001234567", "tax_id": "900123456-7", "email": "facturacion@sanroque.com",
    })
    assert fields["_client_email"] == "facturacion@sanroque.com"
    assert fields["tax_id"] == "900123456-7"


def test_client_without_email_does_not_break_the_context():
    """Solo 197 de 800 clientes tienen correo: la mayoría sigue el camino de siempre."""
    fields = {}
    agent._store_client_context(fields, {"clinic_name": "Vet Sin Correo", "tax_id": "900999999-1"})
    assert fields["_client_email"] == ""
    assert fields["_client_found"] is True


def _invoice_with(fields: dict) -> dict | None:
    """Corre `_try_invoice_in_alegra` con Alegra mockeada y devuelve el `extra` que recibió."""
    captured = {}

    def fake_invoice_order(nit, name, lines, date, extra):
        captured["extra"] = extra
        captured["nit"] = nit
        return {"invoice_id": "inv-1"}

    order_info = {"request_id": "req-1", "event_payload": {"profile": {"code": "401", "name": "Perfil", "price": 40000}}}
    ai_response = {"captured_fields": fields}
    with patch("app.billing.invoice_order", side_effect=fake_invoice_order), \
         patch("app.billing.build_invoice_lines", return_value=[{"id": 1, "price": 40000}]), \
         patch("app.services.db.create_request_event"):
        agent._try_invoice_in_alegra(order_info, ai_response)
    return captured


def test_email_reaches_alegra_when_the_client_has_one():
    captured = _invoice_with({
        "tax_id": "900123456-7", "clinic_name": "Veterinaria San Roque",
        "_client_email": "facturacion@sanroque.com", "_client_phone": "3001234567",
    })
    assert captured["extra"]["email"] == "facturacion@sanroque.com"
    assert captured["extra"]["phone"] == "3001234567"


def test_missing_email_is_omitted_not_sent_empty():
    """`_try_invoice_in_alegra` filtra los vacíos: Alegra no debe recibir email=''."""
    captured = _invoice_with({
        "tax_id": "900123456-7", "clinic_name": "Vet Sin Correo",
        "_client_email": "", "_client_phone": "3001234567",
    })
    assert "email" not in captured["extra"]
    assert captured["extra"]["phone"] == "3001234567"


@pytest.mark.parametrize("field", ["_client_email", "_client_phone"])
def test_billing_never_breaks_the_close(field):
    """La facturación es complementaria: ningún dato faltante puede tumbar el cierre."""
    fields = {"tax_id": "900123456-7", "clinic_name": "Vet", field: None}
    captured = _invoice_with(fields)
    assert captured["nit"] == "900123456-7"
