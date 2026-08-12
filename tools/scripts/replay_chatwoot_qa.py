"""
QA por REPLAY de conversaciones REALES de Chatwoot contra el agente + modelo reales.

Diferencia con validate_flows.py: allí los guiones los escribimos nosotros, y uno
escribe los guiones como espera que el bot responda. Acá los turnos los escribieron
de verdad el equipo de A3 y el equipo del cliente, con sus typos, sus respuestas a
medias y su impaciencia. Es el corpus que encuentra lo que no se nos ocurre probar.

Fidelidad: se mockean SOLO las escrituras y la sesión (para no tocar la base). Las
LECTURAS van contra Supabase real — clientes, catálogo y razas — así la identificación
se prueba contra los 992 clientes reales, no contra un cliente de juguete.

Entrada:  tasks/analisis-chatwoot/conversaciones-reales.json
          (generarlo antes con: python tools/scripts/extract_chatwoot_history.py)

Uso:  python tools/scripts/replay_chatwoot_qa.py                # top 12 segmentos sospechosos
      python tools/scripts/replay_chatwoot_qa.py --limit 5
      python tools/scripts/replay_chatwoot_qa.py --list         # solo listar, sin gastar tokens
      python tools/scripts/replay_chatwoot_qa.py --segment 4-3   # un segmento puntual
"""
import argparse
import json
import re
import sys
from pathlib import Path
from unittest.mock import patch

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

CORPUS = Path(__file__).resolve().parents[2] / "tasks" / "analisis-chatwoot" / "conversaciones-reales.json"
SESSION_GAP_SECONDS = 3600          # 1 h sin mensajes = sesión nueva
MIN_CLIENT_TURNS = 3

# Señales de que el cliente se está peleando con el bot. Sacadas del corpus real,
# no inventadas: "Ya te lo dije" aparece literal en la conv 4.
FRUSTRATION = (
    "ya te lo dije", "ya lo dije", "otra vez", "te repito", "no entiendes",
    "no entendiste", "eso no", "no es eso", "ya te dije", "que pasa",
    "sigues preguntando", "de nuevo", "no me estas", "no funciona",
)
ROBOTIC_MARKERS = ("dato que tengas a mano", "escribe 'hablar con alguien'")

# ── Estado en memoria: reemplaza SOLO sesión/historial/escrituras ────────────────
_state = {}


def _reset(chat_id):
    _state.clear()
    _state.update({
        "chat_id": chat_id,
        "session": {
            "external_chat_id": chat_id, "client_id": None,
            "phase_current": "fase_0_bienvenida", "intent_current": "unknown",
            "captured_fields": {},
        },
        "history": [], "requests": [], "pending_clients": [],
    })


def _create_request(chat_id, session, ai, pedido_id=None):
    _state["requests"].append(ai)
    n = len(_state["requests"])
    if pedido_id:
        _state.setdefault("pedido_requests", {}).setdefault(pedido_id, []).append(
            {"order_number": f"A3-2026-90{n}",
             "patient_name": (ai.get("captured_fields") or {}).get("patient_name"),
             "exam_type": (ai.get("captured_fields") or {}).get("exam_type")}
        )
    return {"request_id": f"replay-req-{n}", "order_number": f"A3-2026-90{n}"}


# Pedidos (decision 011): tambien son ESCRITURAS, asi que van mockeados. Sin esto la
# simulacion crearia pedidos de verdad en Supabase.
def _create_pedido(client_id, chat_id, entry_channel="telegram"):
    _state["pedidos"] = _state.get("pedidos", {})
    pid = f"replay-ped-{len(_state['pedidos']) + 1}"
    _state["pedidos"][pid] = {"id": pid, "pedido_number": f"P-2026-90{len(_state['pedidos']) + 1}",
                              "status": "abierto", "external_chat_id": chat_id}
    return {"id": pid, "pedido_number": _state["pedidos"][pid]["pedido_number"]}


def _get_open_pedido(chat_id):
    for ped in (_state.get("pedidos") or {}).values():
        if ped["external_chat_id"] == chat_id and ped["status"] == "abierto":
            return ped
    return None


def _close_pedido(pedido_id, payment_method=None):
    ped = (_state.get("pedidos") or {}).get(pedido_id)
    if ped:
        ped.update(status="cerrado", payment_method=payment_method)
    return ped


# Solo lo que ESCRIBE o lleva estado de sesión. Todo lo demás (find_client_matches,
# catálogo, razas, perfiles, courier) queda REAL contra Supabase.
_WRITE_PATCHES = {
    "get_or_create_session": dict(side_effect=lambda c, channel="telegram": _state["session"]),
    "get_recent_messages": dict(side_effect=lambda c, limit=8: _state["history"][-limit:]),
    "save_message": dict(side_effect=lambda c, t, r: _state["history"].append({"role": r, "content": t})),
    "update_session": dict(side_effect=lambda c, ai: _state["session"].update(
        phase_current=ai["phase"], intent_current=ai["intent"], captured_fields=ai["captured_fields"])),
    "link_client_to_session": dict(side_effect=lambda c, cid: _state["session"].update(client_id=cid)),
    "clear_client_from_session": dict(side_effect=lambda c: _state["session"].update(client_id=None)),
    "create_request": dict(side_effect=_create_request),
    "create_pedido": dict(side_effect=_create_pedido),
    "get_open_pedido": dict(side_effect=_get_open_pedido),
    "close_pedido": dict(side_effect=_close_pedido),
    "touch_pedido": dict(return_value=None),
    "mark_pedido_invoiced": dict(return_value=None),
    "list_pedido_requests": dict(
        side_effect=lambda pid: (_state.get("pedido_requests") or {}).get(pid, [])),
    "create_pending_client_review": dict(side_effect=lambda cl, rv: _state["pending_clients"].append((cl, rv))),
    "create_request_event": dict(return_value=None),
}


# ── Segmentación del corpus ─────────────────────────────────────────────────────
def segment(conv: dict) -> list[dict]:
    """Parte una conversación larga en sesiones por hueco temporal.

    Las conversaciones de Chatwoot son un hilo único por contacto que abarca meses;
    reproducirlo entero no tiene sentido (son decenas de órdenes distintas). El corte
    por hueco de 1 h recupera las sesiones que de verdad ocurrieron.
    """
    segs, cur, last_ts = [], [], None
    for t in conv["turns"]:
        ts = t.get("created_at") or 0
        if last_ts is not None and ts - last_ts > SESSION_GAP_SECONDS and cur:
            segs.append(cur)
            cur = []
        cur.append(t)
        last_ts = ts
    if cur:
        segs.append(cur)

    out = []
    for i, turns in enumerate(segs, 1):
        client_turns = [t["content"] for t in turns if t["role"] == "cliente"]
        if len(client_turns) < MIN_CLIENT_TURNS:
            continue
        out.append({
            "id": f"{conv['conversation_id']}-{i}",
            "contact": conv["contact"],
            "turns": turns,
            "client_turns": client_turns,
            "started_at": turns[0].get("created_at"),
            "suspicion": _suspicion(turns),
            "starts_fresh": _starts_fresh(client_turns[0]),
        })
    return out


_GREETING = re.compile(
    r"^\s*(hola|holis|buen[oa]s?\s*(d[ií]as?|tardes?|noches?)|buen\s*d[ií]a|qu[eé]\s*tal|"
    r"buenas|hey|saludos)\b", re.IGNORECASE)


def _starts_fresh(first_client_turn: str) -> bool:
    """¿El segmento arranca una conversación, o cae a mitad de una en curso?

    Sin este filtro el replay es basura: si el primer turno es 'Greta' (respuesta a
    '¿nombre del paciente?'), el agente arranca en fase_0 y lo lee como identificador
    de cliente. El descarrilamiento lo causa el harness, no el agente, y ensucia el QA.
    """
    return bool(_GREETING.match(first_client_turn or ""))


def _suspicion(turns: list[dict]) -> int:
    """Cuánto huele a fallo este segmento (para priorizar qué reproducir)."""
    score = 0
    bot = [t["content"] for t in turns if t["role"] == "bot"]
    for prev, cur in zip(bot, bot[1:]):
        if prev.strip() == cur.strip():
            score += 3                      # el bot se repitió literal: bucle
    for t in turns:
        if t["role"] != "cliente":
            continue
        low = t["content"].lower()
        for f in FRUSTRATION:
            if f in low:
                score += 2
                break
    if not any("quedó registrad" in b.lower() or "a3-2026" in b.lower() for b in bot):
        score += 1                          # sesión que nunca cerró una orden
    return score


def load_segments() -> list[dict]:
    if not CORPUS.exists():
        print(f"falta el corpus: {CORPUS}\ncorrelo primero: python tools/scripts/extract_chatwoot_history.py")
        raise SystemExit(1)
    convs = json.load(open(CORPUS, encoding="utf-8"))
    segs = []
    for c in convs:
        segs.extend(segment(c))
    segs = [s for s in segs if s["starts_fresh"]]
    segs.sort(key=lambda s: (-s["suspicion"], -(s["started_at"] or 0)))
    return segs


# ── Replay ──────────────────────────────────────────────────────────────────────
_MONEY = re.compile(r"\$\s?([\d.,]+)")


def replay(seg: dict) -> dict:
    from app.agent import process_turn
    chat_id = f"replay-{seg['id']}"
    _reset(chat_id)
    print("=" * 78)
    print(f"SEGMENTO {seg['id']} | contacto: {seg['contact']} | sospecha: {seg['suspicion']}")
    print("=" * 78)

    replies, issues = [], []
    for msg in seg["client_turns"]:
        try:
            reply = process_turn(chat_id, msg)
        except Exception as exc:  # noqa: BLE001
            issues.append(f"EXCEPCIÓN en '{msg[:45]}': {type(exc).__name__}: {exc}")
            break
        print(f"  USR: {msg[:110]}")
        print(f"  BOT: {(reply or '(sin respuesta)')[:300]}")
        print("  -")
        replies.append(reply)

    bot = [r for r in replies if r]
    for prev, cur in zip(bot, bot[1:]):
        if prev.strip() == cur.strip():
            issues.append(f"BUCLE: respuesta idéntica consecutiva: '{cur[:70]}'")
    for r in bot:
        for m in ROBOTIC_MARKERS:
            if m in r:
                issues.append(f"ROBÓTICO: '{m}'")

    # Silencio sostenido: el bot se bloqueó y el cliente siguió escribiendo al vacío.
    # `_blocked` es intencional para un particular, pero también lo activa
    # `_escalate_unfound_client`: un cliente legítimo mal identificado queda mudo.
    silence = 0
    for r in replies:
        silence = silence + 1 if r is None else 0
        if silence >= 4:
            issues.append(f"SILENCIO: el bot dejó de responder y el cliente siguió "
                          f"escribiendo {silence}+ turnos al vacío")
            break

    # Cerró el resumen pero nunca creó la orden (patrón ERR-080).
    closed = any("quedó registrad" in r.lower() or "a3-2026" in r.lower() for r in bot)
    summarized = any("te resumo la orden" in r.lower() or "confirmas estos datos" in r.lower() for r in bot)
    if summarized and not closed and not _state["requests"]:
        issues.append("RESUMIÓ LA ORDEN PERO NUNCA LA REGISTRÓ (patrón ERR-080)")
    if closed and not _state["requests"]:
        issues.append("ANUNCIÓ CIERRE SIN FILA DE ORDEN (request_id=None)")

    status = "OK" if not issues else "PROBLEMAS"
    print(f"  >>> {status}   (órdenes creadas: {len(_state['requests'])})")
    for i in issues:
        print(f"      ! {i}")
    return {"id": seg["id"], "contact": seg["contact"], "status": status,
            "issues": issues, "orders": len(_state["requests"]), "replies": replies}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=12)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--segment", default=None)
    args = ap.parse_args()

    segs = load_segments()
    print(f"segmentos con >= {MIN_CLIENT_TURNS} turnos del cliente: {len(segs)}\n")

    if args.list:
        for s in segs[:60]:
            print(f"  {s['id']:>8} | sosp {s['suspicion']:>3} | {len(s['client_turns']):>3} turnos "
                  f"| {s['contact'][:26]:<26} | {s['client_turns'][0][:52]}")
        return 0

    if args.segment:
        segs = [s for s in segs if s["id"] == args.segment]
        if not segs:
            print(f"no existe el segmento {args.segment}")
            return 1
    else:
        segs = segs[:args.limit]

    patchers = [patch(f"app.services.db.{n}", **kw) for n, kw in _WRITE_PATCHES.items()]
    for p in patchers:
        p.start()
    results = []
    try:
        for s in segs:
            results.append(replay(s))
    finally:
        for p in patchers:
            p.stop()

    print("\n" + "=" * 78)
    print("RESUMEN DEL REPLAY")
    print("=" * 78)
    ok = sum(1 for r in results if r["status"] == "OK")
    for r in results:
        print(f"  [{r['status']:<9}] {r['id']:>8} | {r['contact'][:24]:<24} | órdenes: {r['orders']}")
        for i in r["issues"]:
            print(f"              ! {i}")
    print(f"\n{ok}/{len(results)} segmentos OK")
    print("No se escribió nada en Supabase ni en Chatwoot.")
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
