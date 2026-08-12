"""
QA SEMÁNTICO del cierre de pedido: ¿entiende la INTENCIÓN, o solo cuatro palabras?

El cliente nunca dice la palabra que uno programó. Para terminar escribe "listo", "ya está",
"terminala", "con eso estamos"; para pagar, "les pagamos cuando pasen" o "en efectivo al
mensajero". Este QA mide las dos caras del problema:

  COBERTURA — frases que SÍ significan "terminé": el pedido tiene que cerrarse.
  PRECISIÓN — frases que NO lo significan: el pedido NO se puede cerrar.

La precisión importa tanto como la cobertura: cerrar un pedido porque el cliente escribió
"listo" cuando quería decir "listo, ahora cargá el otro paciente" le factura de menos y le
deja un paciente sin orden.

Corre contra el MODELO REAL con lecturas reales de Supabase; solo se mockean las escrituras.
NO escribe nada: ni órdenes, ni pedidos, ni facturas.

Uso:
  python tools/scripts/qa_cierre_semantico.py
  python tools/scripts/qa_cierre_semantico.py --solo cierre
"""
import sys
from pathlib import Path
from unittest.mock import patch

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tools" / "scripts"))

from replay_chatwoot_qa import _WRITE_PATCHES, _state, _reset  # noqa: E402

# Cliente real de la base, con una orden ya registrada y el pedido abierto.
CLIENTE = {"id": "qa-cli", "clinic_name": "Animal Pets", "tax_id": "53115419-1"}

CAMPOS_BASE = {
    "_client_found": True, "clinic_name": "Animal Pets", "tax_id": "53115419-1",
    "pickup_address": "DG 51A SUR 61B-03", "requesting_doctor": "Dra. Laura Méndez",
    "patient_name": "Firulais", "species": "Canino", "breed": "Labrador", "sex": "Macho",
    "patient_age": "3 años", "owner_name": "Pedro Gómez", "observations": "sin observaciones",
    "exam_type": "1101 Cuadro Hemático Completo", "selected_tests": ["1101"],
    "_order_registered": True, "_pedido_id": "qa-ped-1",
}

# ── COBERTURA: significan "terminé", el pedido DEBE cerrarse ────────────────────
CIERRA = [
    "listo, nada más por hoy",
    "ya está, cerrame eso",
    "eso sería todo",
    "con eso estamos",
    "no, nada más",
    "terminala ahí",
    "hasta ahí llegamos",
    "no necesito nada más",
    "dale, cerralo",
    "listo",
]

# ── PRECISIÓN: NO significan "terminé", el pedido NO puede cerrarse ─────────────
NO_CIERRA = [
    ("listo, ahora cargame el otro paciente", "pide otra orden"),
    ("ya está ese, va otro más", "pide otra orden"),
    ("esperá que busco el dato", "pide tiempo"),
    ("¿cuánto sale todo?", "pregunta precio"),
    ("no, esa dirección está mal", "corrige un dato"),
    ("listo el hemograma, ahora uno para Michi", "pide otra orden"),
    ("¿a qué hora pasan?", "pregunta logística"),
    ("no entendí", "no entendió"),
]

# ── PAGO: sinónimos que el sistema debe reconocer como forma de pago ────────────
PAGO = [
    ("les pagamos cuando pasen a recoger", "contraentrega"),
    ("en efectivo al mensajero", "contraentrega"),
    ("contra entrega", "contraentrega"),
    ("pagamos al recibir", "contraentrega"),
    ("por transferencia", "pago_linea"),
    ("con tarjeta", "pago_linea"),
    ("mandanos el link de pago", "pago_linea"),
]


def _preparar(chat_id: str) -> None:
    _reset(chat_id)
    _state["session"].update(
        client_id=CLIENTE["id"], phase_current="fase_6_cierre",
        intent_current="route_scheduling", captured_fields=dict(CAMPOS_BASE),
    )
    _state["history"] = [
        {"role": "user", "content": "sí, confirmo"},
        {"role": "bot", "content": "Quedó registrado. Número de orden: A3-2026-901.\n\n"
                                   "¿Necesitas cargar otra orden para otro paciente? Escríbeme: "
                                   "otra orden. Si eso es todo, seguimos con la forma de pago y "
                                   "cerramos el pedido."},
    ]
    _state["pedidos"] = {"qa-ped-1": {"id": "qa-ped-1", "pedido_number": "P-2026-001",
                                      "status": "abierto", "external_chat_id": chat_id}}
    _state["pedido_requests"] = {"qa-ped-1": [
        {"order_number": "A3-2026-901", "patient_name": "Firulais",
         "exam_type": "1101 Cuadro Hemático Completo"}]}


def _turno(frase: str, i: int) -> tuple[str, str]:
    """Devuelve (resultado, reply). resultado ∈ {cerro, pide_pago, sigue, error}."""
    from app.agent import process_turn

    chat_id = f"qa-sem-{i}"
    _preparar(chat_id)
    try:
        reply = process_turn(chat_id, frase) or ""
    except Exception as exc:  # noqa: BLE001
        return "error", f"{type(exc).__name__}: {exc}"
    campos = _state["session"].get("captured_fields") or {}
    if campos.get("_pedido_cerrado"):
        return "cerro", reply
    if campos.get("_pedido_awaiting_payment"):
        return "pide_pago", reply
    return "sigue", reply


def _bloque_cierre() -> tuple[int, int]:
    print("=" * 78)
    print("COBERTURA — frases que significan 'terminé' (debe pedir el pago o cerrar)")
    print("=" * 78)
    ok = 0
    for i, frase in enumerate(CIERRA):
        resultado, reply = _turno(frase, i)
        bien = resultado in ("pide_pago", "cerro")
        ok += bien
        print(f"  [{'OK' if bien else 'XX'}] {frase!r:<42} -> {resultado}")
        if not bien:
            print(f"         bot: {reply[:90]}")
    print(f"\n  cobertura: {ok}/{len(CIERRA)}\n")
    return ok, len(CIERRA)


def _bloque_no_cierre() -> tuple[int, int]:
    print("=" * 78)
    print("PRECISIÓN — frases que NO significan 'terminé' (NO debe cerrar ni pedir pago)")
    print("=" * 78)
    ok = 0
    for i, (frase, motivo) in enumerate(NO_CIERRA, start=100):
        resultado, reply = _turno(frase, i)
        bien = resultado == "sigue"
        ok += bien
        print(f"  [{'OK' if bien else 'XX'}] {frase!r:<42} ({motivo}) -> {resultado}")
        if not bien:
            print(f"         bot: {reply[:90]}")
    print(f"\n  precisión: {ok}/{len(NO_CIERRA)}\n")
    return ok, len(NO_CIERRA)


def _bloque_pago() -> tuple[int, int]:
    print("=" * 78)
    print("PAGO — sinónimos de forma de pago (debe cerrar el pedido con el método correcto)")
    print("=" * 78)
    ok = 0
    for i, (frase, esperado) in enumerate(PAGO, start=200):
        resultado, reply = _turno(frase, i)
        metodo = (_state["pedidos"].get("qa-ped-1") or {}).get("payment_method")
        bien = resultado == "cerro" and metodo == esperado
        ok += bien
        print(f"  [{'OK' if bien else 'XX'}] {frase!r:<42} -> {resultado}, método={metodo!r}"
              f" (esperado {esperado!r})")
    print(f"\n  pago: {ok}/{len(PAGO)}\n")
    return ok, len(PAGO)


def main() -> int:
    solo = None
    if "--solo" in sys.argv:
        solo = sys.argv[sys.argv.index("--solo") + 1]

    patchers = [patch(f"app.services.db.{n}", **kw) for n, kw in _WRITE_PATCHES.items()]
    for p in patchers:
        p.start()
    try:
        resultados = []
        if solo in (None, "cierre"):
            resultados.append(("cobertura", *_bloque_cierre()))
        if solo in (None, "precision"):
            resultados.append(("precisión", *_bloque_no_cierre()))
        if solo in (None, "pago"):
            resultados.append(("pago", *_bloque_pago()))
    finally:
        for p in patchers:
            p.stop()

    print("=" * 78)
    total_ok = sum(r[1] for r in resultados)
    total = sum(r[2] for r in resultados)
    for nombre, ok, n in resultados:
        print(f"  {nombre:<12} {ok}/{n}")
    print(f"  {'TOTAL':<12} {total_ok}/{total}")
    return 0 if total_ok == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
