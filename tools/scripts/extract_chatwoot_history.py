"""
Extrae las conversaciones REALES de Chatwoot a un JSON local (SOLO LECTURA).

Sirve para alimentar el replay de QA (`replay_chatwoot_qa.py`): en vez de inventar
guiones, se reproducen los turnos que escribieron de verdad el equipo de A3 y el
equipo del cliente. Un corpus real detecta lo que ningún guion escrito por nosotros
detecta, porque nosotros escribimos como esperamos que responda el bot.

Uso:  python tools/scripts/extract_chatwoot_history.py
      python tools/scripts/extract_chatwoot_history.py --out ruta/archivo.json

No escribe nada en Chatwoot: solo hace GET de conversaciones y mensajes.
"""
import argparse
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.config import (  # noqa: E402
    CHATWOOT_URL, CHATWOOT_ACCOUNT_ID, CHATWOOT_API_TOKEN,
)

_BASE = f"{CHATWOOT_URL}/api/v1/accounts/{CHATWOOT_ACCOUNT_ID}"
_HEADERS = {"api_access_token": CHATWOOT_API_TOKEN}
DEFAULT_OUT = Path(__file__).resolve().parents[2] / "tasks" / "analisis-chatwoot" / "conversaciones-reales.json"


def _get(path: str) -> dict:
    req = urllib.request.Request(f"{_BASE}{path}", headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def list_conversations() -> list[dict]:
    """Todas las conversaciones del inbox, paginando hasta que se agoten."""
    out, page = [], 1
    while True:
        data = _get(f"/conversations?status=all&page={page}")
        payload = data.get("data", data)
        rows = payload.get("payload", []) if isinstance(payload, dict) else []
        if not rows:
            break
        out.extend(rows)
        page += 1
        if page > 50:  # cortafuegos: nunca debería haber tantas
            break
    return out


def fetch_messages(conversation_id: int) -> list[dict]:
    """Todos los mensajes, paginando hacia atrás con `before`.

    Chatwoot devuelve 20 por página y NO avisa que truncó: una conversación de 40
    mensajes se ve idéntica a una de 20. Es la lección L56 aplicada a otra API —
    si no se pagina, se pierde justo el arranque de la conversación, que es donde
    está la identificación del cliente.
    """
    seen: dict[int, dict] = {}
    before = None
    while True:
        path = f"/conversations/{conversation_id}/messages"
        if before is not None:
            path += f"?before={before}"
        data = _get(path)
        payload = data.get("payload", data)
        rows = payload if isinstance(payload, list) else payload.get("payload", [])
        fresh = [r for r in rows if r.get("id") not in seen]
        if not fresh:
            break
        for r in fresh:
            seen[r["id"]] = r
        before = min(r["id"] for r in rows if r.get("id") is not None)
        if len(seen) > 2000:  # cortafuegos
            break
    return sorted(seen.values(), key=lambda r: r.get("id") or 0)


def _clean(msg: dict) -> dict | None:
    """Un mensaje reducido a lo que importa para el replay.

    message_type: 0=incoming (cliente), 1=outgoing (bot/agente), 2=activity (sistema).
    Las 'activity' son ruido de Chatwoot (asignaciones, cambios de estado), se descartan.
    """
    mtype = msg.get("message_type")
    if mtype not in (0, 1):
        return None
    content = (msg.get("content") or "").strip()
    if not content:
        return None
    sender = msg.get("sender") or {}
    return {
        "role": "cliente" if mtype == 0 else "bot",
        "content": content,
        "created_at": msg.get("created_at"),
        "private": bool(msg.get("private")),
        "sender": sender.get("name") or sender.get("available_name") or "",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    args = ap.parse_args()

    if not (CHATWOOT_URL and CHATWOOT_API_TOKEN):
        print("faltan CHATWOOT_URL / CHATWOOT_API_TOKEN en el entorno")
        return 1

    convs = list_conversations()
    print(f"conversaciones encontradas: {len(convs)}")

    result = []
    for c in convs:
        cid = c.get("id")
        try:
            raw = fetch_messages(cid)
        except Exception as exc:  # noqa: BLE001
            print(f"  conv {cid}: ERROR al bajar mensajes ({type(exc).__name__})")
            continue
        turns = [m for m in (_clean(m) for m in raw) if m]
        meta = c.get("meta") or {}
        contact = (meta.get("sender") or {}).get("name") or ""
        result.append({
            "conversation_id": cid,
            "status": c.get("status"),
            "contact": contact,
            "turns": turns,
            "client_turns": sum(1 for t in turns if t["role"] == "cliente"),
        })
        print(f"  conv {cid:>4} | {contact[:28]:<28} | {len(turns):>3} turnos "
              f"({sum(1 for t in turns if t['role'] == 'cliente')} del cliente)")

    result.sort(key=lambda r: r["client_turns"], reverse=True)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    total_client = sum(r["client_turns"] for r in result)
    print(f"\nguardado en {out}")
    print(f"total de turnos del cliente disponibles para replay: {total_client}")
    print("SOLO LECTURA: no se escribió nada en Chatwoot.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
