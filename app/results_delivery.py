"""Entrega por el chat los PDFs que el turno dejó marcados (paso 3.4a).

Vive fuera del agente porque el envío depende del canal, y `process_turn` solo
devuelve texto. Lo llama `main.py` DESPUÉS de mandar la respuesta, para que el
cliente lea primero y reciba el archivo después."""
import logging

from app.enforcers.resultados import DELIVER_KEY
from app.results_lookup import pdf_filename
from app.services import chatwoot, db, portal_db, storage, telegram

logger = logging.getLogger(__name__)


def _send(channel: str, chat_id: str, filename: str, content: bytes, caption: str) -> None:
    if channel == "chatwoot":
        chatwoot.send_document(chat_id, filename, content, caption)
    else:
        telegram.send_document(chat_id, filename, content, caption)


def deliver_pending(chat_id: str, channel: str = "telegram") -> int:
    """Manda los resultados marcados en la sesión y devuelve cuántos salieron.

    La marca se limpia SIEMPRE, antes de intentar el envío: si algo falla, el
    cliente no queda recibiendo el mismo PDF en cada turno siguiente."""
    session = db.get_or_create_session(chat_id, channel=channel)
    fields = session.get("captured_fields") or {}
    result_ids = fields.get(DELIVER_KEY) or []
    if not result_ids:
        return 0

    db.clear_pending_result_delivery(chat_id)
    client_id = session.get("client_id")
    sent = 0
    for result_id in result_ids:
        try:
            result = portal_db.get_lab_result(result_id)
            # Segundo candado, además del de la búsqueda: el archivo tiene que ser
            # del cliente de ESTA sesión y estar publicado.
            if not result or not result.get("published") or result.get("client_id") != client_id:
                logger.warning("Resultado %s no entregable a %s", result_id, chat_id)
                continue
            content = storage.download_result_pdf(result["pdf_path"])
            _send(channel, chat_id, pdf_filename(result), content, "")
            sent += 1
        except Exception:
            logger.exception("No se pudo entregar el resultado %s por %s", result_id, channel)
    return sent
