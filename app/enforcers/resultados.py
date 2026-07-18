"""Enforcer de la consulta de RESULTADOS (Paso 3.4a — movido TAL CUAL de agent.py).

V1: los resultados no están disponibles por este medio; el mensaje es fijo. Si el turno
además dejó pendiente una recogida, se retoma la ruta en el mismo turno."""
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
from app.messages import RESULTS_PENDING_MESSAGE


def _enforce_results_message(session: dict, ai_response: dict, user_message: str) -> dict:
    """Si el turno se clasificó como consulta de resultados, responde con el
    mensaje fijo. Si junto con los resultados quedó pendiente programar una
    recogida, entrega el mensaje fijo Y retoma la ruta en el mismo turno, para
    no perder la intención de recogida (resume determinístico)."""
    if ai_response.get("intent") != "results":
        return ai_response
    fields = ai_response.get("captured_fields") or {}
    pending = ai_response.get("pending_intents") or []

    operational_answer = _operational_side_question_answer(user_message)
    if operational_answer:
        response = _base_route_response(operational_answer, fields)
        response["message_mode"] = "side_question"
        return _resume_route_after_lateral_turn(session, response) if _has_active_route_context(session, fields) else response

    if "route_scheduling" in pending:
        missing = _missing_route_field(session, fields)
        question = _missing_route_field_question(missing) if missing else "¿Confirmas que programamos la recogida?"
        resumed = _base_route_response(
            f"{RESULTS_PENDING_MESSAGE}\n\nMientras tanto, sigamos con la recogida que me pedías. {question}",
            fields,
        )
        resumed["message_mode"] = "side_question"
        resumed["captured_fields"]["_pending_intents"] = []
        return resumed

    return _results_pending_response(fields, pending)
