"""Facturación de órdenes A3 en Alegra (capa de orquestación).

Traduce una orden cerrada (su `event_payload`, tal como lo arma `db.create_request`) a una
factura de Alegra. No hace I/O crudo (eso vive en `app/services/alegra.py`) ni importa
`app/agent.py`. El agente la invoca en el cierre de orden bajo `ALEGRA_ENABLED`.

Fuente de verdad del total: `event_payload["profile"]["price_adjustment"]["total"]`, el mismo
que A3 persiste y muestra en el dashboard. Las líneas se arman para que el total cuadre.
"""

import re

from app.services import alegra


# Estados de factura de Alegra → etiqueta en español para el dashboard.
INVOICE_STATUS_LABELS = {
    "draft": "Borrador",
    "open": "Abierta",
    "closed": "Pagada",
    "paid": "Pagada",
    "void": "Anulada",
    "cancelled": "Anulada",
    "canceled": "Anulada",
}


def _money(value) -> int:
    try:
        return int(round(float(value or 0)))
    except (TypeError, ValueError):
        return 0


def _client_nit(client: dict) -> str:
    """Extrae el NIT/identificación del contacto, con dígito de verificación si viene."""
    if not isinstance(client, dict):
        return ""
    obj = client.get("identificationObject")
    if isinstance(obj, dict):
        number = str(obj.get("number") or "").strip()
        dv = str(obj.get("dv") or "").strip()
        if number:
            return f"{number}-{dv}" if dv else number
    return str(client.get("identification") or "").strip()


def invoice_to_row(invoice: dict, request_id: str | None = None, origin: str | None = None) -> dict:
    """Mapea una factura cruda de Alegra a la fila que consume el dashboard. Puro y
    defensivo: la forma del objeto de Alegra varía según plan/estado. `request_id` y
    `origin` se cruzan desde nuestros `request_events` (la factura de Alegra no los trae)."""
    invoice = invoice or {}
    client = invoice.get("client") if isinstance(invoice.get("client"), dict) else {}
    number_template = invoice.get("numberTemplate") if isinstance(invoice.get("numberTemplate"), dict) else {}
    status = str(invoice.get("status") or "").strip().lower()
    stamp = invoice.get("stamp") if isinstance(invoice.get("stamp"), dict) else {}
    return {
        "invoice_id": str(invoice.get("id") or ""),
        "number": number_template.get("fullNumber") or invoice.get("number") or "-",
        "date": str(invoice.get("date") or "")[:10] or "-",
        "due_date": str(invoice.get("dueDate") or "")[:10] or "-",
        "client_name": client.get("name") or "Cliente sin nombre",
        "client_nit": _client_nit(client) or "-",
        "document_type": number_template.get("documentType") or invoice.get("documentType") or "Factura de venta",
        "number_template": number_template.get("prefix") or number_template.get("text") or "-",
        "subtotal": _money(invoice.get("subtotal")),
        "tax": _money(invoice.get("tax")),
        "total": _money(invoice.get("total")),
        "status": status or "draft",
        "status_label": INVOICE_STATUS_LABELS.get(status, status.capitalize() or "Borrador"),
        "is_stamped": bool(stamp.get("cufe") or stamp.get("legalStatus") == "STAMPED_AND_ACCEPTED"),
        "request_id": request_id or "",
        "origin": origin or "Agente",
        "pdf_url": alegra.get_invoice_pdf_url(invoice),
    }


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
