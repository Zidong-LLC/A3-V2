"""Restaura el webhook de Telegram para que apunte a Chatwoot (no a Flask).

Ejecutar cuando set_webhook.py fue llamado por error y Chatwoot dejó de recibir mensajes.
"""
import json
import os
import urllib.parse
import urllib.request

from dotenv import load_dotenv

load_dotenv()

CHATWOOT_URL = os.environ["CHATWOOT_URL"].rstrip("/")
CHATWOOT_ACCOUNT_ID = os.environ["CHATWOOT_ACCOUNT_ID"]
CHATWOOT_API_TOKEN = os.environ["CHATWOOT_API_TOKEN"]
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHATWOOT_INBOX_ID = os.environ.get("CHATWOOT_INBOX_ID", "1")

body = json.dumps({"channel": {"bot_token": TELEGRAM_BOT_TOKEN}}).encode()
req = urllib.request.Request(
    f"{CHATWOOT_URL}/api/v1/accounts/{CHATWOOT_ACCOUNT_ID}/inboxes/{CHATWOOT_INBOX_ID}",
    data=body,
    headers={"api_access_token": CHATWOOT_API_TOKEN, "Content-Type": "application/json"},
    method="PATCH",
)
urllib.request.urlopen(req).read()

req2 = urllib.request.urlopen(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getWebhookInfo")
info = json.loads(req2.read())["result"]
url = info.get("url", "")
parsed = urllib.parse.urlparse(url)
print(f"Webhook restaurado en host: {parsed.netloc or 'sin-url'}")
