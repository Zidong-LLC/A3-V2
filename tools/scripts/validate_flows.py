"""
Validación END-TO-END de los flujos conversacionales contra el modelo REAL.
Mockea solo Supabase (BD en memoria); `ai.generate_turn` e `interpret_*` son reales.

Recorre conversaciones completas (multi-turno) y detecta automáticamente:
- bucles (misma respuesta del bot repetida)
- frases robóticas de fallback
- cierres sin orden creada / derivaciones incorrectas

Uso:  python tools/scripts/validate_flows.py
"""
import re
import sys
from pathlib import Path
from unittest.mock import patch

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

CLIENT = {
    "id": "client-001", "clinic_name": "Veterinaria San Roque", "tax_id": "900123456",
    "phone": "6015551234", "address": "Calle 45 # 12-34, Bogotá",
}
COURIER = {"id": "courier-01", "name": "Carlos", "phone": "300111", "availability": "available"}

# Mini-catálogo realista para ejercitar el RACIMO DE ANÁLISIS con el modelo real
# (perfil por necesidad diagnóstica, análisis por área y selección "el primero").
# Sin estos datos los mocks devolvían vacío y el racimo nunca se probaba de verdad.
URO_TESTS = [
    {"code": "1601", "name": "Uroanálisis Completo", "category": "Uroanálisis", "sample": "Orina Fresca", "price": 35000},
    {"code": "1602", "name": "Relación Proteína Orina", "category": "Uroanálisis", "sample": "Orina Fresca", "price": 48000},
    {"code": "1603", "name": "Urocultivo", "category": "Uroanálisis", "sample": "Orina Fresca", "price": 52000},
]
RENAL_LABEL = "RENAL"
RENAL_TESTS = [
    {"code": "0101", "name": "Creatinina", "price": 22000, "category": "Química"},
    {"code": "0102", "name": "BUN", "price": 22000, "category": "Química"},
]
# Catálogo combinado de análisis individuales para resolver get_tests_by_codes_or_names
# (lo usan _enforce_multiple_tests_capture y _enforce_profile_customization_changes).
EXTRA_TESTS = [
    {"code": "0001", "name": "Hemograma Completo", "price": 30000, "category": "Hematología"},
    {"code": "0201", "name": "Glucosa", "price": 18000, "category": "Química"},
]
ALL_TESTS = URO_TESTS + RENAL_TESTS + EXTRA_TESTS

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


def _norm(text):
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def _match_client(query):
    q = _norm(query)
    return bool(q) and (_norm("San Roque") in q or q in _norm(CLIENT["clinic_name"]))


def _area_tests(value, species=None, limit=15):
    """find_tests_by_area: solo 'orina' tiene catálogo (Uroanálisis)."""
    return ("Uroanálisis", URO_TESTS[:limit]) if "orina" in _norm(value) else (None, [])


def _find_label(query):
    """find_diagnostic_label: 'renal' mapea a la etiqueta RENAL."""
    return RENAL_LABEL if "renal" in _norm(query) else None


def _tests_for_label(label):
    return RENAL_TESTS if label == RENAL_LABEL else []


def _tests_by_names(items):
    """get_tests_by_codes_or_names: un test por ítem (código o nombre, contención).
    Devuelve a lo sumo un match por ítem para que el mapeo 1:1 del agente funcione."""
    out = []
    for raw in items or []:
        k = _norm(raw)
        if not k:
            continue
        for t in ALL_TESTS:
            name_k = _norm(t["name"])
            if k == _norm(t["code"]) or k == name_k or k in name_k or name_k in k:
                out.append(t)
                break
    return out


_PATCHES = {
    "get_or_create_session": dict(side_effect=lambda c, channel="telegram": _state["session"]),
    "get_recent_messages": dict(side_effect=lambda c, limit=8: _state["history"][-limit:]),
    "save_message": dict(side_effect=lambda c, t, r: _state["history"].append({"role": r, "content": t})),
    "update_session": dict(side_effect=lambda c, ai: _state["session"].update(
        phase_current=ai["phase"], intent_current=ai["intent"], captured_fields=ai["captured_fields"])),
    "link_client_to_session": dict(side_effect=lambda c, cid: _state["session"].update(client_id=cid)),
    "clear_client_from_session": dict(side_effect=lambda c: _state["session"].update(client_id=None)),
    "get_client_by_id": dict(side_effect=lambda cid: CLIENT if cid == CLIENT["id"] else None),
    "find_client_matches": dict(side_effect=lambda q, limit=6: [CLIENT] if _match_client(q) else []),
    "find_clients_by_tax_id": dict(side_effect=lambda t: [CLIENT] if _norm(t) == _norm(CLIENT["tax_id"]) else []),
    "get_courier_for_client": dict(return_value=COURIER),
    "create_request": dict(side_effect=lambda c, s, ai: (
        _state["requests"].append(ai), {"request_id": f"req-{len(_state['requests'])}",
                                        "order_number": f"A3-2026-00{len(_state['requests'])}"})[1]),
    "create_pending_client_review": dict(side_effect=lambda cl, rv: _state["pending_clients"].append((cl, rv))),
    "get_last_order_for_client": dict(return_value={"order_number": "A3-2026-001", "exam_type": "hemograma"}),
    "get_catalog_context": dict(return_value=""),
    "get_individual_tests_context": dict(return_value=""),
    "list_diagnostic_labels": dict(return_value=[RENAL_LABEL]),
    "find_diagnostic_label": dict(side_effect=_find_label),
    "get_tests_for_label": dict(side_effect=_tests_for_label),
    "find_catalog_profiles": dict(return_value=[]),
    "find_catalog_profile": dict(return_value=None),
    "get_catalog_profiles_by_codes": dict(return_value=[]),
    "find_tests_by_area": dict(side_effect=_area_tests),
    "get_tests_by_codes_or_names": dict(side_effect=_tests_by_names),
    "get_tests_by_codes": dict(side_effect=_tests_by_names),
}

ROBOTIC_MARKERS = ("dato que tengas a mano", "escribe 'hablar con alguien'")


def _run_conversation(title, chat_id, turns, final_checks):
    """turns: lista de mensajes del usuario. final_checks: fn(replies) -> list[str] issues.
    Filtro opcional: `python validate_flows.py F K` corre solo esos flujos (por prefijo)."""
    only = [a.upper() for a in sys.argv[1:]]
    if only and not any(title.upper().startswith(o) for o in only):
        return (title, "SKIP", [])
    from app.agent import process_turn
    _reset(chat_id)
    print("=" * 72)
    print(f"FLUJO: {title}")
    replies = []
    issues = []
    for msg in turns:
        try:
            reply = process_turn(chat_id, msg)
        except Exception as exc:  # noqa: BLE001
            issues.append(f"EXCEPCIÓN en turno '{msg[:40]}': {type(exc).__name__}: {exc}")
            break
        print(f"  USR: {msg}")
        print(f"  BOT: {reply}")
        print("  -")
        replies.append(reply)

    # Detección de bucles y frases robóticas
    bot_replies = [r for r in replies if r]
    for prev, cur in zip(bot_replies, bot_replies[1:]):
        if prev == cur:
            issues.append(f"BUCLE: respuesta idéntica consecutiva: '{cur[:70]}'")
    for r in bot_replies:
        for marker in ROBOTIC_MARKERS:
            if marker in r:
                issues.append(f"ROBÓTICO: '{marker}' en: '{r[:70]}'")

    try:
        issues.extend(final_checks(replies))
    except Exception as exc:  # noqa: BLE001
        issues.append(f"ERROR en checks finales: {type(exc).__name__}: {exc}")
    status = "OK" if not issues else "PROBLEMAS"
    print(f"  >>> {status}")
    for issue in issues:
        print(f"      ! {issue}")
    return title, status, issues


def main():
    patchers = [patch(f"app.services.db.{n}", **kw) for n, kw in _PATCHES.items()]
    for p in patchers:
        p.start()
    results = []
    try:
        # A — Camino feliz completo + segunda orden con "el de siempre"
        def checks_a(replies):
            out = []
            if len(_state["requests"]) != 1:
                out.append(f"esperaba 1 orden creada, hay {len(_state['requests'])}")
            closing = replies[14] or ""
            if "A3-2026" not in closing:
                out.append("el cierre no incluye el número de orden")
            if "Quedó registrado" not in closing:
                out.append("el cierre no muestra el resumen")
            second = replies[16] or ""
            if "Laura" not in second and "Méndez" not in second.replace("Mendez", "Méndez"):
                out.append(f"'el de siempre' no reofreció el médico recordado: '{second[:80]}'")
            return out

        results.append(_run_conversation(
            "A. Camino feliz completo + multi-orden", "val-a",
            ["Hola", "1", "Somos la Veterinaria San Roque", "sí, esa está bien",
             "Dra. Laura Méndez", "Firulais", "canino", "labrador", "macho",
             "3 años", "Pedro Gómez", "sin observaciones", "hemograma",
             "contraentrega", "sí, confirmo",
             "sí, quiero otra orden para otro paciente", "el de siempre"],
            checks_a,
        ))

        # B — Cliente nuevo (no registrado) → derivación inmediata y bloqueo
        def checks_b(replies):
            out = []
            if _state["pending_clients"]:
                out.append("se abrió el Flujo B legacy y guardó cliente pendiente")
            if len(_state["requests"]) != 1:
                out.append(f"esperaba 1 solicitud de derivación, hay {len(_state['requests'])}")
            if _state["session"]["phase_current"] != "fase_7_escalado":
                out.append(f"cliente nuevo no escaló (phase={_state['session']['phase_current']})")
            if replies[-1] is not None:
                out.append("la sesión no quedó bloqueada tras derivar (siguió respondiendo)")
            if not (_state["session"]["captured_fields"].get("_blocked")):
                out.append("falta el flag _blocked en la sesión")
            return out

        results.append(_run_conversation(
            "B. Cliente nuevo → derivación inmediata", "val-b",
            ["Hola", "Quiero programar una recogida de muestras",
              "Veterinaria Patitas Felices", "sí, somos nuevos", "sí",
              "Patitas Felices", "Dr. Andrés Rojas", "Carrera 7 # 45-10",
             "3019876543", "sí, correctos", "y ahora qué hago?"],
            checks_b,
        ))

        # C — Particular (dueño de mascota): bloquear, no atender
        def checks_c(replies):
            out = []
            if replies[-1] is not None:
                out.append("el particular bloqueado recibió respuesta")
            if _state["requests"]:
                out.append("se creó una orden para un particular")
            return out

        results.append(_run_conversation(
            "C. Particular → bloqueo", "val-c",
            ["Hola", "Hola, soy el dueño de mi perrito y quiero un hemograma", "por favor, atiéndanme"],
            checks_c,
        ))

        # D — Pagos: derivar a contabilidad
        def checks_d(replies):
            out = []
            if _state["session"]["phase_current"] != "fase_7_escalado":
                out.append(f"pagos no escaló (phase={_state['session']['phase_current']})")
            return out

        results.append(_run_conversation(
            "D. Pagos → contabilidad", "val-d",
            ["Hola", "3"], checks_d,
        ))

        # E — Resultados: mensaje fijo (aún no disponible)
        def checks_e(replies):
            out = []
            if "no está disponible" not in (replies[-1] or ""):
                out.append(f"la opción 2 no dio el mensaje de resultados: '{(replies[-1] or '')[:80]}'")
            return out

        results.append(_run_conversation(
            "E. Resultados (opción 2)", "val-e",
            ["Hola", "2"], checks_e,
        ))

        # F — Cliente caótico: NIT, off-topic, typos, datos en bloque, edad sin unidad, pago en línea
        def checks_f(replies):
            out = []
            if len(_state["requests"]) != 1:
                out.append(f"esperaba 1 orden creada, hay {len(_state['requests'])}")
                return out
            f = _state["requests"][-1].get("captured_fields") or {}
            if _norm(f.get("species")) != "felino":
                out.append(f"especie esperada Felino, quedó {f.get('species')!r}")
            if _norm(f.get("sex")) != "hembra":
                out.append(f"sexo esperado Hembra, quedó {f.get('sex')!r}")
            if "mes" not in (f.get("patient_age") or ""):
                out.append(f"edad esperada en meses, quedó {f.get('patient_age')!r}")
            if _state["session"]["phase_current"] != "fase_7_escalado":
                out.append("pago en línea no derivó a contabilidad")
            return out

        results.append(_run_conversation(
            "F. Cliente caótico (typos, off-topic, datos en bloque)", "val-f",
            ["Hola", "1", "nit 900123456", "jaja y cómo va el día por allá?",
             "sí, esa dirección está bien",
             "la médica es la Dra. Sofía Ramírez y el paciente es Michi, un gatito",
             "siamés", "hembra", "5", "meses", "Lucía Torres", "ninguna",
             "hemograma", "pago en línea", "sí, confirmo"],
            checks_f,
        ))

        # G — Perfil por necesidad diagnóstica (etiqueta): el bot sugiere las pruebas
        #     en vez de clavarse. Racimo análisis: _enforce_diagnostic_label_help.
        def checks_g(replies):
            out = []
            suggestion = replies[4] or ""
            if "Creatinina" not in suggestion and "BUN" not in suggestion and "renal" not in suggestion.lower():
                out.append(f"el perfil renal no sugirió las pruebas: '{suggestion[:90]}'")
            return out

        results.append(_run_conversation(
            "G. Perfil por necesidad diagnóstica (renal)", "val-g",
            ["Hola", "1", "Somos la Veterinaria San Roque", "sí, esa está bien",
             "necesito un perfil renal para un paciente"],
            checks_g,
        ))

        # H — "El primero" de una lista de análisis por área (caso ERR-017).
        #     El bot despliega Uroanálisis numerado y "el primero" debe capturar el
        #     análisis REAL del catálogo, no el texto genérico "orina".
        def checks_h(replies):
            out = []
            menu = replies[4] or ""
            if "1" not in menu or "uroanálisis" not in menu.lower().replace("analisis", "análisis"):
                out.append(f"no se desplegó el menú de Uroanálisis: '{menu[:90]}'")
            f = _state["session"]["captured_fields"]
            sel = f.get("selected_tests") or []
            # selected_tests puede guardar dicts o strings; normalizamos a un blob.
            blob = _norm("".join(
                (str(t.get("code", "")) + str(t.get("name", ""))) if isinstance(t, dict) else str(t)
                for t in sel
            )) + _norm(f.get("exam_type"))
            if "1601" not in blob and "uroanalisiscompleto" not in blob:
                out.append(
                    f"'el primero' no capturó el análisis real del menú "
                    f"(selected={sel}, exam_type={f.get('exam_type')!r})"
                )
            return out

        results.append(_run_conversation(
            "H. 'El primero' de lista por área (orina)", "val-h",
            ["Hola", "1", "Somos la Veterinaria San Roque", "sí, esa está bien",
             "quiero un análisis de orina", "el primero"],
            checks_h,
        ))

        # J — Opción 4 "Otro" (ERR-005): handoff determinista a operaciones.
        def checks_j(replies):
            out = []
            if _state["session"]["phase_current"] != "fase_7_escalado":
                out.append(f"la opción 4 no escaló (phase={_state['session']['phase_current']})")
            return out

        results.append(_run_conversation(
            "J. Opción 4 (Otro) → operaciones", "val-j",
            ["Hola", "4"], checks_j,
        ))

        # K — Veterinario independiente no registrado (ERR-010): escala, sin bucle
        #     de "compárteme el NIT".
        def checks_k(replies):
            out = []
            if _state["session"]["phase_current"] != "fase_7_escalado":
                out.append(f"el independiente no escaló (phase={_state['session']['phase_current']})")
            nit_asks = sum(1 for r in replies if r and "nit" in r.lower())
            if nit_asks > 1:
                out.append(f"repitió la pregunta del NIT {nit_asks} veces (bucle de identificación)")
            return out

        results.append(_run_conversation(
            "K. Veterinario independiente → escala sin bucle", "val-k",
            ["Hola", "1", "Clínica Inexistente del Norte",
             "ahora estoy trabajando de forma independiente"],
            checks_k,
        ))

        # L — Cliente registrado pide SEDE NUEVA (ERR-012): ofrecer derivar o seguir,
        #     no clavarse en la lista de sedes.
        def checks_l(replies):
            out = []
            last = (replies[-1] or "").lower()
            if not any(k in last for k in ("registr", "deriv", "sede", "operacion", "comunic")):
                out.append(f"no ofreció derivar/seguir ante sede nueva: '{(replies[-1] or '')[:90]}'")
            return out

        results.append(_run_conversation(
            "L. Sede nueva no registrada → ofrecer derivar", "val-l",
            ["Hola", "1", "Somos la Veterinaria San Roque",
             "en realidad es para una sede nueva que aún no está registrada"],
            checks_l,
        ))

        # M — Corrección editable en confirmación (FASE 2 #12): "corregir paciente"
        #     no registra y el cierre final queda con el dato corregido.
        def checks_m(replies):
            out = []
            if len(_state["requests"]) != 1:
                out.append(f"esperaba 1 orden creada tras corregir, hay {len(_state['requests'])}")
                return out
            f = _state["requests"][-1].get("captured_fields") or {}
            if "rocky" not in _norm(f.get("patient_name")):
                out.append(f"la corrección del paciente no quedó en el cierre: patient_name={f.get('patient_name')!r}")
            return out

        results.append(_run_conversation(
            "M. Corrección editable en confirmación", "val-m",
            ["Hola", "1", "Somos la Veterinaria San Roque", "sí, esa está bien",
             "Dra. Laura Méndez", "Firulais", "canino", "labrador", "macho",
             "3 años", "Pedro Gómez", "sin observaciones", "hemograma",
             "contraentrega", "espera, corrige el paciente: ahora se llama Rocky",
             "sí, confirmo"],
            checks_m,
        ))

        # N — ESTRÉS racimo 2: cliente evasivo en un campo de texto (médico). El modelo
        #     repregunta de forma natural; ¿_avoid_repeated_question lo pisa con plantilla?
        #     (la detección automática RACIMO2 marca si ocurrió).
        results.append(_run_conversation(
            "N. Estrés racimo 2 — repetición en médico", "val-n",
            ["Hola", "1", "Somos la Veterinaria San Roque", "sí, esa está bien",
             "uy, no recuerdo el nombre del médico ahora mismo",
             "déjame pensarlo un momento"],
            lambda replies: [],
        ))

        # O — ESTRÉS racimo 2: especie ambigua repetida (enumerado). El modelo debería
        #     confirmar/ofrecer opciones; ¿el guard la reemplaza por la plantilla fija?
        results.append(_run_conversation(
            "O. Estrés racimo 2 — especie ambigua repetida", "val-o",
            ["Hola", "1", "Somos la Veterinaria San Roque", "sí, esa está bien",
             "Dra. Laura Méndez", "Firulais", "es un animalito pequeño",
             "uno chiquito de la casa"],
            lambda replies: [],
        ))

        # P — ESTRÉS racimo 1: varios análisis en un mensaje (multiple_tests). Cuando el
        #     modelo los captura juntos, se registran como perfil 1:1. Observacional: el
        #     modelo no siempre los da en una sola lista (no determinista), así que solo
        #     verificamos que no haya bucle ni respuesta robótica (detección automática).
        results.append(_run_conversation(
            "P. Estrés racimo 1 — varios análisis en un mensaje", "val-p",
            ["Hola", "1", "Somos la Veterinaria San Roque", "sí, esa está bien",
             "Dra. Laura Méndez", "Firulais", "canino", "labrador", "macho",
             "3 años", "Pedro Gómez", "sin observaciones",
             "necesito hemograma, creatinina y glucosa"],
            lambda replies: [],
        ))

        # Q — ESTRÉS racimo 1: perfil por etiqueta + personalización iterativa
        #     (diagnostic_label → customization_changes → custom_profile_close).
        #     Observacional: que no entre en bucle ni saque plantilla robótica.
        results.append(_run_conversation(
            "Q. Estrés racimo 1 — perfil renal + personalización", "val-q",
            ["Hola", "1", "Somos la Veterinaria San Roque", "sí, esa está bien",
             "necesito un perfil renal", "quiero agregarle un urocultivo",
             "mejor quita la creatinina", "listo, cerramos así"],
            lambda replies: [],
        ))

        # R — ESTRÉS racimo 1: mensaje ambiguo que puede tocar varios guards a la vez
        #     (etiqueta 'renal' + área 'orina' + 'varios'). Exhibe si se pisan entre sí.
        results.append(_run_conversation(
            "R. Estrés racimo 1 — solapamiento (renal + orina)", "val-r",
            ["Hola", "1", "Somos la Veterinaria San Roque", "sí, esa está bien",
             "quiero un perfil renal y también un análisis de orina"],
            lambda replies: [],
        ))

        # M2 — Borde ERR-018: corregir SIN dar el valor. El bot pregunta el dato; al
        #      recibirlo debe RE-MOSTRAR el resumen antes del "sí" (y cerrar con el cambio).
        def checks_m2(replies):
            out = []
            if len(_state["requests"]) != 1:
                out.append(f"esperaba 1 orden creada, hay {len(_state['requests'])}")
                return out
            f = _state["requests"][-1].get("captured_fields") or {}
            if "rocky" not in _norm(f.get("patient_name")):
                out.append(f"la corrección no quedó en el cierre: patient_name={f.get('patient_name')!r}")
            after_value = replies[15] or ""
            if "Rocky" not in after_value or ("¿Confirmas" not in after_value and "resumo" not in after_value.lower()):
                out.append(f"no re-mostró el resumen tras dar el dato corregido: '{after_value[:90]}'")
            return out

        results.append(_run_conversation(
            "M2. Corrección sin valor → re-muestra resumen", "val-m2",
            ["Hola", "1", "Somos la Veterinaria San Roque", "sí, esa está bien",
             "Dra. Laura Méndez", "Firulais", "canino", "labrador", "macho",
             "3 años", "Pedro Gómez", "sin observaciones", "hemograma",
             "contraentrega", "corrige el nombre del paciente", "Rocky",
             "sí, confirmo"],
            checks_m2,
        ))

        # S — Dato fuera de orden (R25): al pedir la ESPECIE el cliente da el SEXO
        #     ("es hembra"). Debe capturar el sexo, repreguntar la especie, y luego NO
        #     volver a pedir el sexo (ya lo tiene). La orden cierra coherente.
        def checks_s(replies):
            out = []
            if len(_state["requests"]) != 1:
                out.append(f"esperaba 1 orden creada, hay {len(_state['requests'])}")
                return out
            f = _state["requests"][-1].get("captured_fields") or {}
            if _norm(f.get("sex")) != "hembra":
                out.append(f"el sexo adelantado ('es hembra' al pedir especie) no se capturó: sex={f.get('sex')!r}")
            if _norm(f.get("species")) != "canino":
                out.append(f"la especie no quedó canino: species={f.get('species')!r}")
            return out

        results.append(_run_conversation(
            "S. Dato fuera de orden (sexo al pedir especie)", "val-s",
            ["Hola", "1", "Somos la Veterinaria San Roque", "sí, esa está bien",
             "Dra. Laura Méndez", "Firulais", "es hembra", "canino", "labrador",
             "3 años", "Pedro Gómez", "sin observaciones", "hemograma",
             "contraentrega", "sí, confirmo"],
            checks_s,
        ))
    finally:
        for p in patchers:
            p.stop()

    print("=" * 72)
    print("RESUMEN")
    for title, status, issues in results:
        if status == "SKIP":
            continue
        print(f"  [{status}] {title}")
    ran = [r for r in results if r[1] != "SKIP"]
    bad = [r for r in ran if r[1] != "OK"]
    print(f"\n{len(ran) - len(bad)}/{len(ran)} flujos OK")
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
