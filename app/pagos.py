"""Pago en línea de un pedido con Wompi (propuesta del 28/09, 11 h).

Al cerrar un pedido con «pago en línea» se crea un link de un solo uso por el total y el
bot lo manda por el chat. Wompi avisa el resultado a `/webhooks/wompi`; ahí se valida la
firma, se actualiza el estado y se le confirma al cliente. Con `WOMPI_ENABLED=false` nada
de esto corre y el cierre queda como antes. Si Wompi falla al crear el link, el pedido se
cierra igual y llega el aviso técnico: el cobro lo gestiona Contabilidad.
"""
import logging

from flask import Blueprint, jsonify, request

from app.alerts import notify_error
from app.config import WOMPI_ENABLED, WOMPI_ONLY_NITS
from app.services import chatwoot, db, pagos_db, telegram, wompi
from app.text import money

logger = logging.getLogger(__name__)
pagos_bp = Blueprint("pagos", __name__)
_ESTADOS = {"APPROVED": "approved", "DECLINED": "declined", "VOIDED": "voided", "ERROR": "error", "PENDING": "pending"}


def link_para_pedido(pedido_id: str | None, total: int, cliente: str = "", nit: str | None = None) -> str | None:
    """URL de pago del pedido, o None si no corresponde o no se pudo crear."""
    if not WOMPI_ENABLED or not pedido_id or int(total or 0) <= 0:
        return None
    solo_nit = "".join(ch for ch in str(nit or "").split("-")[0] if ch.isdigit())
    if WOMPI_ONLY_NITS and solo_nit not in WOMPI_ONLY_NITS:  # modo prueba
        return None
    try:
        numero = (db.get_pedido(pedido_id) or {}).get("pedido_number") or "pedido"
        link = wompi.crear_link(f"A3 Laboratorio · {numero}",
                                f"Análisis de laboratorio {numero} {cliente}".strip(), int(total) * 100)
        pagos_db.crear(pedido_id, link["id"], int(total) * 100, link["url"])
        return link["url"]
    except Exception as exc:  # noqa: BLE001 — el pedido se cierra igual
        logger.error("pagos: no se pudo crear el link del pedido %s: %s", pedido_id, exc)
        notify_error("link de pago Wompi", exc, f"pedido {pedido_id}")
        return None


def _avisar(pedido: dict, texto: str, nota: str) -> None:
    chat_id = str(pedido.get("external_chat_id") or "")
    if not chat_id or chat_id.startswith("portal:"):
        return
    try:
        if (pedido.get("entry_channel") or "telegram") == "telegram":
            telegram.send_message(chat_id, texto)
        else:
            chatwoot.send_message(chat_id, texto)
            chatwoot.send_private_note(chat_id, nota)  # la ve Contabilidad en la conversación
        db.save_message(chat_id, texto, "bot")
    except Exception as exc:  # noqa: BLE001 — el pago ya quedó registrado
        logger.error("pagos: no se pudo avisar el pago del pedido %s: %s", pedido.get("id"), exc)


def procesar_evento(evento: dict) -> str:
    """Aplica un evento de Wompi. Devuelve qué hizo (para el log y los tests)."""
    if evento.get("event") != "transaction.updated":
        return "ignorado"
    if not wompi.firma_valida(evento):
        return "firma_invalida"
    tx = (evento.get("data") or {}).get("transaction") or {}
    pago = pagos_db.por_link(tx.get("payment_link_id"))
    if not pago:
        return "desconocido"
    if pago.get("status") == "approved":
        return "repetido"  # Wompi reintenta: un pago aprobado no se vuelve a avisar ni cambia
    estado = _ESTADOS.get(str(tx.get("status") or "").upper())
    if not estado or estado == pago.get("status"):
        return "sin_cambio"
    monto = int(tx.get("amount_in_cents") or 0)
    if estado == "approved" and monto != int(pago["amount_in_cents"]):
        pagos_db.actualizar(pago["id"], "mismatch", tx.get("id"), tx)
        notify_error("pago Wompi con monto distinto",
                     ValueError(f"esperado {pago['amount_in_cents']}, llegó {monto}"), f"pedido {pago['pedido_id']}")
        return "monto_distinto"
    pagos_db.actualizar(pago["id"], estado, tx.get("id"), tx)
    pedido = db.get_pedido(pago["pedido_id"]) or {}
    numero, valor = pedido.get("pedido_number") or "", money(int(pago["amount_in_cents"]) // 100)
    if estado == "approved":
        _avisar(pedido, f"Recibimos tu pago del pedido {numero} por {valor}. ¡Muchas gracias! 🙂",
                f"Pago APROBADO en Wompi · pedido {numero} · {valor} · transacción {tx.get('id')}")
    elif estado in ("declined", "error"):
        _avisar(pedido, f"El pago del pedido {numero} no fue aprobado. Puedes intentarlo de nuevo "
                        f"con el mismo enlace:\n{pago['url']}",
                f"Pago NO aprobado en Wompi ({estado}) · pedido {numero} · {valor}")
    return estado


@pagos_bp.post("/webhooks/wompi")
def wompi_webhook():
    evento = request.get_json(force=True, silent=True)
    if not isinstance(evento, dict):
        return jsonify({"ok": False}), 400
    try:
        resultado = procesar_evento(evento)
    except Exception as exc:  # noqa: BLE001 — con 500 Wompi reintenta (30 min, 3 h, 24 h)
        notify_error("webhook de Wompi", exc)
        return jsonify({"ok": False}), 500
    logger.info("wompi: evento %s", resultado)
    if resultado == "firma_invalida":
        return jsonify({"ok": False}), 401
    return jsonify({"ok": True, "resultado": resultado})
