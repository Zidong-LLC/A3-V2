"""Pagos en línea de los pedidos (tabla `pedido_payments`, migración 041)."""
from datetime import datetime, timezone

from app.services.db import _client


def crear(pedido_id: str, link_id: str, centavos: int, url: str) -> None:
    _client.table("pedido_payments").insert({
        "pedido_id": pedido_id, "payment_link_id": link_id, "amount_in_cents": centavos, "url": url,
    }).execute()


def por_pedidos(pedido_ids: list) -> dict:
    """{pedido_id: su pago más reciente}. Un pedido puede tener varios links (uno vencido o
    rechazado y otro nuevo): manda el último, salvo que haya uno aprobado."""
    ids = [str(i) for i in pedido_ids if i]
    if not ids:
        return {}
    filas = (_client.table("pedido_payments")
             .select("pedido_id, status, amount_in_cents, url, created_at, updated_at")
             .in_("pedido_id", ids).order("created_at").execute()).data or []
    ultimo: dict = {}
    for fila in filas:
        previo = ultimo.get(fila["pedido_id"])
        if not previo or previo.get("status") != "approved":
            ultimo[fila["pedido_id"]] = fila
    return ultimo


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
