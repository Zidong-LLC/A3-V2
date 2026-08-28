"""Enforcer de la consulta de RESULTADOS (Paso 3.4a).

El agente busca en los resultados publicados de la plataforma los del cliente que está
escribiendo y le manda el PDF por el mismo chat (decisión del usuario, 2026-08-28). Si no
sabe quién es, pide el nombre de la clínica o el NIT: sin cliente no se busca nada.

Si la búsqueda falla se cae al mensaje fijo de antes, para que un problema de base nunca
deje al cliente sin respuesta. Si el turno además dejó pendiente una recogida, se retoma
la ruta en el mismo turno."""
import logging
from app.flow import (
    base_route_response as _base_route_response,
    missing_route_field as _missing_route_field,
    missing_route_field_question as _missing_route_field_question,
)
from app.laterales import (
    _has_active_route_context,
    _operational_side_question_answer,
    _results_pending_response,
    _resume_route_after_lateral_turn,
)
from app.messages import RESULTS_NEED_CLIENT_MESSAGE, RESULTS_PENDING_MESSAGE
from app.results_lookup import build_response, order_number_in

logger = logging.getLogger(__name__)

# Clave interna: los ids de resultado que main.py tiene que mandar como PDF después
# de responder el texto. El envío no vive acá porque el enforcer no conoce el canal.
DELIVER_KEY = "_deliver_results"


def _results_answer(session: dict, fields: dict, user_message: str) -> tuple[str, list[str]]:
    """Texto de la respuesta y resultados a enviar. Nunca levanta: ante cualquier
    fallo devuelve el mensaje fijo de siempre."""
    client_id = session.get("client_id")
    if not client_id:
        return RESULTS_NEED_CLIENT_MESSAGE, []
    try:
        return build_response(
            client_id,
            patient=fields.get("patient_name"),
            order_number=order_number_in(user_message),
        )
    except Exception:
        logger.exception("Consulta de resultados por chat falló para %s", client_id)
        return RESULTS_PENDING_MESSAGE, []


def _enforce_results_message(session: dict, ai_response: dict, user_message: str) -> dict:
    """Si el turno se clasificó como consulta de resultados, busca el resultado del
    cliente y responde con él. Si junto con los resultados quedó pendiente programar
    una recogida, entrega la respuesta Y retoma la ruta en el mismo turno, para no
    perder la intención de recogida (resume determinístico)."""
    if ai_response.get("intent") != "results":
        return ai_response
    fields = ai_response.get("captured_fields") or {}
    pending = ai_response.get("pending_intents") or []

    operational_answer = _operational_side_question_answer(user_message)
    if operational_answer:
        response = _base_route_response(operational_answer, fields)
        response["message_mode"] = "side_question"
        return _resume_route_after_lateral_turn(session, response) if _has_active_route_context(session, fields) else response

    answer, deliver = _results_answer(session, fields, user_message)

    if "route_scheduling" in pending:
        missing = _missing_route_field(session, fields)
        question = _missing_route_field_question(missing) if missing else "¿Confirmas que programamos la recogida?"
        resumed = _base_route_response(
            f"{answer}\n\nMientras tanto, sigamos con la recogida que me pedías. {question}",
            fields,
        )
        resumed["message_mode"] = "side_question"
        resumed["captured_fields"]["_pending_intents"] = []
        if deliver:
            resumed["captured_fields"][DELIVER_KEY] = deliver
        return resumed

    response = _results_pending_response(fields, pending)
    response["reply"] = answer
    if deliver:
        response["captured_fields"][DELIVER_KEY] = deliver
    return response
