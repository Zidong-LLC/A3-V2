"""Aviso al motorizado cuando se le asigna o reasigna una recogida.

Decisión del usuario (2026-08-31), pedida por A3 en las llamadas 1, 2 y 4: el aviso va por
Chatwoot, a la conversación vinculada en la tarjeta del motorizado (columna
`couriers.chatwoot_conversation_id`, migración 032). Sin vínculo no se avisa — igual que
hoy, alguien le avisa a mano. El fallo del aviso NUNCA frena la asignación: se loggea.
"""
import logging

logger = logging.getLogger(__name__)


def _texto(order_number: str, clinic: str, address: str, fecha: str, reasignada: bool) -> str:
    encabezado = "Recogida reasignada a vos" if reasignada else "Nueva recogida asignada"
    lineas = [f"🛵 {encabezado}", f"Orden: {order_number or 's/n'}"]
    if clinic:
        lineas.append(f"Veterinaria: {clinic}")
    if address:
        lineas.append(f"Dirección: {address}")
    if fecha:
        lineas.append(f"Fecha de recogida: {fecha}")
    return "\n".join(lineas)


def notify_assignment(courier_id: str | None, order_number: str = "", clinic: str = "",
                      address: str = "", fecha: str = "", reasignada: bool = False) -> bool:
    """Manda el aviso si el motorizado tiene su conversación de Chatwoot vinculada.
    Devuelve si salió. Imports diferidos para no crear ciclos con la capa db."""
    if not courier_id:
        return False
    try:
        from app.services import chatwoot, db

        courier = db.get_courier(courier_id)
        conversation = str((courier or {}).get("chatwoot_conversation_id") or "").strip()
        if not conversation:
            return False
        chatwoot.send_message(conversation, _texto(order_number, clinic, address, fecha, reasignada))
        return True
    except Exception:  # noqa: BLE001 — el aviso jamás frena la asignación
        logger.exception("No se pudo avisar al motorizado %s", courier_id)
        return False
