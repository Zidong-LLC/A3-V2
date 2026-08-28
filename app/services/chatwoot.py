import json
import logging
import urllib.request
from app.config import (
    CHATWOOT_URL, CHATWOOT_ACCOUNT_ID, CHATWOOT_API_TOKEN,
    CHATWOOT_TEAM_CONTABILIDAD, CHATWOOT_TEAM_OPERACIONES,
)
from app.services.multipart import encode as _encode_multipart

logger = logging.getLogger(__name__)

_BASE = f"{CHATWOOT_URL}/api/v1/accounts/{CHATWOOT_ACCOUNT_ID}"
_HEADERS = {
    "Content-Type": "application/json",
    "api_access_token": CHATWOOT_API_TOKEN,
}

_TEAM_MAP = {
    "contabilidad": CHATWOOT_TEAM_CONTABILIDAD,
    "operaciones": CHATWOOT_TEAM_OPERACIONES,
    # `tecnico` es un handoff_area válido del schema pero A3 no tiene equipo propio para él:
    # por decisión del triage (ítem 2) se redirige a operaciones. Antes no estaba mapeado y
    # el escalado técnico se descartaba en silencio.
    "tecnico": CHATWOOT_TEAM_OPERACIONES,
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


def send_document(conversation_id: str, filename: str, content: bytes, caption: str | None = None) -> None:
    """Adjunta un archivo a la conversación. Chatwoot solo acepta adjuntos por
    multipart, así que no puede pasar por `_post`, que manda JSON."""
    content_type, body = _encode_multipart(
        {"content": caption or "", "message_type": "outgoing", "private": "false"},
        [("attachments[]", filename, content, "application/pdf")],
    )
    headers = {"Content-Type": content_type, "api_access_token": CHATWOOT_API_TOKEN}
    req = urllib.request.Request(
        f"{_BASE}/conversations/{conversation_id}/messages",
        data=body,
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(req) as r:
        r.read()


def send_typing(conversation_id: str) -> None:
    _post(f"/conversations/{conversation_id}/toggle_typing_status", {
        "typing_status": "on",
    })


def assign_team(conversation_id: str, handoff_area: str) -> None:
    """Asigna la conversación al equipo del área. Si no hay equipo configurado NO se asigna,
    pero queda registrado: antes retornaba mudo y la conversación se quedaba sin dueño sin
    que nadie se enterara (regla de app/services/CLAUDE.md — nunca fallar en silencio)."""
    team_id = _TEAM_MAP.get(handoff_area)
    if not team_id:
        logger.warning(
            "Chatwoot: escalado sin asignar — conversación %s, área %r (%s). "
            "La conversación queda sin equipo.",
            conversation_id, handoff_area,
            "área desconocida" if handoff_area not in _TEAM_MAP else "equipo sin configurar en el .env",
        )
        return
    _post(f"/conversations/{conversation_id}/assignments", {
        "team_id": int(team_id),
    })
