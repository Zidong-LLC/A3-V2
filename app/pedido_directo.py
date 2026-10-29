"""Pedido de UNA orden para lo que entra por el portal o por «Nueva Orden» del dashboard.

Antes esas órdenes quedaban sueltas: no aparecían en Pedidos y nada les armaba factura (solo
el bot abría pedido). Decisión del usuario (2026-10-29, ERR-194): que generen su propio
borrador igual que el bot. Cada envío es una orden con su forma de pago, así que el pedido
se abre, recibe la orden, se cierra y se factura en el mismo momento; nunca queda «abierto»
(el barrido de abandonados le escribiría a un chat que no existe).
"""
import logging

from app import config, facturar_pedido
from app.services import db

logger = logging.getLogger(__name__)


def _facturar(pedido_id: str) -> dict:
    if not config.ALEGRA_ENABLED:
        return {"status": "cerrado", "invoice": None,
                "warning": "Alegra está desactivado: el pedido quedó cerrado sin facturar."}
    return facturar_pedido.facturar(db.get_pedido(pedido_id) or {"id": pedido_id})


def registrar(*, client_id: str, chat_id: str, canal_pedido: str, session: dict, fields: dict) -> dict | None:
    """Lo mismo que devuelve `db.create_request`, más `pedido_number` y `factura`; None si la
    orden no se pudo crear. Si falla abrir el pedido, la orden entra suelta como antes."""
    try:
        pedido = db.create_pedido(client_id, chat_id, entry_channel=canal_pedido)
    except Exception as exc:  # noqa: BLE001
        logger.warning("pedido directo: no se pudo abrir el pedido (%s); la orden va suelta", exc)
        pedido = None
    pedido_id = (pedido or {}).get("id")
    creada = None
    try:
        creada = db.create_request(
            chat_id=chat_id, session=session, pedido_id=pedido_id,
            ai_response={"intent": "route_scheduling", "captured_fields": fields})
    finally:
        if pedido_id:
            db.close_pedido(pedido_id, fields.get("payment_method"))
    if not creada:
        return None
    creada["pedido_number"] = (pedido or {}).get("pedido_number")
    creada["factura"] = _facturar(pedido_id) if pedido_id else None
    return creada
