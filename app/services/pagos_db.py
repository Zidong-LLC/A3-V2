"""Pagos en línea de los pedidos (tabla `pedido_payments`, migración 041)."""
from datetime import datetime, timezone

from app.services.db import _client


def crear(pedido_id: str, link_id: str, centavos: int, url: str) -> None:
    _client.table("pedido_payments").insert({
        "pedido_id": pedido_id, "payment_link_id": link_id, "amount_in_cents": centavos, "url": url,
    }).execute()


def por_link(link_id: str | None) -> dict | None:
    if not link_id:
        return None
    filas = _client.table("pedido_payments").select("*").eq("payment_link_id", link_id).limit(1).execute().data
    return filas[0] if filas else None


def actualizar(pago_id: str, estado: str, transaccion: str | None, crudo: dict) -> None:
    _client.table("pedido_payments").update({
        "status": estado, "transaction_id": transaccion, "raw": crudo,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", pago_id).execute()
