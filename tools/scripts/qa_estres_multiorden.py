"""QA de ESTRÉS multi-orden: personas sucias contra el modelo y la base reales.

Pedido del usuario (2026-08-15): "tratá de romper al agente" — varios perfiles de cliente,
nunca respuestas perfectas, especialmente varios análisis y varias órdenes (1 a 10).

Disciplinas aplicadas:
- L60: el cliente lo simula una IA con typos/desorden, no un guion.
- L66: el veredicto sale del ESTADO (payloads de `create_request`, fichas del pedido y
  llamadas a factura), no del texto de las respuestas.
- Regla dura Alegra: `billing.invoice_order` va parcheado a un CONTADOR — el estrés cierra
  pedidos en masa y NO puede crear borradores reales. De paso se afirma 1 factura por pedido.

Uso:
  python tools/scripts/qa_estres_multiorden.py                 # todas las personas
  python tools/scripts/qa_estres_multiorden.py maraton_10      # solo esa
  python tools/scripts/qa_estres_multiorden.py --rojo          # L61: validar el QA con un bug conocido
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
from sim_cliente import _cliente_simulado  # noqa: E402

# CRÍTICO: arrancar los patches de ESCRITURA antes de cualquier turno. En la primera versión
# faltaba este bloque y la corrida escribió sesiones, órdenes y un pedido REALES en Supabase
# (hubo que limpiarlos a mano). Sin esto, el estrés no es un simulacro.
for _p in [patch(f"app.services.db.{k}", **v) for k, v in _WRITE_PATCHES.items()]:
    _p.start()

# Mock ENRIQUECIDO de create_request: igual que el del harness pero devolviendo el
# event_payload con el `profile` REAL (mismo armador que producción). Sin esto,
# `_finalize_request` no acumula `_pedido_profiles` y la factura del pedido sale vacía —
# el chequeo "1 factura por pedido" daba falso rojo por el harness, no por el agente.
from replay_chatwoot_qa import _create_request as _harness_create_request  # noqa: E402
from app.services import db as _dbmod  # noqa: E402


def _create_request_enriquecido(chat_id, session, ai, pedido_id=None):
    info = _harness_create_request(chat_id, session, ai, pedido_id=pedido_id)
    perfil = _dbmod._profile_event_payload(ai.get("captured_fields") or {})
    if info is not None:
        info["event_payload"] = {"profile": perfil} if perfil else {}
        ai["_event_payload"] = info["event_payload"]  # para el veredicto por estado
    return info


patch("app.services.db.create_request", side_effect=_create_request_enriquecido).start()

IDENT = ("Sos de 'Animal Pets' (registrada). Identificate con ese nombre cuando te lo "
         "pidan y confirmá la dirección que el bot te ofrezca. Médico: Dr. Ruiz. ")
CIERRE = ("REGLA DURA: tenés que cargar TODAS las órdenes del plan, EN ORDEN, una por una. "
          "Cuando el bot registre una orden y pregunte si cargás otra, decí 'otra orden' y "
          "seguí con la SIGUIENTE del plan. NO menciones el pago hasta terminar la última. "
          "Recién cuando la ÚLTIMA orden del plan esté registrada, decí con tus palabras que "
          "ya está, y cuando pregunte el pago decí 'contraentrega'. Cuando el bot confirme "
          "el cierre del pedido, escribí '[FIN]'. NUNCA escribas '[FIN]' antes de eso. ")

# Cada persona: (estilo, plan de órdenes). Cada orden: (paciente, [códigos esperados]).
# Los códigos son del catálogo REAL. El estilo NUNCA es un guion perfecto.
PERSONAS = {
    "apurado_typos": (
        IDENT + "Escribís rapidísimo, con typos y sin tildes ('agreagar', 'perfl', 'kiero'). "
        "Datos del paciente en UN solo bloque. Respuestas secas ('si', 'no', 'dale'). "
        "Plan EN ORDEN: (1) Rocky, perro boxer macho 4 años, dueño Juan — pedí el perfil "
        "152 y despues agregale sodio y potasio (con typo: 'agreagar sodio y potasio'). "
        "(2) Misu, gata siames hembra 2 años, dueña Ana — el 1101 y el 1701 juntos. "
        "(3) Toby, perro criollo macho 8 años, dueño Luis — el perfil 653 solo. " + CIERRE,
        [("Rocky", ["152", "1405", "1404"]), ("Misu", ["1101", "1701"]), ("Toby", ["653"])],
    ),
    "corrector": (
        IDENT + "Te corregís TODO el tiempo. Plan EN ORDEN: (1) Nina, perra poodle hembra "
        "5 años, dueño Mario — pedí el perfil 152, agregale una glucosa, y EN EL RESUMEN "
        "decí 'mejor no, sacale la glucosa' y confirmá sin ella. Decí primero que el médico "
        "es 'dr peres' y corregite a 'dr ruiz' antes del resumen. "
        "(2) Simba, gato persa macho 3 años, dueña Carla — decí 'todo igual menos el "
        "análisis' cuando reofrezca, y pedí el 1101. " + CIERRE,
        [("Nina", ["152"]), ("Simba", ["1101"])],
    ),
    "charlatan": (
        IDENT + "Hablás de más: metés preguntas en el medio ('¿a qué hora pasan?', "
        "'¿cuánto me sale todo?') y después seguís. Plan EN ORDEN: (1) Luna, perra beagle "
        "hembra 6 años, dueño Pedro — un cuadro hemático (1101); preguntá el precio antes "
        "de confirmar. (2) Max, perro pastor macho 2 años, dueña Sofia — perfil 152 con "
        "sodio (1405) agregado; en el medio preguntá a qué hora pasa el motorizado. "
        "(3) Coco, loro macho 1 año, dueño Raul — preguntá si atienden aves y pedí un "
        "cuadro hemático (1101). " + CIERRE,
        [("Luna", ["1101"]), ("Max", ["152", "1405"]), ("Coco", ["1101"])],
    ),
    "masivo_5": (
        IDENT + "Cargás 5 pacientes seguidos, estilo telegráfico. Plan EN ORDEN: "
        "(1) P1, perro labrador macho 3 años, dueño A — perfil 152. "
        "(2) P2, gato criollo hembra 2 años, dueño B — 1101 y 1701. "
        "(3) P3, perro pug macho 5 años, dueño C — perfil 653 con potasio (1404) agregado. "
        "(4) P4, perra criolla hembra 1 año, dueño D — decí 'todo igual menos el análisis' "
        "y pedí el 1517. "
        "(5) P5, gato siamés macho 4 años, dueño E — perfil 152. " + CIERRE,
        [("P1", ["152"]), ("P2", ["1101", "1701"]), ("P3", ["653", "1404"]),
         ("P4", ["1517"]), ("P5", ["152"])],
    ),
    "maraton_10": (
        IDENT + "Cargás DIEZ pacientes seguidos, telegráfico y con algún typo. Plan EN "
        "ORDEN (paciente, datos, análisis): "
        "(1) M1 perro criollo macho 2 años dueño D1 — perfil 152. "
        "(2) M2 gata criolla hembra 3 años dueño D2 — 1101. "
        "(3) M3 perro boxer macho 4 años dueño D3 — 1101 y 1701. "
        "(4) M4 perra poodle hembra 5 años dueño D4 — perfil 653. "
        "(5) M5 gato persa macho 1 año dueño D5 — perfil 152 con sodio (1405). "
        "(6) M6 perro beagle macho 6 años dueño D6 — 1517. "
        "(7) M7 perra criolla hembra 7 años dueño D7 — perfil 152 (igual que el primero). "
        "(8) M8 gato siames macho 2 años dueño D8 — 1101. "
        "(9) M9 perro pastor macho 3 años dueño D9 — perfil 653 con potasio (1404). "
        "(10) M10 perra labrador hembra 4 años dueño D10 — 1701. " + CIERRE,
        [("M1", ["152"]), ("M2", ["1101"]), ("M3", ["1101", "1701"]), ("M4", ["653"]),
         ("M5", ["152", "1405"]), ("M6", ["1517"]), ("M7", ["152"]), ("M8", ["1101"]),
         ("M9", ["653", "1404"]), ("M10", ["1701"])],
    ),
    "caotico": (
        IDENT + "Respondés desordenado: a veces contestás OTRA cosa de la que preguntan "
        "(si piden el propietario, respondés el análisis), intentás pagar a mitad de la "
        "carga ('¿te pago ya?'), y una orden la CANCELÁS a mitad ('no, mejor esa no, "
        "borrala') y seguís con la siguiente. Plan: (1) K1, perro criollo macho 2 años, "
        "dueño X — perfil 152. (2) empezá una para 'K2' y cancelala a mitad. "
        "(3) K3, gata criolla hembra 5 años, dueño Z — 1101. " + CIERRE,
        [("K1", ["152"]), ("K3", ["1101"])],
    ),
}


def _items_de_orden(ai: dict) -> set[str]:
    """Códigos REALMENTE guardados en una orden registrada (estado, no texto).

    Fuente primaria: el payload de facturación (lo que va al PDF y a Alegra — la verdad del
    dinero). Fallback: los campos capturados."""
    payload = (ai.get("_event_payload") or {}).get("profile") or {}
    items = set()
    base = (payload.get("base_profile") or {}).get("code")
    if base:
        items.add(str(base))
    for t in (payload.get("added_tests") or []):
        if t.get("code"):
            items.add(str(t["code"]))
    if items:
        return items
    cf = ai.get("captured_fields") or {}
    if cf.get("_selected_profile_code"):
        items.add(str(cf["_selected_profile_code"]))
    for c in (cf.get("selected_tests") or []):
        items.add(str(c))
    for p in (cf.get("_extra_profiles") or []):
        if p.get("code"):
            items.add(str(p["code"]))
    return items


def _run(nombre: str, estilo: str, plan: list, max_turns: int = 120) -> dict:
    from app import agent, billing

    chat = f"estres-{nombre}"
    _reset(chat)
    facturas = []
    with patch.object(billing, "invoice_order",
                      side_effect=lambda *a, **k: facturas.append(a) or {"invoice_id": f"inv-{len(facturas)}", "number": "FE-X"}), \
         patch.object(agent, "ALEGRA_ENABLED", True):
        # El plan viaja también en el objetivo, numerado: el cliente-IA pierde el hilo en
        # conversaciones largas si el plan solo vive en la descripción inicial.
        objetivo = ("Tu plan, EN ORDEN (no saltees ninguna): "
                    + "; ".join(f"({i+1}) {pac}: códigos {','.join(cods)}"
                                for i, (pac, cods) in enumerate(plan))
                    + ". Cargá una por una y recién al final el pago.")
        transcript = []
        for _ in range(max_turns):
            msg = _cliente_simulado(estilo, transcript, objetivo)
            if "[FIN]" in msg:
                break
            transcript.append(("user", msg))
            try:
                reply = agent.process_turn(chat, msg) or "(silencio)"
            except Exception as exc:  # noqa: BLE001
                reply = f"[EXCEPCIÓN {type(exc).__name__}: {exc}]"
            transcript.append(("bot", reply))

    # ── Veredicto por ESTADO ──
    requests = _state.get("requests") or []
    fallos = []
    todos_los_codigos_planeados = [set(c) for _, c in plan]
    for i, (paciente, esperados) in enumerate(plan):
        if i >= len(requests):
            fallos.append(f"orden {i+1} ({paciente}): NO se registró")
            continue
        guardados = _items_de_orden(requests[i])
        faltan = set(esperados) - guardados
        if faltan:
            fallos.append(f"orden {i+1} ({paciente}): PERDIÓ {sorted(faltan)} (guardó {sorted(guardados)})")
        # Contaminación: códigos de OTRA orden del plan que no son de esta.
        ajenos = guardados - set(esperados)
        contaminantes = {c for c in ajenos
                         for j, cods in enumerate(todos_los_codigos_planeados)
                         if j != i and c in cods and c not in set(esperados)}
        if contaminantes:
            fallos.append(f"orden {i+1} ({paciente}): CONTAMINADA con {sorted(contaminantes)} de otra orden")
    if len(requests) > len(plan):
        fallos.append(f"se registraron {len(requests)} órdenes para un plan de {len(plan)} (duplicación)")
    # Cierre del pedido: fichas y factura única.
    campos = _state["session"].get("captured_fields") or {}
    cerrado = campos.get("_pedido_cerrado") is True
    if not cerrado:
        fallos.append("el pedido NO quedó cerrado")
    if len(facturas) != 1:
        fallos.append(f"facturas emitidas: {len(facturas)} (debe ser exactamente 1)")
    # Transcripción COMPLETA a archivo: el triage de una rotura necesita el contexto entero,
    # no los últimos 14 turnos.
    import os
    logdir = os.environ.get("ESTRES_LOG_DIR") or str(RAIZ / "tools" / "scripts")
    ruta = Path(logdir) / f"estres_transcript_{nombre}.txt"
    with open(ruta, "w", encoding="utf-8") as fh:
        for who, text in transcript:
            fh.write(f"{'CLIENTE' if who == 'user' else 'BOT'}: {text}\n\n")
    return {"nombre": nombre, "fallos": fallos, "n_requests": len(requests),
            "transcript": transcript}


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    elegidas = {k: v for k, v in PERSONAS.items() if not args or k in args}
    resultados = []
    for nombre, (estilo, plan) in elegidas.items():
        print("=" * 74)
        print(f"PERSONA {nombre} — {len(plan)} órdenes planificadas")
        r = _run(nombre, estilo, plan)
        resultados.append(r)
        if r["fallos"]:
            print(f"  [XX] {len(r['fallos'])} fallos:")
            for f in r["fallos"]:
                print(f"     - {f}")
            print("  --- transcripción (últimos 14 turnos) ---")
            for who, text in r["transcript"][-14:]:
                print(f"  {'C' if who == 'user' else 'B'}: {text[:130]}")
        else:
            print(f"  [OK] {r['n_requests']} órdenes registradas, pedido cerrado, 1 factura")
    print("\n" + "=" * 74)
    ok = sum(1 for r in resultados if not r["fallos"])
    print(f"RESUMEN: {ok}/{len(resultados)} personas sin fallos")
    for r in resultados:
        estado = "OK " if not r["fallos"] else "XX "
        print(f"  [{estado}] {r['nombre']:<16} {r['n_requests']} órdenes, {len(r['fallos'])} fallos")
    return 0 if ok == len(resultados) else 1


if __name__ == "__main__":
    raise SystemExit(main())
