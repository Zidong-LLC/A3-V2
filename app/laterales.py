"""Preguntas LATERALES del flujo (Paso 3.4a): dudas operativas del servicio, la respuesta
fija de resultados y el reenganche de la ruta tras un turno lateral/small talk.

Movidas TAL CUAL de agent.py (puro movimiento, sin cambio de lógica). Vive encima de
flow/menus/text y debajo de enforcers/agent: `_resume_route_after_lateral_turn` necesita
`menus._reply_asks_missing_field`, y menus ya importa de flow — por eso no puede vivir en
flow.py (ciclo)."""
from app.text import tokenize as _tokenize, strip_question_sentences as _strip_question_sentences
from app.flow import (
    ROUTE_REQUIRED_FIELDS as _ROUTE_REQUIRED_FIELDS,
    missing_route_field as _missing_route_field,
    missing_route_field_question as _missing_route_field_question,
)
from app.detectors import _ANALYSIS_TOKENS
from app.menus import _reply_asks_missing_field
from app.messages import RESULTS_PENDING_MESSAGE
from app.rules import TERMINAL_PHASES


_TIME_QUESTION_TOKENS = frozenset({
    "cuanto", "cuánto", "cuando", "cuándo", "tiempo", "tardan", "tarda",
    "demoran", "demora", "demorar", "promedio", "aproximado", "aproximadamente",
    "hora", "horas", "dia", "dias", "día", "días", "plazo", "urgente",
    "rapido", "rápido", "llega", "llegan", "llegaria", "llegaría", "pasan",
})
_RESULT_TOKENS = frozenset({"resultado", "resultados", "entrega", "entregan", "entregar"})
_ROUTE_TIMING_TOKENS = frozenset({
    "motorizado", "motorizados", "repartidor", "mensajero", "ruta", "recogida",
    "retiro", "retirar", "recoger", "pasan", "pasar", "llega", "llegaria", "llegaría",
})
# Marcadores de que el cliente PREGUNTA por el servicio de recogida (vs. ORDENA
# impacientemente "programen la recogida ya"). Sin esto, cualquier mención de
# "recogida/recoger" disparaba la respuesta operativa fija y metía bucle.
_SERVICE_QUESTION_MARKERS = frozenset({
    "hacen", "atienden", "recogen", "retiran", "pueden", "puede", "tienen",
    "ofrecen", "como", "cómo", "cual", "cuál", "sirve", "sirven", "trabajan",
    "manejan", "cubren", "donde", "dónde", "ustedes", "hay",
})
# Verbos imperativos: el cliente PIDE que se programe, no pregunta por el servicio.
_SCHEDULING_IMPERATIVE_TOKENS = frozenset({
    "programen", "programa", "programen", "agenden", "agende", "agenda",
    "coordinen", "coordina", "manden", "manda", "envien", "envíen", "envia",
    "envía", "recogela", "recógela", "ya", "hoy", "urgente", "rapido", "rápido",
})


def _is_service_question(text: str, tokens: set) -> bool:
    """¿El mensaje es una PREGUNTA sobre el servicio (no una orden impaciente)?"""
    has_imperative = bool(tokens & _SCHEDULING_IMPERATIVE_TOKENS)
    has_question = ("?" in text or "¿" in text or bool(tokens & _SERVICE_QUESTION_MARKERS))
    return has_question and not has_imperative


def _operational_side_question_answer(text: str) -> str | None:
    """Preguntas operativas de A3: responder sin inventar, antes de retomar el flujo."""
    tokens = set(_tokenize(text))
    if not tokens:
        return None

    asks_time = bool(tokens & _TIME_QUESTION_TOKENS)
    if asks_time and tokens & (_RESULT_TOKENS | _ANALYSIS_TOKENS):
        return (
            "Depende del análisis y de la muestra; para no darte un tiempo incorrecto, "
            "dime qué prueba necesitas y te oriento con el tiempo estimado."
        )
    if asks_time and tokens & _ROUTE_TIMING_TOKENS:
        return (
            "La hora exacta de recogida la confirma operaciones según la ruta y la disponibilidad "
            "del motorizado; si es urgente, lo dejamos marcado para priorizar la coordinación."
        )
    # Las preguntas de precio NO se deflectan acá con una frase genérica: el precio real lo
    # resuelve `_catalog_price_answer` (casos seguros) o el LLM, que recibe el catálogo con
    # precios y conoce los sinónimos (hemograma = Cuadro Hemático). Deflectar bloqueaba esa
    # respuesta y el cliente dejaba de ver el precio.
    if tokens & {"animal", "animales", "especie", "especies"} and tokens & {"cantidad", "cuantos", "cuántos", "cuales", "cuáles", "que", "qué", "hacen", "atienden"}:
        return (
            "Trabajamos principalmente con pacientes veterinarios como caninos y felinos; "
            "otras especies se revisan según el análisis y la muestra."
        )
    if tokens & {"retirar", "retiran", "recoger", "recogen", "recogida", "motorizado", "motorizados"}:
        # Solo si es una PREGUNTA por el servicio; si el cliente ORDENA que programen
        # ("recógela hoy", "programen la recogida ya"), no es duda operativa: dejar
        # que el flujo siga capturando/cerrando en vez de soltar la frase fija (bucle).
        if _is_service_question(text, tokens):
            return "Sí, recogemos muestras con motorizado asignado para clientes registrados en Bogotá."
        return None
    return None


def _has_active_route_context(session: dict, fields: dict) -> bool:
    return (
        session.get("intent_current") == "route_scheduling"
        or bool(session.get("client_id") or fields.get("_client_found"))
        or any(fields.get(k) for k in _ROUTE_REQUIRED_FIELDS)
    )


def _results_pending_response(fields: dict | None = None, pending_intents: list | None = None) -> dict:
    """Respuesta de la opción 2 (consultar resultados): informa que aún no está
    disponible por este medio y cierra el turno sin pedir datos. Si quedan
    intenciones pendientes (p. ej. una ruta), se preservan para retomarlas."""
    pending = pending_intents or []
    return {
        "reply": RESULTS_PENDING_MESSAGE,
        "phase": "fase_2_recogida_datos" if pending else "fase_6_cierre",
        "intent": "results",
        "service_area": "results",
        "requires_handoff": False,
        "handoff_area": None,
        "captured_fields": fields or {},
        "confidence": 1.0,
        "message_mode": "side_question",
        "pending_intents": pending,
        "resume_prompt": "",
    }


def _resume_route_after_lateral_turn(session: dict, ai_response: dict) -> dict:
    if ai_response.get("intent") != "route_scheduling" or ai_response.get("requires_handoff"):
        return ai_response
    if ai_response.get("phase") in TERMINAL_PHASES or ai_response.get("message_mode") == "cancellation":
        return ai_response
    if (
        ai_response.get("message_mode") not in {"side_question", "small_talk"}
        and ai_response.get("user_intent_signal") not in {"off_topic", "unclear"}
    ):
        return ai_response

    fields = ai_response.get("captured_fields") or {}
    missing = _missing_route_field(session, fields)
    if not missing:
        return ai_response

    reply = (ai_response.get("reply") or "").strip()
    if "?" in reply and _reply_asks_missing_field(reply, missing):
        return ai_response

    base = _strip_question_sentences(reply)
    question = _missing_route_field_question(missing)
    ai_response["reply"] = f"{base} {question}".strip() if base else question
    return ai_response
