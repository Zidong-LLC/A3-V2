"""Enforcer del paso de CONFIRMACIÓN de la orden (Paso 3.4a — movido TAL CUAL de agent.py).

Muestra el resumen editable, maneja los ajustes de análisis durante la confirmación y
ejecuta el cierre determinístico cuando el cliente confirma con la orden completa."""
from app import state
from app.text import tokenize as _tokenize
from app.flow import (
    base_route_response as _base_route_response,
    missing_route_field as _missing_route_field,
    missing_route_field_question as _missing_route_field_question,
)
from app.detectors import (
    _confirms_order_now,
    _is_order_confirmation,
    _named_analysis_terms,
    _wants_partial_analysis_change,
)
from app.laterales import _operational_side_question_answer
from app.orders import (
    _add_tests_to_order,
    _area_options_for_profile_addition,
    _price_answer_for_order,
    _route_closure_summary,
    _route_confirmation_summary,
)
from app.messages import PAYMENT_ONLINE_HANDOFF_MESSAGE
from app.services import db

CONFIRMATION_PHASE = state.Phase.CONFIRMACION.value


def _confirmation_analysis_adjustment(session: dict, fields: dict, user_message: str, signal: str | None) -> dict | None:
    pending_action = fields.get("_awaiting_additional_test")
    if not pending_action and not _wants_partial_analysis_change(user_message):
        return None

    tokens = set(_tokenize(user_message))
    action = pending_action or "add"
    if tokens & {"quitar", "quita", "quitale", "quítale", "sacar", "saca", "sin", "menos", "retirar", "remover"}:
        action = "remove"

    # Al AGREGAR, la mención de un ÁREA ('agregale un análisis de orina') va al menú de
    # esa área ANTES que cualquier match difuso por nombre ('orina' → Cortisol; chat 4).
    if action == "add":
        area_response = _area_options_for_profile_addition(fields, user_message, require_question=False)
        if area_response:
            area_response["phase"] = CONFIRMATION_PHASE
            return area_response

    rows = (db.get_tests_by_codes_or_names([user_message])
            or db.get_tests_by_codes_or_names(_named_analysis_terms(user_message)))
    if not rows:
        if signal == "negate" or tokens & {"nada", "ninguno", "ninguna"}:
            return None
        # No nombró un test exacto: si pregunta por un ÁREA ('qué análisis de orina
        # tienen'), ofrecer las opciones de esa área para agregar, en vez de repreguntar
        # a ciegas y dejarlo trabado.
        area_response = _area_options_for_profile_addition(fields, user_message)
        if area_response:
            area_response["phase"] = CONFIRMATION_PHASE
            return area_response
        fields["_awaiting_additional_test"] = action
        ask = "¿Qué análisis quieres quitar?" if action == "remove" else "¿Qué análisis quieres agregar?"
        response = _base_route_response(f"Claro. {ask}", fields)
        response["phase"] = CONFIRMATION_PHASE
        return response

    _add_tests_to_order(fields, rows, action)
    fields.pop("_awaiting_additional_test", None)
    fields.pop("_correction_pending", None)

    summary = _route_confirmation_summary(fields)
    response = _base_route_response(summary or _missing_route_field_question(_missing_route_field(session, fields)), fields)
    response["phase"] = CONFIRMATION_PHASE
    return response


def _enforce_confirmation_step(session: dict, ai_response: dict, fields: dict, previous_phase: str, user_message: str) -> dict:
    """Antes de registrar una orden completa, mostrar el resumen y pedir
    confirmación (Sí / Corregir). Solo deja cerrar cuando el usuario ya confirmó."""
    if ai_response.get("intent") != "route_scheduling":
        return ai_response
    if ai_response.get("message_mode") == "cancellation":
        return ai_response

    if previous_phase == CONFIRMATION_PHASE:
        adjusted = _confirmation_analysis_adjustment(
            session, fields, user_message, ai_response.get("user_intent_signal")
        )
        if adjusted:
            return adjusted

    # Cierre DETERMINÍSTICO: si venimos del resumen (fase_4) y el usuario confirma
    # con la orden completa, cerrar SIEMPRE acá, sin depender de que el modelo emita
    # la fase terminal. Antes el cierre quedaba a criterio del AI y, si no devolvía
    # fase_6_cierre, la orden se quedaba trabada en la confirmación sin registrarse.
    if (previous_phase == CONFIRMATION_PHASE
            and _confirms_order_now(ai_response, user_message)
            and not _missing_route_field(session, fields)):
        operational_answer = _operational_side_question_answer(user_message)
        # Si confirmó y a la vez preguntó el precio, respondemos el valor REAL del análisis
        # ya elegido (no la respuesta genérica) antes del "Quedó registrado".
        price_answer = _price_answer_for_order(fields, user_message)
        if fields.get("payment_method") == "pago_linea":
            ai_response["phase"] = "fase_7_escalado"
            ai_response["requires_handoff"] = True
            ai_response["handoff_area"] = "contabilidad"
            ai_response["reply"] = PAYMENT_ONLINE_HANDOFF_MESSAGE
        else:
            ai_response["phase"] = "fase_6_cierre"
            ai_response["requires_handoff"] = False
            ai_response["handoff_area"] = None
            summary = _route_closure_summary(fields)
            if summary:
                ai_response["reply"] = summary
        prefix = price_answer or operational_answer
        if prefix:
            ai_response["reply"] = f"{prefix}\n\n{ai_response['reply']}"
        fields.pop("_correction_pending", None)
        ai_response["service_area"] = "route_scheduling"
        ai_response["message_mode"] = "flow_progress"
        return ai_response

    if _missing_route_field(session, fields):
        return ai_response
    # Ya estábamos en confirmación: el cierre lo maneja el bloque determinístico de
    # arriba y las correcciones su propio handler; cualquier otra respuesta la deja
    # pasar al modelo. No re-disparamos el resumen acá.
    if previous_phase == CONFIRMATION_PHASE:
        # Excepción: tras una corrección, cuando el dato nuevo llegó y la orden quedó
        # completa, re-mostrar el resumen para que el cliente vea el cambio antes del "sí".
        if fields.get("_correction_pending") and not _is_order_confirmation(user_message):
            fields.pop("_correction_pending", None)
            summary = _route_confirmation_summary(fields)
            if summary:
                ai_response["reply"] = summary
                ai_response["phase"] = CONFIRMATION_PHASE
                ai_response["requires_handoff"] = False
                ai_response["handoff_area"] = None
                ai_response["message_mode"] = "flow_progress"
                ai_response["captured_fields"] = fields
        return ai_response

    # Orden completa por primera vez: mostrar SIEMPRE el resumen determinístico, sin
    # depender de que el modelo haya devuelto una fase terminal. Antes, si el modelo
    # improvisaba la confirmación en fase_4 (no terminal), el sistema no tomaba control
    # y el bot daba vueltas con respuestas raras en vez de un resumen claro.
    summary = _route_confirmation_summary(fields)
    if not summary:
        return ai_response
    operational_answer = _operational_side_question_answer(user_message)
    if operational_answer:
        summary = f"{operational_answer}\n\n{summary}"
    ai_response["reply"] = summary
    ai_response["phase"] = CONFIRMATION_PHASE
    ai_response["requires_handoff"] = False
    ai_response["handoff_area"] = None
    ai_response["message_mode"] = "flow_progress"
    return ai_response
