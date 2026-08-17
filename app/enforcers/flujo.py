"""Enforcers del FLUJO de recogida (coherencia de campo, siguiente faltante, paso de pago)."""
import re

from app import catalog, state
from app.config import PEDIDOS_ENABLED

CONFIRMATION_PHASE = state.Phase.CONFIRMACION.value
from app.flow import (
    FIELD_LABELS as _FIELD_LABELS,
    ROUTE_REQUIRED_FIELDS as _ROUTE_REQUIRED_FIELDS,
    base_route_response as _base_route_response,
    missing_route_field as _missing_route_field,
    missing_route_field_question as _missing_route_field_question,
    route_ready_for_payment as _route_ready_for_payment,
    extra_analysis_offer as _extra_analysis_offer,
)
from app.detectors import _STABLE_ORDER_FIELDS, _detect_which_field_is_being_asked, _last_bot_message, _looks_off_topic_smalltalk, _wants_partial_analysis_change
from app.menus import _reply_asks_missing_field
from app.messages import PAYMENT_METHOD_QUESTION, EXTRA_ANALYSIS_OFFER

# Métodos de pago válidos (fuente: agent los definía; único uso real es este enforcer).
PAYMENT_METHODS = frozenset({"contraentrega", "pago_linea"})
from app.services import ai, db
from app.rules import TERMINAL_PHASES, calculate_custom_profile_total


_COHERENCE_GUARDED_FIELDS = frozenset({
    "requesting_doctor", "patient_name", "species", "breed", "sex", "patient_age", "owner_name",
})



def _enforce_field_coherence(
    session: dict, ai_response: dict, prev_fields: dict, user_message: str, history: list[dict]
) -> dict:
    """Red de seguridad: si el bot pidió un dato concreto del paciente y el usuario
    respondió con un saludo o small talk, no captura basura. Verifica con un modelo
    corto (solo cuando la respuesta huele a off-topic) y, si confirma que no responde,
    descarta lo capturado para ese campo y reencauza con calidez."""
    if ai_response.get("intent") != "route_scheduling" or ai_response.get("requires_handoff"):
        return ai_response
    if ai_response.get("message_mode") == "cancellation":
        return ai_response
    if ai_response.get("phase") in TERMINAL_PHASES or ai_response.get("phase") == CONFIRMATION_PHASE:
        return ai_response

    fields = ai_response.get("captured_fields", {})
    if not (session.get("client_id") or fields.get("_client_found")):
        return ai_response
    # No interferir con el armado/personalización de perfil ni la selección de análisis.
    if fields.get("selected_tests") is not None or fields.get("_profile_customizing"):
        return ai_response

    field = _detect_which_field_is_being_asked(history)
    if field not in _COHERENCE_GUARDED_FIELDS:
        return ai_response
    if not _looks_off_topic_smalltalk(user_message):
        return ai_response

    question = _last_bot_message(history) or _missing_route_field_question(field)
    interp = ai.interpret_route_field(question, user_message)
    if interp.get("action") == "save" and interp.get("value"):
        return ai_response

    # Incoherente: descartar lo que el modelo haya capturado para ese campo y reencauzar.
    fields[field] = prev_fields.get(field)
    reply = interp.get("reply") or _missing_route_field_question(field)
    response = _base_route_response(reply, fields)
    response["message_mode"] = "small_talk"
    return response



def _corrected_stable_fields(fields: dict, prev_fields: dict) -> list[str]:
    """Campos ESTABLES de la orden cuyo valor CAMBIÓ en este turno (había uno y ahora hay
    otro distinto): eso es una corrección del cliente, no progreso normal (ERR-069)."""
    return [f for f in _STABLE_ORDER_FIELDS
            if prev_fields.get(f) and fields.get(f) and fields.get(f) != prev_fields.get(f)]


def _correction_ack_text(corrected: list[str], fields: dict) -> str:
    parts = [f"{_FIELD_LABELS.get(f, f)}: {fields.get(f)}" for f in corrected]
    return f"Listo, corrijo {' y '.join(parts)}."


def _enforce_first_missing_after_progress(session: dict, ai_response: dict, prev_fields: dict) -> dict:
    # Contrato del turno RESUELTO (ERR-137): una respuesta final no se pisa con un empuje.
    # Cinturón redundante con el retorno temprano del pipeline — protege reordenamientos.
    if ai_response.get("turn_resolved"):
        return ai_response
    if ai_response.get("intent") != "route_scheduling" or ai_response.get("requires_handoff"):
        return ai_response
    if ai_response.get("phase") in TERMINAL_PHASES or ai_response.get("phase") == CONFIRMATION_PHASE:
        return ai_response

    fields = ai_response.get("captured_fields", {})
    if fields.get("_client_match_options") or fields.get("_client_not_found"):
        return ai_response
    # Oferta de agregar otro análisis activa (Parte B): no pisarla con la pregunta de pago.
    # PERO si el turno fue una CORRECCIÓN de un dato estable (el carril la cedió al modelo,
    # ERR-069), el acuse + la re-oferta se arman determinísticos: el cliente ve que su
    # cambio quedó tomado y el flujo retoma el paso donde estaba.
    if fields.get("_offering_extra_analysis"):
        corrected = _corrected_stable_fields(fields, prev_fields)
        if corrected and not (fields.get("_test_menu_options") or fields.get("_profile_menu_options")):
            ai_response["reply"] = f"{_correction_ack_text(corrected, fields)} {_extra_analysis_offer()}"
        return ai_response
    # Un menú recién ofrecido (análisis o perfiles) ES la pregunta del análisis: no
    # pisarlo con la plantilla del dato faltante (ERR-048: "Perfecto, lo anoto. ¿qué
    # análisis o perfil desean?" tapaba el menú de perfiles por categoría).
    if (fields.get("_test_menu_options") or fields.get("_profile_menu_options")
            or (fields.get("selected_tests") is not None and not fields.get("exam_type"))):
        return ai_response
    progressed = any(fields.get(f) and fields.get(f) != prev_fields.get(f) for f in _ROUTE_REQUIRED_FIELDS)
    if not progressed:
        return ai_response

    missing = _missing_route_field(session, fields)
    if not missing or _reply_asks_missing_field(ai_response.get("reply", ""), missing):
        return ai_response
    if missing == "pickup_address" and fields.get("_address_confirmation_pending"):
        return ai_response

    # Acuse explícito de una corrección (ERR-069: 'me confundí con la raza es un tobiano'
    # se guardaba bien pero el acuse genérico no lo decía — el cliente insistió 3 veces):
    # nombrar QUÉ se corrigió y a QUÉ valor, y recién ahí empujar el paso pendiente.
    corrected = _corrected_stable_fields(fields, prev_fields)
    ack = _correction_ack_text(corrected, fields) if corrected else "Perfecto, lo anoto."
    ai_response["reply"] = f"{ack} {_missing_route_field_question(missing)}"
    return ai_response



def _enforce_payment_step(session: dict, ai_response: dict, fields: dict, user_message: str = "") -> dict:
    if ai_response.get("intent") != "route_scheduling":
        return ai_response
    if fields.get("_profile_customizing"):
        return ai_response
    # Mientras está activa la oferta de agregar otro análisis (Parte B), no saltar al pago:
    # ese paso lo decide _handle_extra_analysis_answer cuando el cliente diga que sigue.
    if fields.get("_offering_extra_analysis"):
        return ai_response

    if not _route_ready_for_payment(session, fields):
        return ai_response

    # Con la jerarquía de pedidos (decisión 011) la forma de pago NO se pide al completar la
    # orden: es del PEDIDO y se pregunta una sola vez al cerrarlo, después de que el cliente
    # decida que no va a agregar más órdenes. Acá el paso simplemente cede y la orden avanza
    # a su confirmación sin pago.
    if PEDIDOS_ENABLED:
        return ai_response

    # LÓGICA DE RETROCESO (L50): el flujo no solo avanza — el cliente puede volver a un paso
    # anterior desde cualquier punto ("antes de cerrar quiero agregar otro análisis", "esperá,
    # el dueño es otro"). Si la IA leyó una corrección/cambio, el empuje del paso de pago CEDE
    # y se respeta la respuesta del modelo que atiende ese cambio. Fuente primaria: la señal;
    # el detector de tokens de abajo es la red para cuando el modelo no la marca.
    if not fields.get("payment_method") and ai_response.get("user_intent_signal") == "correction":
        return ai_response

    # Red de tokens: pide AGREGAR otro análisis sin nombrarlo → reabrir el paso de agregado.
    if not fields.get("payment_method") and _wants_partial_analysis_change(user_message):
        fields["_offering_extra_analysis"] = True
        fields["_awaiting_additional_test"] = "add"
        ai_response["reply"] = "Claro. ¿Qué análisis quieres agregar? Decime el nombre o el código."
        ai_response["phase"] = "fase_2_recogida_datos"
        ai_response["intent"] = "route_scheduling"
        ai_response["service_area"] = "route_scheduling"
        ai_response["requires_handoff"] = False
        ai_response["handoff_area"] = None
        ai_response["message_mode"] = "flow_progress"
        return ai_response

    payment_method = fields.get("payment_method")
    if payment_method in PAYMENT_METHODS:
        ai_response["service_area"] = "route_scheduling"
        if payment_method == "pago_linea":
            ai_response["requires_handoff"] = True
            ai_response["handoff_area"] = ai_response.get("handoff_area") or "contabilidad"
        elif payment_method == "contraentrega":
            ai_response["requires_handoff"] = False
            ai_response["handoff_area"] = None
        return ai_response

    # Un menú activo es una PREGUNTA ABIERTA al cliente (ej. las opciones de orina del
    # anclaje): el empuje del pago no la pisa — el pago se pregunta cuando el menú se
    # resuelva (misma lógica L50: ningún empuje de paso pisa lo pendiente). Los menús
    # pegados de turnos anteriores ya fueron descartados antes (ERR-060), así que lo que
    # queda acá es una pregunta legítima de ESTE turno.
    if fields.get("_test_menu_options") or fields.get("_profile_menu_options"):
        return ai_response
    ai_response["reply"] = PAYMENT_METHOD_QUESTION
    ai_response["phase"] = "fase_2_recogida_datos"
    ai_response["intent"] = "route_scheduling"
    ai_response["service_area"] = "route_scheduling"
    ai_response["requires_handoff"] = False
    ai_response["handoff_area"] = None
    ai_response["message_mode"] = "flow_progress"
    ai_response["pending_intents"] = ai_response.get("pending_intents", [])
    return ai_response

