"""QA de GUIONES REALES: cliente de REGLAS (sin IA) contra el agente real.

Pedido del usuario (2026-08-16): "quiero resolver problemas que saltan realmente en el
agente, no que la IA se invente errores". El cliente-IA del estrés ya rindió (7 bugs reales,
ERR-123→129) pero su ruido domina: acá el cliente es un mapa de reglas — responde a lo que
el bot pregunta con fraseos FIJOS tomados de conversaciones reales y de los bugs cazados.
Un rojo acá es un bug del AGENTE, reproducible siempre. Verdicto por ESTADO (L66).

Solo el AGENTE usa el modelo real. Escrituras parcheadas (regla dura).

Uso:  python tools/scripts/qa_guiones_reales.py [escenario ...]
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

for _p in [patch(f"app.services.db.{k}", **v) for k, v in _WRITE_PATCHES.items()]:
    _p.start()

from replay_chatwoot_qa import _create_request as _harness_create_request  # noqa: E402
from app.services import db as _dbmod  # noqa: E402


def _create_request_enriquecido(chat_id, session, ai, pedido_id=None):
    info = _harness_create_request(chat_id, session, ai, pedido_id=pedido_id)
    perfil = _dbmod._profile_event_payload(ai.get("captured_fields") or {})
    if info is not None:
        info["event_payload"] = {"profile": perfil} if perfil else {}
        if _state.get("requests"):
            _state["requests"][-1]["_event_payload"] = info["event_payload"]
    return info


patch("app.services.db.create_request", side_effect=_create_request_enriquecido).start()


def _cliente_de_reglas(bot: str, plan: list[dict], estado: dict) -> str | None:
    """Responde a la pregunta del bot con el dato del plan. Sin inventar NADA.
    `estado` lleva el índice de la orden en curso y los one-shots ya usados."""
    b = bot.lower()
    i = estado["orden"]
    orden = plan[i] if i < len(plan) else None

    # one-shots del escenario (fraseos especiales que se dicen UNA vez ante su disparador)
    for disparador, respuesta in (orden or {}).get("al", []):
        clave = (i, disparador)
        if disparador in b and clave not in estado["usados"]:
            estado["usados"].add(clave)
            return respuesta

    # PRIORIDAD: lo compuesto primero (el resumen contiene los keywords de TODOS los
    # campos; contestar por keyword de campo dentro del resumen desincroniza el guion).
    if "quedamos atentos" in b or "total del pedido" in b:
        return None  # pedido cerrado
    if "resumo la orden" in b or "¿confirmas" in b or "¿confirmás" in b:
        return (orden or {}).get("confirmacion") or "Sí, confirmo."
    if "mantengo estos datos" in b or "quieres cambiar alguno" in b:
        return (orden or {}).get("al_reofrecimiento") or "Confirmo esos datos."
    if "otra orden" in b and ("forma de pago" in b or "necesitas" in b):
        if i + 1 < len(plan):
            estado["orden"] += 1
            return "Otra orden, por favor."
        return "Eso es todo."
    if "forma de pago" in b or "cómo pagan" in b or "como pagan" in b:
        return "Contraentrega."
    if "agregamos otro análisis" in b or "quieres agregar" in b:
        return (orden or {}).get("agregado") or "No, así está bien."
    if "respóndeme con el número" in b or "con qué te ayudamos" in b:
        return "1"
    if "nit o el nombre" in b or "nombre exacto" in b:
        return "Animal Pets"
    if "¿es correcta" in b or "es correcta?" in b:
        return "Sí, correcta."
    if "observación" in b or "observaciones" in b:
        return "Sin observaciones."
    if "médico solicitante" in b:
        return "Dr. Ruiz"
    if "nombre del paciente" in b:
        return orden["paciente"] if orden else "—"
    if "especie" in b or "canino, felino" in b or "felino u otra" in b:
        return orden["especie"]
    if "raza" in b:
        return orden["raza"]
    if "macho o hembra" in b:
        return orden["sexo"]
    if "edad" in b:
        return orden["edad"]
    if "propietario" in b:
        return orden["dueno"]
    if "análisis o perfil desean" in b or "qué análisis" in b:
        return orden["analisis"]
    return None  # el bot no preguntó nada esperado: cortar y que lo diga el veredicto


# Escenarios: cada uno de un patrón REAL (conversaciones reales + los fraseos de los bugs).
ESCENARIOS = {
    "orden_simple_perfil": [
        {"paciente": "Bobi", "especie": "Canino", "raza": "Criollo", "sexo": "Macho",
         "edad": "3 años", "dueno": "Pol", "analisis": "Perfil 152", "esperado": ["152"]},
    ],
    "analisis_sueltos": [
        {"paciente": "Misu", "especie": "Felino", "raza": "Siamés", "sexo": "Hembra",
         "edad": "2 años", "dueno": "Ana", "analisis": "El 1101 y el 1701 juntos, por favor",
         "esperado": ["1101", "1701"]},
    ],
    "pago_en_el_resumen": [  # ERR-123: contesta el resumen con el pago
        {"paciente": "Duke", "especie": "Canino", "raza": "Pastor", "sexo": "Macho",
         "edad": "4 años", "dueno": "Gus", "analisis": "Perfil 152",
         "confirmacion": "Contraentrega.", "esperado": ["152"]},
    ],
    "direccion_nueva_sucursal": [  # ERR-129: rechaza la dirección CON la nueva escrita
        {"paciente": "Nala", "especie": "Canino", "raza": "Beagle", "sexo": "Hembra",
         "edad": "2 años", "dueno": "Tito", "analisis": "El 1101",
         "al": [("¿es correcta", "la dirección está mal, te di la de la nueva sucursal. Calle 45 Sur # 12-30.")],
         "esperado": ["1101"]},
    ],
    "multi_orden_3": [
        {"paciente": "Rocky", "especie": "Canino", "raza": "Boxer", "sexo": "Macho",
         "edad": "4 años", "dueno": "Juan", "analisis": "Perfil 152",
         "agregado": "Sí, agregale sodio y potasio", "esperado": ["152", "1404", "1405"]},
        {"paciente": "Misu", "especie": "Felino", "raza": "Siamés", "sexo": "Hembra",
         "edad": "2 años", "dueno": "Ana", "analisis": "1101 y 1701",
         "al_reofrecimiento": "Todo igual menos el análisis",
         "esperado": ["1101", "1701"]},
        {"paciente": "Toby", "especie": "Canino", "raza": "Criollo", "sexo": "Macho",
         "edad": "8 años", "dueno": "Luis", "analisis": "El perfil 653 solo",
         "al_reofrecimiento": "Todo igual menos el análisis",
         "esperado": ["653"]},
    ],
}


def _items_de(req: dict) -> set[str]:
    payload = (req.get("_event_payload") or {}).get("profile") or {}
    items = {str((payload.get("base_profile") or {}).get("code") or "")} - {""}
    items |= {str(t["code"]) for t in (payload.get("added_tests") or []) if t.get("code")}
    if items:
        return items
    cf = req.get("captured_fields") or {}
    items = {str(cf.get("_selected_profile_code") or "")} - {""}
    items |= {str(c) for c in (cf.get("selected_tests") or [])}
    return items


def correr(nombre: str, plan: list[dict], max_turns: int = 60) -> list[str]:
    from app import agent, billing

    chat = f"guion-{nombre}"
    _reset(chat)
    facturas = []
    estado = {"orden": 0, "usados": set()}
    transcript = []
    with patch.object(billing, "invoice_order",
                      side_effect=lambda *a, **k: facturas.append(a) or {"invoice_id": "i", "number": "F"}), \
         patch.object(agent, "ALEGRA_ENABLED", True):
        msg = "Hola, buenas."
        for _ in range(max_turns):
            transcript.append(("C", msg))
            reply = agent.process_turn(chat, msg) or ""
            transcript.append(("B", reply))
            msg = _cliente_de_reglas(reply, plan, estado)
            if msg is None:
                break

    fallos = []
    requests = _state.get("requests") or []
    for o in plan:
        req = next((r for r in requests
                    if ((r.get("captured_fields") or {}).get("patient_name") or "").strip().lower()
                    == o["paciente"].lower()), None)
        if req is None:
            fallos.append(f"{o['paciente']}: NO se registró")
            continue
        falta = set(o["esperado"]) - _items_de(req)
        sobra = _items_de(req) - set(o["esperado"])
        if falta:
            fallos.append(f"{o['paciente']}: PERDIÓ {sorted(falta)} (guardó {sorted(_items_de(req))})")
        if sobra:
            fallos.append(f"{o['paciente']}: DE MÁS {sorted(sobra)}")
    if len(requests) != len(plan):
        fallos.append(f"órdenes registradas: {len(requests)} para un plan de {len(plan)}")
    campos = _state["session"].get("captured_fields") or {}
    if campos.get("_pedido_cerrado") is not True:
        fallos.append("el pedido NO quedó cerrado")
    if len(facturas) != 1:
        fallos.append(f"facturas: {len(facturas)} (esperada 1)")
    if fallos:
        print("  --- últimos turnos ---")
        for w, t in transcript[-10:]:
            print(f"  {w}: {t[:120]}")
    return fallos


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    elegidos = {k: v for k, v in ESCENARIOS.items() if not args or k in args}
    total = 0
    for nombre, plan in elegidos.items():
        print("=" * 74)
        print(f"GUION {nombre} — {len(plan)} orden(es)")
        fallos = correr(nombre, plan)
        total += len(fallos)
        if fallos:
            print(f"  [XX] {len(fallos)} fallos:")
            for f in fallos:
                print(f"     - {f}")
        else:
            print("  [OK] estado limpio: órdenes, pedido cerrado, 1 factura")
    print("=" * 74)
    print(f"TOTAL: {total} fallos en {len(elegidos)} guiones")
    return 0 if total == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
