"""
Diagnóstico de IDENTIFICACIÓN de cliente contra la BD REAL + modelo REAL.
Mockea SOLO sesión/escritura (en memoria); las lecturas de clientes
(find_client_matches, find_clients_by_tax_id, get_client_by_id) usan Supabase real.
NO escribe en la base. Uso:  python tools/scripts/diag_identificacion.py "Animal Planet"
"""
import sys
from pathlib import Path
from unittest.mock import patch

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

_state = {}


def _reset(chat_id):
    _state.clear()
    _state.update({
        "session": {
            "external_chat_id": chat_id, "client_id": None,
            "phase_current": "fase_0_bienvenida", "intent_current": "unknown",
            "captured_fields": {},
        },
        "history": [], "requests": [],
    })


# Solo sesión/escritura en memoria; el resto (clientes) va a Supabase real.
_MEM_PATCHES = {
    "get_or_create_session": lambda c, channel="telegram": _state["session"],
    "get_recent_messages": lambda c, limit=8: _state["history"][-limit:],
    "save_message": lambda c, t, r: _state["history"].append({"role": r, "content": t}),
    "update_session": lambda c, ai: _state["session"].update(
        phase_current=ai["phase"], intent_current=ai["intent"], captured_fields=ai["captured_fields"]),
    "link_client_to_session": lambda c, cid: _state["session"].update(client_id=cid),
    "clear_client_from_session": lambda c: _state["session"].update(client_id=None),
    "create_request": lambda c, s, ai: (_state["requests"].append(ai), {"request_id": "r1", "order_number": "A3-2026-001"})[1],
    "create_pending_client_review": lambda cl, rv: None,
    "get_last_order_for_client": lambda cid: None,
}


def _state_line():
    f = _state["session"]["captured_fields"]
    opts = f.get("_client_match_options")
    return (
        f"      [estado] clinic_name={f.get('clinic_name')!r} tax_id={f.get('tax_id')!r} "
        f"client_id={_state['session'].get('client_id')!r} "
        f"opciones={len(opts) if opts else 0} "
        f"found={f.get('_client_found')} not_found={f.get('_client_not_found')}"
    )


def run(turns):
    patchers = [patch(f"app.services.db.{n}", side_effect=fn) for n, fn in _MEM_PATCHES.items()]
    for p in patchers:
        p.start()
    try:
        from app.agent import process_turn
        _reset("diag-ident")
        for msg in turns:
            reply = process_turn("diag-ident", msg)
            print(f"  USR: {msg}")
            print(f"  BOT: {reply}")
            print(_state_line())
            print("  -")
    finally:
        for p in patchers:
            p.stop()


def _diag(turns):
    """Corre la conversación y devuelve el estado final + último reply."""
    patchers = [patch(f"app.services.db.{n}", side_effect=fn) for n, fn in _MEM_PATCHES.items()]
    for p in patchers:
        p.start()
    try:
        from app.agent import process_turn
        _reset("diag-ident")
        last = None
        for msg in turns:
            last = process_turn("diag-ident", msg)
        f = _state["session"]["captured_fields"]
        return {
            "reply": last,
            "client_id": _state["session"].get("client_id"),
            "options": len(f.get("_client_match_options") or []),
            "not_found": bool(f.get("_client_not_found")),
            "clinic_name": f.get("clinic_name"),
            "tax_id": f.get("tax_id"),
        }
    finally:
        for p in patchers:
            p.stop()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        print("=" * 64)
        print(f"IDENTIFICACIÓN: {sys.argv[1]!r}")
        run(["Hola", "1", sys.argv[1]])
        sys.exit(0)

    # Batería de fortificación: variantes reales de cómo un cliente da su identificador.
    CASOS = [
        ("Nombre parcial (2 matches)", "Animal Planet"),
        ("Nombre exacto", "Animal Planet HVP"),
        ("Nombre dentro de frase", "Somos la veterinaria Animal Planet"),
        ("Nombre con typo (doble t)", "Animal Planett"),
        ("Nombre con typo (Bioanimall)", "Bioanimall"),
        ("Nombre con typo (Anímal Planet)", "Anpetal Planet"),
        ("NIT exacto", "51731849-8"),
        ("NIT sin dígito verificación", "51731849"),
        ("Multi-sede mismo NIT", "23784139-2"),
        ("Nombre genérico (muchos)", "veterinaria animal"),
    ]
    print("=" * 64)
    print("BATERÍA DE FORTIFICACIÓN — identificación contra BD real")
    print("=" * 64)
    resultados = []
    for titulo, entrada in CASOS:
        r = _diag(["Hola", "1", entrada])
        if r["client_id"]:
            estado = "IDENTIFICADO directo"
        elif r["options"]:
            estado = f"OPCIONES ({r['options']})"
        elif r["not_found"]:
            estado = "NO ENCONTRADO"
        else:
            estado = "SIN BÚSQUEDA (no capturó identificador)"
        resultados.append((titulo, entrada, estado))
        print(f"\n[{titulo}]  entrada={entrada!r}")
        print(f"   captura: clinic_name={r['clinic_name']!r} tax_id={r['tax_id']!r}")
        print(f"   => {estado}")
        print(f"   BOT: {(r['reply'] or '')[:140]}")
    print("\n" + "=" * 64)
    print("RESUMEN")
    for titulo, entrada, estado in resultados:
        print(f"  [{estado:28}] {titulo}")
