import urllib.request
import json
from app.config import TELEGRAM_BOT_TOKEN

_BASE = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"


def send_message(chat_id: str, text: str) -> None:
    payload = json.dumps({"chat_id": chat_id, "text": text}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{_BASE}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(req) as r:
        r.read()


def send_typing(chat_id: str) -> None:
    payload = json.dumps({"chat_id": chat_id, "action": "typing"}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{_BASE}/sendChatAction",
        data=payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(req) as r:
        r.read()


def set_webhook(url: str, secret: str) -> dict:
    payload = json.dumps({"url": url, "secret_token": secret, "allowed_updates": ["message"]}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{_BASE}/setWebhook",
        data=payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())
