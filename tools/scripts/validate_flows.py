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
def _load_real_tests() -> list[dict]:
    """El catálogo REAL de análisis (159 filas). Nada de listas a mano.

    Antes había tres listas inventadas (URO/RENAL/EXTRA) cuyos códigos CHOCABAN con los reales:
    1603 era "Urocultivo $52k" a mano y "Estudio de Cálculo $83k" en la base, así que el bot
    anunciaba un precio y el resumen mostraba otro. Un harness incoherente hace fallar flujos
    que no tienen nada roto — y peor, puede tapar los que sí. Se valida contra la base."""
    try:
        from app.services import db as _db
        rows = _db.list_catalog_tests(limit=5000)
        if rows:
            print(f"[catálogo de análisis REAL: {len(rows)} filas]")
            return rows
    except Exception as exc:  # noqa: BLE001
        print(f"[sin catálogo real ({type(exc).__name__}): los flujos de análisis no son válidos]")
    return []


ALL_TESTS = _load_real_tests()


def _by_category(needle: str) -> list[dict]:
    return [r for r in ALL_TESTS if needle.lower() in str(r.get("category") or "").lower()]


URO_TESTS = _by_category("uro")[:3]
RENAL_LABEL = "RENAL"
# Etiqueta diagnóstica renal: los análisis reales que la componen.
RENAL_TESTS = [r for r in ALL_TESTS
               if str(r.get("name", "")).lower().startswith("creatinina")
               or "bun" in str(r.get("name", "")).lower()][:2]
EXTRA_TESTS = [r for r in ALL_TESTS
               if str(r.get("name", "")).lower().startswith(("cuadro hem", "glucosa"))][:2]

# Catálogo de razas: se trae el REAL de Supabase (323 razas / 332 filas) porque los casos que
# importan —las 8 ambiguas, las que chocan con palabras de especie, el par boer/boxer— solo
# existen en el catálogo completo. Si no hay red, cae a una muestra mínima y los flujos de raza
# quedan sin valor pero el resto del validador sigue corriendo.
_FALLBACK_BREEDS = [
    {"breed_key": "pastor_aleman", "name": "Pastor Alemán", "species": "Canino"},
    {"breed_key": "labrador", "name": "Labrador", "species": "Canino"},
    {"breed_key": "pitbull", "name": "Pitbull", "species": "Canino"},
    {"breed_key": "siames", "name": "Siamés", "species": "Felino"},
    {"breed_key": "mestizo", "name": "Mestizo", "species": "Canino"},
    {"breed_key": "mestizo", "name": "Mestizo", "species": "Felino"},
]


def _load_real_breeds() -> list[dict]:
    try:
        from app.services import db as _db
        rows = _db.list_catalog_breeds()
        if rows:
            print(f"[catálogo de razas REAL: {len(rows)} filas]")
            return rows
    except Exception as exc:  # noqa: BLE001
        print(f"[sin catálogo real ({type(exc).__name__}), usando muestra mínima]")
    return _FALLBACK_BREEDS


BREEDS = _load_real_breeds()

# Perfiles de catálogo para la recomendación por especie ('no sé / qué me recomiendas')
# y para resolver la selección con código y precio reales.
CATALOG_PROFILES = [
    {"code": "301", "name": "Perfil Felinos I", "category": "Perfiles Felinos", "species": "felino",
     "description": "Cuadro Hemático, Creatinina, GGT, Coproscópico", "price": 43000},
    {"code": "302", "name": "Perfil Felino II", "category": "Perfiles Felinos", "species": "felino",
     "description": "Creatinina, BUN/UREA, GGT", "price": 27000},
    {"code": "401", "name": "Perfil Canino I", "category": "Perfiles Caninos", "species": "canino",
     "description": "Cuadro Hemático, Creatinina, ALT", "price": 40000},
    {"code": "402", "name": "Perfil Canino II", "category": "Perfiles Caninos", "species": "canino",
     "description": "Glucosa, BUN/UREA, Creatinina", "price": 30000},
    {"code": "501", "name": "Perfil Renal I", "category": "Perfiles Renales", "species": "ambos",
     "description": "Cuadro Hemático, Parcial de Orina, BUN/UREA, Creatinina", "price": 34000},
    # Categoría con perfiles ARMADOS pedida por nombre (ERR-045: 'pre quirúrgico').
    {"code": "701", "name": "Perfil Prequirúrgico I", "category": "Prequirúrgico", "species": "ambos",
     "description": "Cuadro Hemático, ALT, Creatinina", "price": 24000},
    {"code": "702", "name": "Perfil Prequirúrgico II", "category": "Prequirúrgico", "species": "ambos",
     "description": "Cuadro Hemático, ALT, Creatinina, Glucosa", "price": 36000},
]


def _profiles_for_species(species=None, limit=6):
    key = (species or "").strip().lower()
    if key in ("canino", "felino"):
        rows = [p for p in CATALOG_PROFILES if p["species"] in (key, "ambos")]
    else:
        rows = list(CATALOG_PROFILES)
    rows.sort(key=lambda r: 0 if r["species"] == key else 1)
    return rows[:limit]


def _profiles_by_codes(codes, species=None):
    cset = {str(c).strip() for c in (codes or [])}
    return [p for p in CATALOG_PROFILES if p["code"] in cset]


def _find_one_profile(value, species=None):
    """find_catalog_profile: resuelve un perfil por código o por nombre (contención)."""
    key = _norm(value)
    if not key:
        return None
    for p in CATALOG_PROFILES:
        if _norm(p["code"]) in key or _norm(p["name"]) in key or key in _norm(p["name"]):
            return p
    return None

def _profiles_matching_category(text, species=None, limit=12):
    """list_catalog_profiles_matching_category: usa el filtro puro REAL sobre el mock."""
    from app.services.db import filter_profiles_by_category_mention
    key = (species or "").strip().lower()
    rows = [p for p in CATALOG_PROFILES
            if key not in ("canino", "felino") or p["species"] in (key, "ambos")]
    return filter_profiles_by_category_mention(rows, text)[:limit]


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


def _find_label(query, species=None):
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
    "list_catalog_breeds": dict(return_value=BREEDS),
    "get_catalog_context": dict(return_value=""),
    "get_individual_tests_context": dict(return_value=""),
    "list_diagnostic_labels": dict(return_value=[RENAL_LABEL]),
    "find_diagnostic_label": dict(side_effect=_find_label),
    "get_tests_for_label": dict(side_effect=_tests_for_label),
    "find_catalog_profiles": dict(return_value=[]),
    "find_catalog_profile": dict(side_effect=_find_one_profile),
    "get_catalog_profiles_by_codes": dict(side_effect=_profiles_by_codes),
    "list_catalog_profiles_for_species": dict(side_effect=_profiles_for_species),
    "list_catalog_profiles_matching_category": dict(side_effect=_profiles_matching_category),
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
            menu = replies[5] or ""
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
             "sí, esa dirección está bien", "quiero un análisis de orina", "el primero"],
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
             "necesito un perfil renal", "quiero agregarle un parcial de orina",
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

        # T — Preventa/metodología antes de identificarse: responder como persona y NO
        #     capturar una explicación clínica como nombre de veterinaria.
        def checks_t(replies):
            out = []
            joined = " ".join((r or "") for r in replies).lower()
            if "no encuentro" in joined:
                out.append("buscó cliente antes de recibir un identificador real")
            f = _state["session"]["captured_fields"]
            if "motivos" in _norm(f.get("clinic_name")) or "muerte" in _norm(f.get("clinic_name")):
                out.append(f"capturó una explicación clínica como cliente: {f.get('clinic_name')!r}")
            if _state["requests"]:
                out.append("creó una solicitud durante preguntas de preventa")
            last = (replies[-1] or "").lower()
            if "nit" not in last or "nombre" not in last:
                out.append(f"no retomó identificación al pedir programar: '{(replies[-1] or '')[:90]}'")
            return out

        results.append(_run_conversation(
            "T. Preventa/metodología no dispara identificación", "val-t",
            ["Hola",
             "hacen analisis para mascotas verdad? atienden en Colombia?",
             "como es la metodologia si tengo una muestra para analizar que necesito?",
             "?ustedes se encargan de retirar las muestras tienen gente asiganada para eso?",
             "tengo que hacer un analisis a un perro muerto",
             "para ver los motivos de su muerte",
             "estoy registrado te paso mis datos para programar la recogida de meustras"],
            checks_t,
        ))
        # U — ERR-045: pedir un perfil por CATEGORÍA ('pre quirúrgico') ofrece los
        #     perfiles ARMADOS de esa categoría (no la lista genérica por especie) y la
        #     orden cierra con el perfil elegido, su código y su precio real.
        def checks_u(replies):
            out = []
            menu = (replies[12] or "")
            menu_norm = _norm(menu)
            # _norm elimina caracteres acentuados ('prequirúrgico' -> 'prequirrgico').
            if "701" not in menu or "prequir" not in menu_norm:
                out.append(f"no ofreció los perfiles prequirúrgicos armados: '{menu[:90]}'")
            if "401" in menu or "402" in menu:
                out.append(f"cayó a la lista genérica por especie: '{menu[:90]}'")
            if len(_state["requests"]) != 1:
                out.append(f"esperaba 1 orden creada, hay {len(_state['requests'])}")
                return out
            f = _state["requests"][-1].get("captured_fields") or {}
            if str(f.get("_selected_profile_code")) != "701":
                out.append(f"el perfil elegido no quedó con código: {f.get('_selected_profile_code')!r}")
            if int(f.get("_selected_profile_price") or 0) != 24000:
                out.append(f"el perfil cerró sin precio real: {f.get('_selected_profile_price')!r}")
            return out

        results.append(_run_conversation(
            "U. Perfil por categoría (prequirúrgico) → perfiles armados", "val-u",
            ["Hola", "1", "nit 900123456", "sí, esa dirección está bien",
             "Dra. Laura Méndez", "Anahí", "canino", "pitbull", "hembra",
             "2 años", "Luciano", "sin observaciones",
             "cuál me recomiendas pre quirúrgico? qué perfil tienen?",
             "el 1", "no, seguimos con el pago", "contraentrega", "sí, confirmo"],
            checks_u,
        ))
        # V — ERR-046: con la confirmación de dirección PENDIENTE, el cliente responde
        #     otra cosa ("quiero un análisis de orina"). El dato se conserva pero la
        #     dirección se RE-PREGUNTA (no se asume); al confirmarla, el flujo retoma
        #     el menú del área y la selección funciona.
        def checks_v(replies):
            out = []
            reask = replies[4] or ""
            if "45" not in reask or "direcci" not in reask.lower():
                out.append(f"no re-preguntó la dirección pendiente: '{reask[:90]}'")
            if "médico" in reask.lower():
                out.append(f"avanzó al médico sin confirmar la dirección: '{reask[:90]}'")
            # El pedido del cliente no se pierde: la misma respuesta atiende el análisis
            # (menú de área, sugerencia o registro) antes de re-preguntar la dirección.
            if not any(k in _norm(reask) for k in ("orina", "uroanalisis", "renal", "prueba", "analisis")):
                out.append(f"la re-pregunta ignoró el pedido del cliente: '{reask[:90]}'")
            f = _state["session"]["captured_fields"]
            if not f.get("_address_confirmed"):
                out.append("la dirección no quedó confirmada tras el sí explícito")
            return out

        results.append(_run_conversation(
            "V. Dirección pendiente + respuesta esquiva → re-pregunta", "val-v",
            ["Hola", "1", "Somos la Veterinaria San Roque", "sí, esa está bien",
             "quiero un análisis de orina", "sí, esa dirección está bien"],
            checks_v,
        ))
        # W — ERR-048: la frase real de la prueba fallida ("Tienes perfiles pre
        #     quirúrgico?", categoría con ESPACIO que la etiqueta diagnóstica no matchea)
        #     debe ofrecer los perfiles armados de la categoría, sin caer al menú
        #     genérico por especie ni ser pisada por la plantilla del dato faltante.
        def checks_w(replies):
            out = []
            menu = replies[12] or ""
            if "701" not in menu or "prequir" not in _norm(menu):
                out.append(f"no ofreció los perfiles prequirúrgicos: '{menu[:90]}'")
            if "lo anoto" in menu.lower():
                out.append(f"la plantilla del dato faltante pisó el menú: '{menu[:90]}'")
            if len(_state["requests"]) != 1:
                out.append(f"esperaba 1 orden creada, hay {len(_state['requests'])}")
                return out
            f = _state["requests"][-1].get("captured_fields") or {}
            if str(f.get("_selected_profile_code")) != "701":
                out.append(f"el perfil elegido no quedó con código: {f.get('_selected_profile_code')!r}")
            return out

        results.append(_run_conversation(
            "W. 'Tienes perfiles pre quirúrgico?' → perfiles armados", "val-w",
            ["Hola", "1", "nit 900123456", "sí, esa dirección está bien",
             "Dra. Laura Méndez", "Pepe", "canino", "pitbull", "macho",
             "2 años", "Gaston", "sin observaciones",
             "Tienes perfiles pre quirúrgico?",
             "el 1", "no, seguimos con el pago", "contraentrega", "sí, confirmo"],
            checks_w,
        ))
        # X — ERR-050 (chat 4 real, 2026-07-04): agregar un análisis a un perfil ya
        #     elegido. "agregarle un análisis más" NO ofrece perfiles nuevos; "un análisis
        #     de orina" muestra el menú del ÁREA (no fuzzy-match a un test suelto); la
        #     selección suma ESTRUCTURADA a selected_tests y el resumen trae el total
        #     ajustado ($24.000 + $52.000 = $76.000), no solo el perfil base.
        def checks_x(replies):
            out = []
            ask_which = replies[14] or ""
            if "recomendar" in ask_which.lower() or "401" in ask_which or "402" in ask_which:
                out.append(f"'agregarle un análisis más' ofreció perfiles nuevos: '{ask_which[:90]}'")
            if "agregar" not in ask_which.lower():
                out.append(f"no preguntó cuál análisis agregar: '{ask_which[:90]}'")
            # El agregado se valida contra el catálogo REAL: el menú de orina ofrece
            # Uroanálisis (1601 Parcial de Orina …), no el "urocultivo" del mock viejo.
            esperado = URO_TESTS[0] if URO_TESTS else {"code": "1601", "name": "Parcial de Orina", "price": 16000}
            base, agregado = 24000, int(esperado.get("price") or 0)
            total = f"${base + agregado:,} COP"
            clave = _norm(esperado["name"].split("(")[0])
            area_menu = replies[15] or ""
            if esperado["code"] not in area_menu and clave not in _norm(area_menu):
                out.append(f"'un análisis de orina' no desplegó el menú del área: '{area_menu[:90]}'")
            added = replies[16] or ""
            if esperado["code"] not in added and clave not in _norm(added):
                out.append(f"la selección del menú no agregó {esperado['name']}: '{added[:90]}'")
            summary = replies[17] or ""
            if total not in summary:
                out.append(f"el resumen no trae el total ajustado ({total}): '{summary[:120]}'")
            if clave not in _norm(summary):
                out.append(f"el resumen no lista el agregado: '{summary[:120]}'")
            if len(_state["requests"]) != 1:
                out.append(f"esperaba 1 orden creada, hay {len(_state['requests'])}")
                return out
            f = _state["requests"][-1].get("captured_fields") or {}
            if str(f.get("_selected_profile_code")) != "701":
                out.append(f"perfil base perdido: {f.get('_selected_profile_code')!r}")
            sel = [str(t) for t in (f.get("selected_tests") or [])]
            if esperado["code"] not in "".join(sel):
                out.append(f"el agregado no quedó ESTRUCTURADO en selected_tests: {sel}")
            if f.get("exam_type") != "Perfil Prequirúrgico I":
                out.append(f"exam_type no es el nombre limpio del perfil: {f.get('exam_type')!r}")
            return out

        results.append(_run_conversation(
            "X. Perfil elegido + agregar análisis (ERR-050)", "val-x",
            ["Hola", "1", "nit 900123456", "sí, esa dirección está bien",
             "Dra. Laura Méndez", "Anahi", "canino", "pitbull", "hembra",
             "7 años", "Gaston", "sin observaciones",
             "Tienes perfiles pre quirúrgico?",
             "el 1",
             "quiero agregarle un analisis mas a este perfil",
             "quiero agregarle un analisis de orina al perfil",
             "el parcial de orina está bien",
             "contraentrega", "sí, confirmo"],
            checks_x,
        ))

        # Y — La raza inequívoca aporta la especie: el bot NO debe preguntarla
        def checks_y(replies):
            out = []
            # La especie se pregunta ANTES que la raza: esa pregunta es legítima. Lo que no
            # debe pasar es que la vuelva a preguntar una vez que la raza ya la aportó.
            for r in [x for x in replies[7:] if x]:
                low = r.lower()
                if "especie" in low or "canino, felino" in low or "¿es canino" in low:
                    out.append(f"re-preguntó la especie teniendo la raza: '{r[:80]}'")
            if not _state["requests"]:
                out.append("no se creó la orden")
            else:
                captured = _state["requests"][-1]["captured_fields"]
                if captured.get("species") != "Canino":
                    out.append(f"species esperada 'Canino', quedó '{captured.get('species')}'")
                if captured.get("breed") != "Pastor Alemán":
                    out.append(f"breed esperada 'Pastor Alemán', quedó '{captured.get('breed')}'")
            return out

        results.append(_run_conversation(
            "Y. Raza inequívoca infiere la especie", "val-y",
            ["Hola", "1", "nit 900123456", "sí, esa dirección está bien",
             "Dra. Laura Méndez", "Rocky", "pastor aleman", "macho",
             "4 años", "Pedro Gómez", "sin observaciones", "hemograma",
             "contraentrega", "sí, confirmo", "sí, confirmo"],
            checks_y,
        ))

        # Z — Raza ambigua (Mestizo): NO debe inferir especie, tiene que preguntarla
        def checks_z(replies):
            out = []
            asked = any("especie" in (r or "").lower() or "canino" in (r or "").lower()
                        for r in replies)
            if not asked:
                out.append("no preguntó la especie con una raza ambigua ('mestizo')")
            if _state["requests"]:
                captured = _state["requests"][-1]["captured_fields"]
                if not captured.get("species"):
                    out.append("la orden quedó sin especie")
            return out

        results.append(_run_conversation(
            "Z. Raza ambigua sigue preguntando la especie", "val-z",
            ["Hola", "1", "nit 900123456", "sí, esa dirección está bien",
             "Dra. Laura Méndez", "Luna", "mestizo", "felino", "hembra",
             "2 años", "Ana Ruiz", "sin observaciones", "hemograma",
             "contraentrega", "sí, confirmo", "sí, confirmo"],
            checks_z,
        ))

        # ── QA adversarial de razas/especies (catálogo real) ──────────────────────
        def _order():
            return _state["requests"][-1]["captured_fields"] if _state["requests"] else {}

        # QA1 — Cadena de correcciones donde la ÚLTIMA raza cambia la especie inferida.
        # Riesgo: que quede la especie de una raza corregida (Canino de "mestizo") con la
        # raza nueva (Holstein, bovina), o que se pierda la corrección.
        def checks_qa1(replies):
            out = []
            captured = _order()
            if not captured:
                out.append("no se creó la orden")
                return out
            breed = (captured.get("breed") or "").lower()
            species = captured.get("species")
            if "holstein" not in breed:
                out.append(f"la última corrección de raza se perdió: breed='{captured.get('breed')}'")
            if species and species != "Bovino":
                out.append(f"raza Holstein con especie '{species}': incoherente")
            return out

        results.append(_run_conversation(
            "QA1. Correcciones encadenadas de raza (cambia la especie)", "qa-1",
            ["Hola", "1", "nit 900123456", "sí, esa dirección está bien",
             "Dra. Laura Méndez", "Toro", "mestizo", "no perdón, es criollo",
             "me equivoqué, es un Holstein", "macho", "5 años", "Pedro Gómez",
             "sin observaciones", "hemograma", "contraentrega", "sí, confirmo", "sí, confirmo"],
            checks_qa1,
        ))

        # QA2 — Al pedir la RAZA el cliente responde una palabra de ESPECIE ("conejo").
        # Riesgo: que se registre "Conejo" como raza y quede sin especie, o que entre en bucle.
        def checks_qa2(replies):
            out = []
            captured = _order()
            if not captured:
                out.append("no se creó la orden")
                return out
            if not captured.get("species"):
                out.append("la orden quedó sin especie")
            if (captured.get("species") or "").lower() not in ("conejo", "lagomorfo"):
                out.append(f"esperaba especie Conejo, quedó '{captured.get('species')}'")
            return out

        results.append(_run_conversation(
            "QA2. Palabra de especie como respuesta a la raza", "qa-2",
            ["Hola", "1", "nit 900123456", "sí, esa dirección está bien",
             "Dra. Laura Méndez", "Pelusa", "conejo", "holland lop", "hembra",
             "1 año", "Ana Ruiz", "sin observaciones", "hemograma",
             "contraentrega", "sí, confirmo", "sí, confirmo"],
            checks_qa2,
        ))

        # QA3 — Especies exóticas nuevas (axolote, erizo, sugar glider) que antes no existían.
        def checks_qa3(replies):
            out = []
            captured = _order()
            if not captured:
                out.append("no se creó la orden")
                return out
            if not captured.get("species"):
                out.append("la orden quedó sin especie")
            for reply in [r for r in replies if r]:
                if "no atendemos" in reply.lower() or "no trabajamos" in reply.lower():
                    out.append(f"rechazó una especie que A3 sí atiende: '{reply[:70]}'")
            return out

        results.append(_run_conversation(
            "QA3. Especie exótica nueva (axolote)", "qa-3",
            ["Hola", "1", "nit 900123456", "sí, esa dirección está bien",
             "Dra. Laura Méndez", "Nemo", "es un axolote", "no sé la raza", "macho",
             "2 años", "Ana Ruiz", "sin observaciones", "hemograma",
             "contraentrega", "sí, confirmo", "sí, confirmo"],
            checks_qa3,
        ))

        # QA4 — Especie declarada y raza de OTRA especie. El catálogo no debe pisar
        # lo que el cliente dijo explícitamente.
        def checks_qa4(replies):
            out = []
            captured = _order()
            if not captured:
                out.append("no se creó la orden")
                return out
            if captured.get("species") != "Felino":
                out.append(f"pisó la especie que dio el cliente: quedó '{captured.get('species')}'")
            return out

        results.append(_run_conversation(
            "QA4. Especie declarada + raza de otra especie", "qa-4",
            ["Hola", "1", "nit 900123456", "sí, esa dirección está bien",
             "Dra. Laura Méndez", "Michi", "felino", "holstein", "hembra",
             "3 años", "Ana Ruiz", "sin observaciones", "hemograma",
             "contraentrega", "sí, confirmo", "sí, confirmo"],
            checks_qa4,
        ))

        # QA5 — Typos severos encadenados. 'doverman' debe recuperarse; 'chiwawa' no llega
        # al umbral y queda como texto libre: lo que NO puede pasar es que se pierda el dato.
        def checks_qa5(replies):
            out = []
            captured = _order()
            if not captured:
                out.append("no se creó la orden")
                return out
            if not captured.get("breed"):
                out.append("se perdió la raza")
            if not captured.get("species"):
                out.append("la orden quedó sin especie")
            return out

        results.append(_run_conversation(
            "QA5. Typos severos en la raza", "qa-5",
            ["Hola", "1", "nit 900123456", "sí, esa dirección está bien",
             "Dra. Laura Méndez", "Rocky", "es un doverman", "macho",
             "4 años", "Pedro Gómez", "sin observaciones", "hemograma",
             "contraentrega", "sí, confirmo", "sí, confirmo"],
            checks_qa5,
        ))

        # QA6 — Todo el paciente en un solo mensaje, con la raza aportando la especie.
        def checks_qa6(replies):
            out = []
            captured = _order()
            if not captured:
                out.append("no se creó la orden")
                return out
            for field in ("patient_name", "breed", "sex", "patient_age", "owner_name"):
                if not captured.get(field):
                    out.append(f"perdió {field} del mensaje en bloque")
            if captured.get("species") != "Canino":
                out.append(f"no infirió Canino del pastor alemán: '{captured.get('species')}'")
            return out

        results.append(_run_conversation(
            "QA6. Paciente completo en un mensaje", "qa-6",
            ["Hola", "1", "nit 900123456", "sí, esa dirección está bien",
             "Dra. Laura Méndez",
             "el paciente es Rocky, un pastor alemán macho de 4 años, del señor Pedro Gómez",
             "sin observaciones", "hemograma", "contraentrega", "sí, confirmo", "sí, confirmo"],
            checks_qa6,
        ))

        # QA7 — R29: al confirmar, el bot debe nombrar la especie CANÓNICA, no la palabra
        # del cliente ("cabra" → "anoto Caprino", no "anoto Cabra"). Reporte real del usuario.
        def checks_qa7(replies):
            out = []
            confirm = " ".join(r for r in replies if r).lower()
            if "cabra como especie" in confirm:
                out.append("confirmó con la palabra del cliente ('Cabra') en vez de 'Caprino'")
            if "caprino" not in confirm:
                out.append("nunca nombró la especie canónica 'Caprino' en la conversación")
            captured = _state["requests"][-1]["captured_fields"] if _state["requests"] else {}
            if captured and captured.get("species") != "Caprino":
                out.append(f"species esperada 'Caprino', quedó '{captured.get('species')}'")
            if captured and captured.get("sex") != "Hembra":
                out.append(f"sex esperado 'Hembra', quedó '{captured.get('sex')}'")
            return out

        results.append(_run_conversation(
            "QA7. Especie normalizada se confirma con el nombre canónico", "qa-7",
            ["Hola", "1", "nit 900123456", "sí, esa dirección está bien",
             "Dra. Laura Méndez", "Pepe", "es una cabra", "ni tiene raza",
             "3 años", "Ana Ruiz", "sin observaciones", "hemograma",
             "contraentrega", "sí, confirmo", "sí, confirmo"],
            checks_qa7,
        ))

        # QA8 — reproduce la conversación REAL del QA del usuario (chat 1, 07-21 14:05):
        # cuatro datos en un mensaje y luego VARIOS análisis juntos. Lo que se vio: el bot
        # respondió "Listo, lo anoto" sin nombrar qué análisis registró ni su precio.
        def checks_qa8(replies):
            out = []
            captured = _state["requests"][-1]["captured_fields"] if _state["requests"] else {}
            if not captured:
                out.append("no se creó la orden")
                return out
            esperado = {"requesting_doctor": "Jorge", "owner_name": "Pepito",
                        "patient_name": "Luisa", "species": "Caprino"}
            for field, valor in esperado.items():
                real = str(captured.get(field) or "")
                if valor.lower() not in real.lower():
                    out.append(f"{field}: esperaba '{valor}', quedó '{real}'")
            # ERR-076. Pidió TRES cosas: perfil prequirúrgico + sodio + potasio.
            exam = str(captured.get("exam_type") or "")
            tests = captured.get("selected_tests") or []
            blob = (exam + " " + " ".join(str(x) for x in tests)).lower()
            print(f"      [exam_type={exam!r} selected_tests={tests}]")
            hablado = " ".join(r for r in replies if r).lower()
            # `selected_tests` guarda CÓDIGOS: se traducen contra el catálogo REAL (ALL_TESTS).
            for code in tests:
                for row in ALL_TESTS:
                    if str(row.get("code")) == str(code):
                        blob += " " + str(row.get("name", "")).lower()
            for pedido in ("prequir", "sodio", "potasio"):
                if pedido in blob:
                    continue
                # (b) INVARIANTE DURO: si algo pedido no quedó en la orden, el bot TENÍA que
                # haberlo ofrecido. Perderlo en silencio es el bug de dinero.
                if pedido not in hablado:
                    out.append(f"se PERDIO en silencio: '{pedido}' ni en la orden ni ofrecido")
                else:
                    out.append(f"(aviso) '{pedido}' se ofreció pero no quedó en la orden")
            return out

        results.append(_run_conversation(
            "QA8. Cuatro datos en un mensaje + varios análisis juntos (QA real)", "qa-8",
            ["Hola", "1", "nit 900123456", "sí, esa dirección está bien",
             "El nombre de del médico es Jorge, el dueño del paciente se llama Pepito y es una cabra que se llama a Luisa",
             "No tiene razón o desconozco, la encontré en la calle papi",
             "Creo que tiene tres años",
             "Sí, quiero dejar una observación que es medio urgente es para caridad",
             "Sí, mira, necesitamos un pre quirúrgico, un análisis de sodio y uno de potasio",
             "el 1",  # elige el perfil que el bot ofrece: sin esto la orden NO debe cerrar
             "contraentrega", "sí, confirmo", "sí, confirmo"],
            checks_qa8,
        ))

        # QA9 — ERR-076 AISLADO. QA8 arranca con una frase real enredada ("es una cabra que se
        # llama a Luisa") que el modelo a veces no descompone; cuando falla, el flujo ni llega
        # al turno de los análisis y el resultado no dice nada del pedido mixto. Este flujo da
        # los datos de a uno para medir SOLO la regla del pedido mixto.
        def checks_qa9(replies):
            out = []
            captured = _state["requests"][-1]["captured_fields"] if _state["requests"] else {}
            if not captured:
                out.append("no se creó la orden")
                return out
            blob = str(captured.get("exam_type") or "").lower()
            for code in (captured.get("selected_tests") or []):
                for row in ALL_TESTS:
                    if str(row.get("code")) == str(code):
                        blob += " " + str(row.get("name", "")).lower()
            hablado = " ".join(r for r in replies if r).lower()
            for pedido in ("prequir", "sodio", "potasio"):
                if pedido in blob:
                    continue
                if pedido not in hablado:
                    out.append(f"se PERDIO en silencio: '{pedido}'")
                else:
                    out.append(f"'{pedido}' se ofreció pero no quedó en la orden")
            return out

        results.append(_run_conversation(
            "QA9. Pedido mixto aislado: perfil con opciones + análisis sueltos", "qa-9",
            ["Hola", "1", "nit 900123456", "sí, esa dirección está bien",
             "Dra. Laura Méndez", "Luisa", "canino", "criollo", "hembra",
             "3 años", "Pepito", "sin observaciones",
             "necesitamos un pre quirúrgico, un análisis de sodio y uno de potasio",
             "el 1",
             "contraentrega", "sí, confirmo", "sí, confirmo"],
            checks_qa9,
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
