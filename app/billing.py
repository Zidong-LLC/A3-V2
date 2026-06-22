"""Facturación de órdenes A3 en Alegra (capa de orquestación).

Traduce una orden cerrada (su `event_payload`, tal como lo arma `db.create_request`) a una
factura de Alegra. No hace I/O crudo (eso vive en `app/services/alegra.py`) ni importa
`app/agent.py`. El agente la invoca en el cierre de orden bajo `ALEGRA_ENABLED`.

Fuente de verdad del total: `event_payload["profile"]["price_adjustment"]["total"]`, el mismo
que A3 persiste y muestra en el dashboard. Las líneas se arman para que el total cuadre.
"""

import re

from app.services import alegra


def _slug(text: str) -> str:
    """Código de referencia estable a partir de un nombre, cuando no hay código de catálogo."""
    base = re.sub(r"[^a-z0-9]+", "-", (text or "").strip().lower()).strip("-")
    return f"A3-{base[:40]}" if base else "A3-item"


def _line(code: str | None, name: str, price: int) -> dict:
    return {
        "reference": str(code).strip() if code else _slug(name),
        "name": name or "Análisis",
        "price": int(price or 0),
        "quantity": 1,
    }


def build_invoice_lines(profile_payload: dict | None) -> list[dict]:
    """Convierte el `profile` del event_payload en líneas de factura
    [{reference, name, price, quantity}]. El perfil base se factura con su precio menos las
    pruebas removidas; cada prueba agregada es una línea aparte. Así el total cuadra con
    `price_adjustment.total`. Devuelve [] si no hay nada con precio para facturar."""
    if not profile_payload:
        return []

    base = profile_payload.get("base_profile") or {}
    added = profile_payload.get("added_tests") or []
    removed = profile_payload.get("removed_tests") or []

    removed_total = sum(int(t.get("price") or 0) for t in removed)
    base_price = max(int(base.get("price") or 0) - removed_total, 0)

    lines: list[dict] = []
    if base.get("name") or base.get("code"):
        lines.append(_line(base.get("code"), base.get("name") or "Perfil", base_price))
    for test in added:
        lines.append(_line(test.get("code"), test.get("name"), test.get("price")))

    if not any(line["price"] for line in lines):
        return []
    return lines


def invoice_order(
    client_nit: str,
    client_name: str,
    lines: list[dict],
    date: str,
    client_extra: dict | None = None,
) -> dict | None:
    """Asegura el contacto y los ítems en Alegra y crea la factura (borrador). Devuelve
    {contact_id, invoice_id, number, total} o None si no hay líneas. Propaga AlegraError:
    el llamador (agente) la captura para no romper el cierre de la orden."""
    if not lines or not client_nit:
        return None

    contact = alegra.get_or_create_contact(client_nit, client_name, client_extra)
    contact_id = contact.get("id")

    invoice_items = []
    for line in lines:
        item = alegra.get_or_create_item(line["reference"], line["name"], line["price"])
        invoice_items.append({"id": item.get("id"), "quantity": line["quantity"], "price": line["price"]})

    invoice = alegra.create_invoice(contact_id, invoice_items, date)
    return {
        "contact_id": contact_id,
        "invoice_id": invoice.get("id"),
        "number": (invoice.get("numberTemplate") or {}).get("fullNumber") or invoice.get("number"),
        "total": invoice.get("total"),
    }
