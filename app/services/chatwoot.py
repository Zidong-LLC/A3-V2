import json
import urllib.request
from app.config import (
    CHATWOOT_URL, CHATWOOT_ACCOUNT_ID, CHATWOOT_API_TOKEN,
    CHATWOOT_TEAM_CONTABILIDAD, CHATWOOT_TEAM_OPERACIONES,
)

_BASE = f"{CHATWOOT_URL}/api/v1/accounts/{CHATWOOT_ACCOUNT_ID}"
_HEADERS = {
    "Content-Type": "application/json",
    "api_access_token": CHATWOOT_API_TOKEN,
}

_TEAM_MAP = {
    "contabilidad": CHATWOOT_TEAM_CONTABILIDAD,
    "operaciones": CHATWOOT_TEAM_OPERACIONES,
}


def _post(path: str, body: dict) -> None:
    payload = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{_BASE}{path}",
        data=payload,
        headers=_HEADERS,
        method="POST",
    )
    with urllib.request.urlopen(req) as r:
        r.read()


def send_message(conversation_id: str, text: str) -> None:
    _post(f"/conversations/{conversation_id}/messages", {
        "content": text,
        "message_type": "outgoing",
        "private": False,
    })


def send_typing(conversation_id: str) -> None:
    _post(f"/conversations/{conversation_id}/toggle_typing_status", {
        "typing_status": "on",
    })


def assign_team(conversation_id: str, handoff_area: str) -> None:
    team_id = _TEAM_MAP.get(handoff_area)
    if not team_id:
        return
    _post(f"/conversations/{conversation_id}/assignments", {
        "team_id": int(team_id),
    })
