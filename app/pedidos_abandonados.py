"""Cierre de pedidos abandonados (decisión 011, anexo del 2026-10-26).

Un pedido ABIERTO sin actividad hace más de una hora se cierra con las órdenes que el
cliente ya confirmó —esas recogidas siguen en pie: el motorizado ya fue avisado—, se le
avisa al cliente por su canal, y se limpian de su sesión los datos del pedido. Sin esa
limpieza, el pedido siguiente del mismo chat arrastraba al resumen y al borrador de
factura análisis que no eran suyos.

Desde el 2026-11-25 (decisión del usuario, cambia el anexo del 26/10 de la decisión 011)
también se arma el BORRADOR de Alegra, como en el portal y «Nueva Orden»: A3 reportó que
esos pedidos quedaban para facturar a mano, uno a uno (P-2026-017). La forma de pago va
«sin definir» porque el cliente no la confirmó; A3 la revisa antes de emitir.

Lo dispara el cron de Render cada 15 minutos (`POST /api/platform/pedidos/barrido`) y,
de respaldo, el inicio de cualquier turno del bot (`agent._sweep_stale_pedidos`).
Nunca lanza: un pedido que falla no frena a los demás.
"""
import logging
import threading

from app import config, facturar_pedido
from app.services import chatwoot, db, telegram

logger = logging.getLogger(__name__)
HORAS = 1
# El cron y el turno de un cliente lo pueden disparar a la vez (es un solo proceso): sin
# candado, los dos encontraban el mismo pedido y el cliente recibía el aviso dos veces (ERR-187).
_EN_CURSO = threading.Lock()


def texto_aviso(ordenes: int) -> str:
    if ordenes == 1:
        detalle = "la orden que ya confirmaste; esa recogida queda programada"
    else:
        detalle = f"las {ordenes} órdenes que ya confirmaste; esas recogidas quedan programadas"
    return (f"Hola, como pasó más de una hora sin respuesta cerré tu pedido con {detalle}. "
            "Si necesitás otra, me escribís y abrimos un pedido nuevo.")


def _avisar(pedido: dict, ordenes: int) -> bool:
    chat_id = str(pedido.get("external_chat_id") or "")
    if not chat_id or not ordenes:
        return False
    texto = texto_aviso(ordenes)
    try:
        # El transporte según el canal del pedido: whatsapp y chatwoot viajan por Chatwoot.
        if (pedido.get("entry_channel") or "telegram") == "telegram":
            telegram.send_message(chat_id, texto)
        else:
            chatwoot.send_message(chat_id, texto)
        db.save_message(chat_id, texto, "bot")
        return True
    except Exception:  # noqa: BLE001 — el aviso no puede frenar el cierre
        logger.exception("pedidos: no se pudo avisar el cierre de %s a %s", pedido.get("id"), chat_id)
        return False


def _borrador(pedido: dict) -> bool:
    """Arma el borrador del pedido recién cerrado. Nunca lanza: si Alegra falla, el pedido
    queda «cerrado» con el motivo en su historial y se factura desde Pedidos."""
    if not config.ALEGRA_ENABLED:
        return False
    try:
        return facturar_pedido.facturar(db.get_pedido(pedido["id"]) or pedido).get("status") == "facturado"
    except Exception:  # noqa: BLE001
        logger.exception("pedidos: no se pudo armar el borrador del abandonado %s", pedido.get("id"))
        return False


def cerrar_abandonados(horas: int = HORAS) -> dict:
    """Cierra, limpia y avisa. Devuelve cuántos cerró, avisó y fallaron."""
    if not _EN_CURSO.acquire(blocking=False):
        return {"cerrados": 0, "avisados": 0, "fallidos": 0, "en_curso": True}
    try:
        return _cerrar(horas)
    finally:
        _EN_CURSO.release()


def _cerrar(horas: int) -> dict:
    resultado = {"cerrados": 0, "avisados": 0, "fallidos": 0, "facturados": 0}
    try:
        pendientes = db.list_stale_pedidos(horas)
    except Exception as exc:  # noqa: BLE001
        logger.warning("pedidos: falló el barrido de abandonados: %s", exc)
        return {**resultado, "error": str(exc)[:120]}
    for pedido in pendientes:
        pedido_id = pedido.get("id")
        try:
            ordenes = db.list_pedido_requests(pedido_id)
            db.close_pedido(pedido_id, pedido.get("payment_method"))
            if pedido.get("external_chat_id"):
                db.limpiar_pedido_de_sesion(str(pedido["external_chat_id"]))
            facturado = _borrador(pedido)
            # Se avisa SIEMPRE a operaciones, con o sin factura: el cliente nunca confirmó
            # la forma de pago y alguien tiene que saber que este pedido se cerró solo.
            logger.warning(
                "pedidos: %s (%s) cerrado por inactividad tras %sh con %s orden(es) — "
                "revisar con operaciones: el cliente no confirmó el cierre (%s)",
                pedido.get("pedido_number") or pedido_id, pedido.get("external_chat_id"), horas, len(ordenes),
                "borrador armado" if facturado else "SIN borrador: facturar desde Pedidos",
            )
            resultado["cerrados"] += 1
            resultado["facturados"] += facturado
            resultado["avisados"] += _avisar(pedido, len(ordenes))
        except Exception as exc:  # noqa: BLE001
            logger.warning("pedidos: no se pudo cerrar el abandonado %s: %s", pedido_id, exc)
            resultado["fallidos"] += 1
    return resultado
