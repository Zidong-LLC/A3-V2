"""Emisión automática «según confirmación del pedido» (propuesta del 28/09; decisión 017).

A3 (informe del 25/11): las facturas quedaban en borrador «para manualmente, uno a uno»,
cuando la propuesta decía «pasar de borrador a factura emitida según confirmación del pedido».
El usuario lo aprobó el 2026-11-25. Se emite SOLO lo que el cliente confirmó:

- Contraentrega: apenas el pedido tiene borrador (el cliente eligió cómo paga al cerrar).
- Pago en línea: cuando Wompi aprueba el pago.
- Sin forma de pago (pedido cerrado por inactividad) u otra: queda en BORRADOR para revisar.

Quién se emite solo lo elige A3 en Facturación (tabla `emision_ajustes`, migración 042):
'manual' (nadie, solo el botón; es como nace), 'clientes' (solo los elegidos, para probar) o
'todos'. Por encima, el interruptor general `ALEGRA_EMISSION_ENABLED` de Render (decisión 016):
apagado, no se emite nada, ni con el botón ni solo. Emite por la única puerta,
`emision.emitir`, con todos sus candados (borrador, total > 0, una vez, historial). Corre en
segundo plano: el portal y el aviso de Wompi no esperan a Alegra. Nunca lanza.
"""
import logging
import threading

from app import emision
from app.alerts import notify_error
from app.services import db, emision_ajustes_db, pagos_db

log = logging.getLogger(__name__)


def alcanza(pedido: dict, ajustes: dict) -> bool:
    """¿El modo elegido en Facturación incluye a este cliente?"""
    if ajustes.get("modo") == "todos":
        return True
    if ajustes.get("modo") == "clientes":
        return str(pedido.get("client_id") or "") in ajustes.get("client_ids", [])
    return False


def confirmado(pedido: dict) -> bool:
    """¿El cliente confirmó cómo paga este pedido? Solo entonces se emite sin una persona."""
    forma = str(pedido.get("payment_method") or "").lower()
    if forma == "contraentrega":
        return True
    if forma == "pago_linea":
        pago = pagos_db.por_pedidos([pedido.get("id")]).get(str(pedido.get("id"))) or {}
        return pago.get("status") == "approved"
    return False


def intentar(pedido_id: str, origen: str) -> dict | None:
    """Emite el pedido si corresponde. None si no correspondía; si no, lo que dijo la emisión."""
    try:
        if not emision.activa():
            return None
        ajustes = emision_ajustes_db.leer()
        if ajustes.get("modo") == "manual":
            return None
        pedido = db.get_pedido(pedido_id) or {}
        if pedido.get("status") != "facturado" or not alcanza(pedido, ajustes) or not confirmado(pedido):
            return None
        resultado = emision.emitir(pedido)
        numero = pedido.get("pedido_number") or pedido_id
        if resultado.get("ok"):
            log.info("emision automática: pedido %s emitido como %s (%s)", numero, resultado.get("numero"), origen)
        else:  # queda en borrador; alguien de Facturación tiene que mirarlo
            log.warning("emision automática: pedido %s NO emitido (%s): %s", numero, origen, resultado.get("error"))
            notify_error("emisión automática a la DIAN", RuntimeError(str(resultado.get("error"))),
                         f"pedido {numero} quedó en borrador ({origen})")
        return resultado
    except Exception as exc:  # noqa: BLE001 — el pedido y su borrador ya existen
        log.exception("emision automática: falló el pedido %s (%s)", pedido_id, origen)
        notify_error("emisión automática a la DIAN", exc, f"pedido {pedido_id} ({origen})")
        return {"ok": False, "error": str(exc)[:200]}


def programar(pedido_id: str | None, origen: str) -> None:
    """Lanza `intentar` en segundo plano. Con el interruptor general apagado no lanza nada."""
    if not pedido_id or not emision.activa():
        return
    threading.Thread(target=intentar, args=(str(pedido_id), origen), daemon=True,
                     name=f"emision-{pedido_id}").start()
