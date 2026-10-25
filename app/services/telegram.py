import urllib.request
import json
from app.config import TELEGRAM_BOT_TOKEN
from app.services.multipart import encode as _encode_multipart
from app.text import partir_mensaje

_BASE = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
# Sin timeout, un Telegram colgado dejaba el hilo del turno esperando para siempre.
_TIMEOUT = 20


def send_message(chat_id: str, text: str) -> None:
    # Telegram rechaza más de 4096 caracteres (HTTP 400): se manda en partes.
    for parte in partir_mensaje(text):
        payload = json.dumps({"chat_id": chat_id, "text": parte}, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            f"{_BASE}/sendMessage",
            data=payload,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
            r.read()


def send_document(chat_id: str, filename: str, content: bytes, caption: str | None = None) -> None:
    """Envía un archivo al chat. Se usa para entregar el PDF de un resultado."""
    content_type, body = _encode_multipart(
        {"chat_id": str(chat_id), "caption": caption},
        [("document", filename, content, "application/pdf")],
    )
    req = urllib.request.Request(
        f"{_BASE}/sendDocument",
        data=body,
        headers={"Content-Type": content_type},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
        r.read()


def send_typing(chat_id: str) -> None:
    payload = json.dumps({"chat_id": chat_id, "action": "typing"}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{_BASE}/sendChatAction",
        data=payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
        r.read()


def set_webhook(url: str, secret: str) -> dict:
    payload = json.dumps({"url": url, "secret_token": secret, "allowed_updates": ["message"]}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{_BASE}/setWebhook",
        data=payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
        return json.loads(r.read())
