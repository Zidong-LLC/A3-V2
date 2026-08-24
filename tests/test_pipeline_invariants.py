"""Invariantes ESTRUCTURALES del pipeline — la red que impide que la clase vuelva.

Seis bugs (ERR-019 → 067 → 070 → 071 → 072 → 073 → 076) fueron el MISMO problema: un atajo
interno decide por listas de palabras y hace `return` ANTES de que el modelo lea el turno.
Cada arreglo previo fue ampliar una lista de tokens, y por eso ERR-072 fue una regresión: al
degradar un atajo, el mensaje cayó en el siguiente de la cadena.

Estos tests no prueban comportamiento: son lint estructural. Fallan cuando alguien vuelve a
introducir la causa raíz, con un mensaje que explica qué hacer en vez de eso.
"""
import ast
import re
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"
AGENT = APP / "agent.py"

# Medido el 2026-07-21. Es un umbral MONÓTONO DECRECIENTE: cada atajo que se convierta a
# handler post-modelo lo baja. Nadie puede subirlo sin dejar rastro en el mismo commit.
#
# 40 → 42 el 2026-07-28 (ERR-099, ficha en tasks/errores-soluciones.md). Los dos `return`
# nuevos redirigen la corrección del CLIENTE hacia _restart_identification_for_new_client.
# No convierten un turno visible en invisible: ambos viven dentro de bloques que ya
# retornaban pre-LLM en TODAS sus ramas (la corrección en fase terminal y la corrección en
# la confirmación), y usan el mismo patrón que _wants_to_change_client dos líneas más
# arriba. Lo que cambia es a dónde va el turno, no si el modelo lo ve.
#
# 42 → 43 el 2026-08-12 (ERR-088, ficha en tasks/errores-soluciones.md). El `return` nuevo
# NO vuelve invisible ningún turno: parte en dos el guard de `_blocked`, que ya retornaba
# pre-LLM sin excepción. Al contrario, deja pasar al modelo turnos que antes morían acá —
# los del cliente escalado que se re-identifica con un nombre que sí existe en la base.
# El guard tiene que ser pre-LLM porque decide si el turno se procesa, igual que el que
# reemplaza; convertirlo en handler post-modelo significaría llamar al modelo para todos
# los mensajes de una conversación que un humano ya tomó.
#
# 43 se mantiene tras la decisión 011 (jerarquía de pedidos). El cierre del pedido se
# resolvió como enforcer POST-modelo señal-primero (`_enforce_open_pedido_close`), no como
# atajo pre-LLM: el cliente puede decir que terminó de mil formas ("listo", "terminala", "ya
# está", "no va más") y ninguna lista de tokens las cubre — el modelo sí las entiende. Lo
# único pre-LLM es que el atajo de despedida CEDE cuando hay un pedido abierto, para que el
# turno llegue al modelo; eso no agrega returns.
# 44 (2026-08-15, ERR-118): cierre determinístico del pedido cuando el ESTADO no admite otra
# lectura — pedido abierto + orden registrada + forma de pago en el mensaje. Decide por
# estado; el único texto que lee es la red de pago ya probada (QA 7/7). Pasar por el modelo
# en ese estado rompía el cierre ("Contraentrega." → "¿Qué análisis o perfil desean?").
# 44 -> 35 el 2026-08-21 (Etapa 2 del refactor de comprensión, ficha ABIERTO-003): se
# degradaron a handlers post-modelo señal-primero (molde C1/C2/C3) los tres grupos que
# competían por los mensajes de corrección/cierre: el bloque de la reoferta de estables
# (_stable_confirm_pending, 5 returns), las correcciones en fase CONFIRMACIÓN (cambio de
# cliente + corrección de campo, 3 returns) y el call-site de la oferta de análisis extra
# (1 return). Ahora el MODELO lee esos turnos ("la dejamos así", "me equivoqué en algo",
# "si análisis quiero perfil 653") y los tokens quedan de red.
# 35 -> 24 el 2026-08-21 (Etapa 3): fase terminal y memoria. Se degradaron los carriles
# post-cierre (despedida, saludo, lateral, "quedamos atentos", negativa, reptiles), el
# smalltalk en ruta activa y los dos carriles de "el de siempre" (que además REVIVEN la
# señal same_as_previous, hasta hoy letra muerta del enum). "Otra orden" en terminal la
# absorbe C1 con su red ampliada (_wants_another_service_order).
# 24 -> 13 el 2026-08-24 (Etapa 4a): catálogo y laterales. Los seis carriles que competían
# por las preguntas de servicio/catálogo (info pre-identificación, precio real del
# catálogo, lateral operativa, muestrario/overview, recomendación de perfiles y etiqueta
# diagnóstica) se movieron JUNTOS a un handler post-modelo insertado ANTES de la frontera
# de orden (misma precedencia que tenían pre-LLM). Acciones canónicas y detectores
# idénticos; los gates leen entry_intent (pre-reset de B12). Quedan pre-LLM: los guards de
# estado (_blocked, ERR-088), la bienvenida, el cierre determinístico del pedido (ERR-118),
# la consulta del número de orden, el bloqueo de cliente final, las opciones del menú de
# bienvenida (2/4/reconsiderar — respuesta a un menú mostrado, como 18/19), "dije/dicho"
# con lista de coincidencias en pantalla, y las selecciones de menús por número/código:
# todos deciden por ESTADO + dato exacto, no por interpretación de la oración.
PRE_LLM_RETURNS_BASELINE = 13


def _process_turn_ast() -> tuple[ast.FunctionDef, int]:
    """Devuelve (nodo de process_turn, línea de la 1ª llamada a ai.generate_turn)."""
    tree = ast.parse(AGENT.read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "process_turn")
    call = min(n.lineno for n in ast.walk(fn)
               if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
               and n.func.attr == "generate_turn")
    return fn, call


def test_no_new_pre_llm_shortcuts():
    """EL invariante central: congela cuántos `return` corren antes de que hable el modelo."""
    fn, call_line = _process_turn_ast()
    returns = [n.lineno for n in ast.walk(fn) if isinstance(n, ast.Return) and n.lineno < call_line]
    assert len(returns) == PRE_LLM_RETURNS_BASELINE, (
        f"\n\nHay {len(returns)} `return` PRE-LLM en process_turn; el baseline es "
        f"{PRE_LLM_RETURNS_BASELINE}.\n"
        "Un `return` antes de `ai.generate_turn` significa que el modelo NUNCA ve ese turno: "
        "es la causa raíz de ERR-067/070/071/072/073/076.\n"
        "  • Si AGREGASTE uno: convertilo en handler POST-modelo señal-primero (molde C1/C2/C3 "
        "en app/agent.py, handlers de `user_intent_signal`), con los tokens de red.\n"
        "  • Si de verdad tiene que ser pre-LLM: bajá/subí este baseline en el MISMO commit y "
        "explicá el porqué en tasks/errores-soluciones.md.\n"
        "  • Si CONVERTISTE uno (¡gracias!): bajá el baseline a este número.\n"
    )


def test_pending_intents_is_not_destroyed_in_new_places():
    """`pending_intents` es el canal para 'dos intenciones en un mensaje'. Emitir `[]` a mano
    borra la segunda intención del cliente; solo se permite donde ya estaba."""
    allowed = {"agent.py", "flow.py"}
    offenders = []
    for path in APP.rglob("*.py"):
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r'["\']pending_intents["\']\s*:\s*\[\s*\]', line) and path.name not in allowed:
                offenders.append(f"{path.relative_to(APP)}:{i}")
    assert not offenders, (
        f"\n\nEstos sitios nuevos vacían `pending_intents`: {offenders}\n"
        "Cuando un atajo responde y emite `pending_intents: []`, destruye el registro de la "
        "segunda intención que el cliente expresó en el mismo mensaje.\n"
        "Propagá el valor previo en vez de vaciarlo.\n"
    )


def test_no_signal_of_the_enum_is_dead_code():
    """Una señal que el modelo emite y el código nunca lee es cobertura falsa: fue exactamente
    lo que dejó a `pending_intents` inerte (0 menciones en prompt.py)."""
    schema = (APP / "schema.py").read_text(encoding="utf-8")
    enum_block = re.search(r'"user_intent_signal".*?"enum"\s*:\s*\[(.*?)\]', schema, re.S)
    assert enum_block, "no se encontró el enum user_intent_signal en schema.py"
    signals = re.findall(r'"([a-z_]+)"', enum_block.group(1))
    assert len(signals) >= 10, f"se esperaban ~14 señales, se leyeron {len(signals)}"

    # Señales sin consumidor HOY. La lista solo puede ENCOGER: cada una que se cablee sale.
    #   - same_as_previous: hay `_is_same_as_previous` decidiendo por tokens en dos atajos pre-LLM.
    # (`cancel` SÍ se consume, en app/detectors/orden.py:137, como veto de confirmación.)
    # `farewell` salió de esta lista el 2026-08-12: la lee `_enforce_open_pedido_close` para
    # cerrar el pedido sin depender de que el cliente diga la palabra exacta.
    # provides_requested_data revivió el 2026-08-15: la lee el guardrail de coherencia
    # (_enforce_comprehension_recheck) para detectar "dice que dio el dato pero no capturó".
    # same_as_previous salió de esta lista el 2026-08-21 (Etapa 3b): la consume el
    # handler post-modelo de "el de siempre" con la resolución de snapshot/memoria.
    known_dead = set()
    code = "\n".join(p.read_text(encoding="utf-8") for p in APP.rglob("*.py")
                     if p.name not in ("schema.py", "prompt.py"))
    dead = {s for s in signals if f'"{s}"' not in code and f"'{s}'" not in code}
    nuevas = dead - known_dead
    assert not nuevas, (
        f"\n\nEstas señales del enum no las lee nadie: {sorted(nuevas)}\n"
        "Agregar una señal al schema que ningún código consulta da falsa sensación de "
        "cobertura: el modelo la emite y se descarta.\n"
        "Cableala en un handler, o sacala del schema.\n"
    )
    revividas = known_dead - dead
    assert not revividas, (
        f"\n\n¡Buena noticia! Estas señales ya tienen consumidor: {sorted(revividas)}.\n"
        "Sacalas de `known_dead` en este test para que no puedan volver a morir.\n"
    )


def test_an_order_never_closes_with_an_unresolved_request():
    """ERR-076 — invariante de DINERO: si el cliente pidió algo que quedó sin resolver, la
    orden no puede llegar a fase terminal. Vale más repreguntar que facturar de menos."""
    from app import agent

    fields = {
        "_client_found": True, "pickup_address": "Cra 15 #80-20", "requesting_doctor": "Dra Ana",
        "patient_name": "Pepe", "species": "Caprino", "breed": "Sin determinar", "sex": "Hembra",
        "patient_age": "3 años", "owner_name": "Juan", "observations": "ninguna",
        "exam_type": "Sodio, Potasio", "selected_tests": ["1404", "1405"],
        "payment_method": "contraentrega", "_pending_ambiguous_items": ["un pre quirúrgico"],
    }
    ai = {"intent": "route_scheduling", "phase": "fase_6_cierre",
          "reply": "Quedó registrado.", "captured_fields": fields}
    out = agent._prevent_incomplete_route_closure({"client_id": "c1"}, ai, fields)
    assert "quedó registrado" not in out["reply"].lower()
    assert out["phase"] != "fase_6_cierre"


def test_ningun_vocabulario_depende_de_tildes():
    """Etapa N del refactor de comprensión (2026-08-21): `tokenize` normaliza tildes, así
    que una entrada de vocabulario que SOLO exista acentuada ("sácalo" sin "sacalo") es
    código muerto — nunca matchea un token. La gente escribe sin tildes (ERR-142/143:
    "sácalo" y "déjalo así" no estaban en ninguna lista en su forma llana y el bot no
    entendió al cliente). Este lint exige el par llano de toda entrada acentuada."""
    import importlib

    acc = str.maketrans("áéíóúüñ", "aeiouun")
    modulos = [
        "app.detectors.basico", "app.detectors.cliente", "app.detectors.orden",
        "app.detectors.direccion", "app.detectors.perfil", "app.detectors.analisis",
        "app.catalog", "app.laterales", "app.menus", "app.orders", "app.flow",
        "app.species", "app.enforcers.orden", "app.enforcers.confirmacion",
        "app.enforcers.ayudas", "app.enforcers.flujo", "app.agent",
    ]
    huerfanas = []
    for modname in modulos:
        mod = importlib.import_module(modname)
        for name, val in vars(mod).items():
            if isinstance(val, (frozenset, set, tuple)) and val and all(
                    isinstance(x, str) for x in val):
                for entry in val:
                    llana = entry.translate(acc)
                    if llana != entry and llana not in val:
                        huerfanas.append(f"{modname}.{name}: {entry!r} (falta {llana!r})")
    assert not huerfanas, (
        "\n\nEstas entradas de vocabulario SOLO existen con tilde y ya no matchean nada "
        "(tokenize normaliza):\n  " + "\n  ".join(sorted(huerfanas)) +
        "\nAgregá el par sin tilde en el mismo set (o escribí la entrada directamente llana).\n"
    )
