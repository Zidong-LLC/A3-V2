import re
import time
import logging
import contextvars
from typing import Callable
from datetime import datetime

from app import billing, catalog, state
from app.text import (
    tokenize as _tokenize, as_text_items as _as_text_items, money as _money, catalog_item_key as _catalog_item_key,
    strip_price_text as _strip_price_text, ACCENT_TRANSLATION as _ACCENT_TRANSLATION,
    strip_question_sentences as _strip_question_sentences,
)
from app.laterales import (
    _operational_side_question_answer as _operational_side_question_answer,
    _has_active_route_context as _has_active_route_context,
    _results_pending_response as _results_pending_response,
    _resume_route_after_lateral_turn as _resume_route_after_lateral_turn,
    _is_service_question as _is_service_question,
)
from app.species import (
    ANIMAL_DOMAIN as _ANIMAL_DOMAIN, RECOVERABLE_SPECIES as _RECOVERABLE_SPECIES,
    IMPLIED_ANIMAL_FIELDS as _IMPLIED_ANIMAL_FIELDS, RECOVERABLE_SEX as _RECOVERABLE_SEX,
    apply_implied_animal_fields as _apply_implied_animal_fields,
)
from app.breeds import resolve_breed as _resolve_breed
from app.config import ALEGRA_ENABLED, APP_TIMEZONE, FSM_ENFORCE, PEDIDOS_ENABLED
from app.services import ai, db, alegra
from app.rules import TERMINAL_PHASES, calculate_custom_profile_total, calculate_profile_adjusted_total
from app.detectors import (
    _looks_off_topic_smalltalk,
    _is_order_number_query,
    _is_final_user_text,
    _asks_for_area_options,
    _followup_wants_new_analysis,
    _wants_another_service_order,
    _explicitly_wants_another_order,
    _reply_asks_for_route_field,
    _SOCIAL_PHRASES,
    _OFF_TOPIC_SMALL_TALK_TOKENS,
    _ORDER_QUERY_TOKENS,
    _ORDER_CREATE_TOKENS,
    _ORDER_NUMBER_TOKENS,
    _FINAL_USER_PHRASES,
    _AREA_OPTION_QUESTION_TOKENS,
    _ANALYSIS_TOKENS,
    _FOLLOWUP_NEW_TOKENS,
    _FOLLOWUP_CREATE_TOKENS,
    _FOLLOWUP_OBJECT_TOKENS,
    _PRICE_QUESTION_TOKENS,
    _TOTAL_QUESTION_TOKENS,
    _wants_partial_analysis_change,
    _removes_the_additions,
    _replaces_offered_analysis,
    _wants_new_order_strict,
    _wants_to_change_analysis,
    _looks_like_catalog_profile,
    _looks_like_specific_profile_query,
    _is_profile_detail_question,
    _is_generic_blood_analysis,
    _doesnt_know_what_to_ask,
    _split_multiple_exam_items,
    _profile_codes_from_text,
    _last_bot_message,
    _detect_which_field_is_being_asked,
    _wants_profile_recommendation,
    _named_analysis_terms,
    _wants_to_proceed_to_payment,
    _payment_method_from_text,
    _PARTIAL_KEEP_MARKERS,
    _ANALYSIS_ADD_REMOVE_TOKENS,
    _ANALYSIS_CHANGE_SIGNAL_TOKENS,
    _ANALYSIS_NOUN_TOKENS,
    _PROFILE_SPECIFIC_SUFFIXES,
    _PROFILE_DETAIL_TOKENS,
    _DOESNT_KNOW_PHRASES,
    _EXAM_ITEM_SEPARATOR,
    _RECOMMENDATION_TOKENS,
    _PRICE_STOPWORDS,
    _ACTION_STOPWORDS,
    _REMOVE_TOKENS,
    _PROCEED_TO_PAYMENT_TOKENS,
    _PROCEED_TO_PAYMENT_PHRASES,
    _SAME_AS_PREVIOUS_TOKENS,
    _SAME_AS_PHRASES,
    _is_same_as_previous,
    _wants_to_change_client,
    _wants_new_branch,
    _claims_unregistered_client,
    _asks_if_new_client,
    _is_no_identifier_text,
    _looks_like_bare_client_name,
    _asks_for_client_identity,
    _rejects_match_options,
    _BRANCH_NOUN_TOKENS,
    _CLIENT_CHANGE_SIGNAL_TOKENS,
    _CLIENT_NOUN_TOKENS,
    _BRANCH_NEW_SIGNAL_TOKENS,
    _NON_IDENTIFIER_TOKENS,
    _REJECT_ALL_MATCH_TOKENS,
    _FAREWELL_TOKENS, _CONTINUE_TOKENS, _GREETING_TOKENS, _AFFIRMATIVE_TOKENS, _NEGATIVE_TOKENS,
    _RESULTS_CHOICE_TOKENS, _OTHER_CHOICE_TOKENS,
    _PROFILE_CUSTOMIZE_TOKENS, _PROFILE_CONFIRM_TOKENS, _CLOSE_PROFILE_TOKENS,
    _CLOSE_PROFILE_PHRASES, _AMBIGUOUS_PROFILE_TOKENS, _ARMED_PROFILE_TOKENS,
    _ADDRESS_CONFIRM_TOKENS, _NO_OWNER_TOKENS, _NO_OWNER_PHRASES,
    _is_farewell, _is_greeting_only, _is_affirmative_text, _is_negative_text,
    _is_results_choice, _is_other_choice, _confirms_new_client, _explicitly_says_new_client,
    _is_profile_customization_request, _is_profile_confirmation, _wants_to_close_custom_profile,
    _is_ambiguous_profile_change, _asks_for_armed_profiles,
    _confirms_address, _rejects_address, _says_no_owner,
    _CORRECTION_TOKENS,
    _CONFIRM_ORDER_TOKENS,
    _ORDER_REQUEST_TOKENS,
    _OPTION_CORRECTION_TOKENS,
    _OPTION_WORDS,
    _RECONSIDER_HINT_TOKENS,
    _HANDOFF_ACCEPT_TOKENS,
    _is_order_confirmation,
    _is_bare_confirmation,
    _is_correction_request,
    _detect_correction_field,
    _expresses_order_request,
    _wants_to_reconsider_option,
    _accepts_handoff_offer,
    _confirms_order_now,
)
from app.flow import (
    AGE_UNIT_TOKENS as _AGE_UNIT_TOKENS,
    FIELD_LABELS as _flow_FIELD_LABELS,
    age_has_unit as _age_has_unit,
    ROUTE_ORDER_FIELDS_BEFORE_PAYMENT as _ROUTE_ORDER_FIELDS_BEFORE_PAYMENT,
    ROUTE_REQUIRED_FIELDS as _ROUTE_REQUIRED_FIELDS,
    base_route_response as _base_route_response,
    format_test_items as _format_test_items,
    estimated_total_text as _estimated_total_text,
    route_ready_for_payment as _route_ready_for_payment,
    missing_route_field as _missing_route_field,
    missing_route_field_question as _missing_route_field_question,
)
from app.menus import (
    _select_tests_from_menu as _select_tests_from_menu,
    _ORDINAL_SELECTIONS as _ORDINAL_SELECTIONS,
    _profile_menu_option_lines as _profile_menu_option_lines,
    _profile_description_items as _profile_description_items,
    _catalog_row_matches_item as _catalog_row_matches_item,
    _format_profile_recommendation as _format_profile_recommendation,
    _profile_detail_reply as _profile_detail_reply,
    _reply_asks_missing_field as _reply_asks_missing_field,
    _unknown_catalog_items as _unknown_catalog_items,
    _test_area_suggestion_reply as _test_area_suggestion_reply,
    _store_test_menu_options as _store_test_menu_options,
    _store_profile_menu_options as _store_profile_menu_options,
    _profile_lists_unchanged as _profile_lists_unchanged,
    _analysis_help_candidate as _analysis_help_candidate,
    _test_options_response as _test_options_response,
    _store_selected_profile_fields as _store_selected_profile_fields,
    _profile_customization_reply as _profile_customization_reply,
    _diagnostic_label_suggestion_reply as _diagnostic_label_suggestion_reply,
    _format_profile_options_with_details as _format_profile_options_with_details,
    _client_identity_prompt_count as _client_identity_prompt_count,
)
from app.enforcers.catalogo import (
    _enforce_client_identification_gate as _enforce_client_identification_gate,
    _enforce_custom_profile_close as _enforce_custom_profile_close,
    _enforce_generic_blood_analysis_help as _enforce_generic_blood_analysis_help,
    _enforce_selected_tests_grounding as _enforce_selected_tests_grounding,
    _enforce_test_category_help as _enforce_test_category_help,
)
from app.enforcers.ayudas import (
    _enforce_analysis_help_fallback as _enforce_analysis_help_fallback,
    _enforce_catalog_profile_help as _enforce_catalog_profile_help,
    _enforce_profile_detail_step as _enforce_profile_detail_step,
)
from app.enforcers.flujo import (
    _enforce_field_coherence as _enforce_field_coherence,
    _enforce_first_missing_after_progress as _enforce_first_missing_after_progress,
    _enforce_payment_step as _enforce_payment_step,
)
from app.orders import (
    _resolve_profile_base_if_missing as _resolve_profile_base_if_missing,
    _order_summary_lines as _order_summary_lines,
    _route_confirmation_summary as _route_confirmation_summary,
    _route_closure_summary as _route_closure_summary,
    _analysis_settled_response as _analysis_settled_response,
    _add_tests_to_order as _add_tests_to_order,
    _area_options_for_profile_addition as _area_options_for_profile_addition,
    _clear_field_for_correction as _clear_field_for_correction,
    _format_category_profile_menu as _format_category_profile_menu,
    _category_profiles_menu_response as _category_profiles_menu_response,
    _selected_profile_addition_response as _selected_profile_addition_response,
    _capture_profile_menu_selection as _capture_profile_menu_selection,
    _format_tests_total as _format_tests_total,
    _catalog_price_answer as _catalog_price_answer,
    _price_answer_for_order as _price_answer_for_order,
)
from app.enforcers.orden import (
    _handle_extra_analysis_answer as _handle_extra_analysis_answer,
    _enforce_extra_analysis_offer as _enforce_extra_analysis_offer,
    _enforce_multiple_tests_capture as _enforce_multiple_tests_capture,
    _enforce_loose_exam_catalog_resolution as _enforce_loose_exam_catalog_resolution,
    _enforce_profile_customization_changes as _enforce_profile_customization_changes,
    _enforce_profile_exam_type_integrity as _enforce_profile_exam_type_integrity,
    _enforce_profile_recommendation_help as _enforce_profile_recommendation_help,
    _enforce_diagnostic_label_help as _enforce_diagnostic_label_help,
    _enforce_catalog_profile_code_selection as _enforce_catalog_profile_code_selection,
    _ADD_ANALYSIS_TOKENS as _ADD_ANALYSIS_TOKENS,
)
from app.enforcers import enforce_selected_tests_are_catalog_codes as _enforce_selected_tests_are_catalog_codes
from app.enforcers.resultados import _enforce_results_message as _enforce_results_message
from app.enforcers.confirmacion import (
    _confirmation_analysis_adjustment as _confirmation_analysis_adjustment,
    _enforce_confirmation_step as _enforce_confirmation_step,
)
from app.enforcers.grounding import (
    enforce_exam_type_grounding as _enforce_exam_type_grounding,
    enforce_age_unit_grounding as _enforce_age_unit_grounding,
)
from app.messages import (
    CLIENT_LOOKUP_PROGRESS_MESSAGE, WELCOME_MESSAGE, FINAL_USER_MESSAGE,
    CLIENT_IDENTIFICATION_REQUIRED_MESSAGE, CLIENT_NOT_FOUND_MESSAGE,
    CLIENT_NEW_REGISTRATION_MESSAGE, CLIENT_SEARCH_FAILED_MESSAGE,
    CLIENT_RETRY_NOT_FOUND_MESSAGE, CLIENT_IDENTIFIER_RETRY_MESSAGE,
    POST_TERMINAL_GREETING_REPLY, RESULTS_PENDING_MESSAGE, OPTION_RECONSIDER_MESSAGE,
    ORDER_NUMBER_NEEDS_CLIENT_MESSAGE, ORDER_NUMBER_NOT_FOUND_MESSAGE, FAREWELL_REPLY,
    CLOSING_PROMPT, PEDIDO_CLOSING_PROMPT, PEDIDO_CLOSING_QUESTION, PAYMENT_METHOD_QUESTION, PAYMENT_ONLINE_HANDOFF_MESSAGE,
    EXTRA_ANALYSIS_OFFER, EXTRA_ANALYSIS_AMBIGUOUS_QUESTION,
    NO_COURIER_HANDOFF_MESSAGE, AGE_QUESTION, CORRECTION_PROMPT,
    ADVISOR_ASSIGNMENT_LINE,
)

logger = logging.getLogger(__name__)

# Fase de la conversación al ENTRAR al turno actual. Alcance de turno (thread-safe con
# ContextVar), lo setea process_turn al inicio y lo lee el observador de la FSM (3.2) para
# detectar transiciones de fase no previstas, sin drillear el dato por los ~20 return.
_turn_prev_phase: contextvars.ContextVar[str] = contextvars.ContextVar(
    "turn_prev_phase", default=""
)

# Mensajes de texto fijos → app/messages.py (importados arriba).

# _FAREWELL_TOKENS, _CONTINUE_TOKENS, _GREETING_TOKENS → app/detectors.py (importados arriba).

# Consulta del número de orden ya creada (no confundir con crear una orden nueva)
# Ronda A del troceo → detectors/analisis.py y menus.py (importados arriba).
def _order_number_reply(order: dict | None) -> str:
    if order and order.get("order_number"):
        exam = order.get("exam_type")
        detail = f" ({exam})" if exam else ""
        return (
            f"El número de tu orden más reciente es {order['order_number']}{detail}. "
            "Guárdalo para cualquier seguimiento."
        )
    return ORDER_NUMBER_NOT_FOUND_MESSAGE


def _append_order_number(reply: str, order_info) -> str:
    order_number = order_info.get("order_number") if isinstance(order_info, dict) else None
    if not order_number:
        return reply
    return f"{reply}\n\nNúmero de orden: {order_number}"


# Capa de respuesta del flujo → app/flow.py (importada arriba con alias).
def _titlecase_value(value: str | None) -> str | None:
    if not value or not isinstance(value, str):
        return value
    return " ".join(
        word.capitalize() if any(ch.isalpha() for ch in word) else word
        for word in value.split()
    )


def _normalize_name_fields(fields: dict) -> None:
    """Fuerza Mayúscula inicial en los campos de texto del paciente/cliente."""
    for field in _TITLECASE_FIELDS:
        if fields.get(field):
            fields[field] = _titlecase_value(fields[field])


# Frases de REFERENCIA a un dato anterior ("el que ya te dije", "el de siempre") que el
# modelo a veces captura LITERALES como si fueran el nombre (prueba real chat 4:
# requesting_doctor="El Que Ya Te Dije"; mismo patrón que ERR-030 con clinic_name).
_REFERENCE_VALUE_TOKENS = frozenset({"dije", "dijo", "dijeron", "mencione", "mencioné", "menciono"})
_REFERENCE_VALUE_EXACT = frozenset({
    "el mismo", "la misma", "el de siempre", "la de siempre", "el de antes",
    "la de antes", "el anterior", "la anterior", "el habitual", "la habitual",
})
_NAME_FIELDS_FOR_REFERENCE_CHECK = ("requesting_doctor", "patient_name", "owner_name", "clinic_name")


def _reject_reference_phrases_as_names(fields: dict, prev_fields: dict) -> None:
    """Descarta un valor NUEVO de campo de nombre que sea una frase-referencia capturada
    literal ('El Que Ya Te Dije' no es un médico): el campo vuelve a vacío y el pipeline
    re-pregunta con normalidad. Si el modelo interpretó bien (capturó 'Sr Juan' del
    historial), el valor pasa limpio."""
    for field in _NAME_FIELDS_FOR_REFERENCE_CHECK:
        value = fields.get(field)
        if not value or value == (prev_fields or {}).get(field):
            continue
        norm = " ".join(_tokenize(str(value)))
        if norm in _REFERENCE_VALUE_EXACT or set(norm.split()) & _REFERENCE_VALUE_TOKENS:
            fields[field] = None


# _is_farewell, _is_greeting_only → app/detectors.py (importados arriba).


# _AFFIRMATIVE_TOKENS, _NEGATIVE_TOKENS → app/detectors.py (importados arriba).

_HANDOFF_INTENTS = frozenset({"accounting", "new_client"})

PAYMENT_METHODS = frozenset({"contraentrega", "pago_linea"})
# PAYMENT_METHOD_QUESTION, PAYMENT_ONLINE_HANDOFF_MESSAGE, EXTRA_ANALYSIS_OFFER,
# CLOSING_PROMPT → app/messages.py (importados arriba).


# Detectores de análisis/perfil → app/detectors/analisis.py (importados arriba).
# NO_COURIER_HANDOFF_MESSAGE, AGE_QUESTION → app/messages.py (importados arriba).
# Campos de texto libre que se normalizan a Mayúscula inicial (Sección 11 del spec).
# No incluye exam_type (códigos/nombres de perfil) ni observations (texto libre).
_TITLECASE_FIELDS = ("clinic_name", "patient_name", "species", "breed", "owner_name", "requesting_doctor", "sex")

# Confirmación editable previa al registro (Sección 7.1 del spec).
CONFIRMATION_PHASE = state.Phase.CONFIRMACION.value  # "fase_4_confirmacion" (fuente: state.Phase)
# CORRECTION_PROMPT → app/messages.py (importado arriba).
# Vocabulario de confirmación/pedido/corrección → app/detectors.py (importados arriba).
# _is_same_as_previous y su vocabulario → app/detectors/orden.py (importados arriba).
# Señal de que un campo es lo que CAMBIA (no "el mismo"): "el mismo, solo CAMBIA el paciente".
_CHANGE_TOKENS = frozenset({
    "cambia", "cambiaba", "cambian", "cambiar", "cambie", "cambio", "cambió",
    "distinto", "distinta", "diferente", "otro", "otra", "menos", "excepto", "salvo",
})

_SAME_AS_FIELD_KEYWORDS = (
    (("médico", "medico", "doctor", "doctora", "solicitante"), "requesting_doctor"),
    # owner_name antes que patient_name: "el mismo propietario que el otro perro" debe
    # resolver al propietario, no al paciente. patient_name solo matchea "paciente".
    (("propietario", "dueño", "dueno", "dueña", "duena"), "owner_name"),
    (("paciente",), "patient_name"),
    (("examen", "análisis", "analisis", "perfil", "perfiles", "prueba"), "exam_type"),
    (("dirección", "direccion", "domicilio", "retiro", "recogida"), "pickup_address"),
    (("especie",), "species"),
    (("raza",), "breed"),
    (("sexo",), "sex"),
    (("edad",), "patient_age"),
    (("observación", "observacion", "observaciones"), "observations"),
    (("pago", "forma de pago"), "payment_method"),
)

_FIELD_LABELS = _flow_FIELD_LABELS  # fuente única en app/flow.py (ERR-069)

# Concordancia de género para armar frases con los labels ("la dirección de retiro es
# la misma", no "el dirección... es el mismo"). Default: masculino.
_FIELD_GRAMMAR = {
    "pickup_address": ("la", "la misma"),
    "payment_method": ("la", "la misma"),
    "species": ("la", "la misma"),
    "breed": ("la", "la misma"),
    "patient_age": ("la", "la misma"),
}

# _CORRECTION_FIELD_KEYWORDS y _detect_correction_field viven en detectors/orden.py (ERR-069).
MAX_CLIENT_MATCH_OPTIONS = 5
# Datos estables del cliente que el agente recuerda a largo plazo (entre órdenes
# y sesiones del mismo chat). NO incluye datos del paciente: esos cambian en cada
# orden y reutilizarlos arrastraría información de otro animal.
_CLIENT_MEMORY_FIELDS = ("pickup_address", "requesting_doctor", "payment_method")

_ORDER_RESET_FIELDS = frozenset({
    "exam_type", "patient_name", "species", "patient_age", "requesting_doctor",
    "owner_name", "breed", "sex", "observations", "payment_method", "selected_tests", "removed_tests",
    "_selected_profile_code", "_selected_profile_name", "_selected_profile_price",
    "_selected_profile_description", "_profile_detail_offered",
    "_profile_detail_confirmed", "_profile_customizing",
    "_profile_options_offered", "_diagnostic_label", "_prev_order_snapshot",
    "_test_menu_options", "_test_menu_adds_to_profile", "_awaiting_additional_test",
    "_offering_extra_analysis",
    # ERR-114 — el carril del pedido MIXTO. `_mixed_request_text` guarda el TEXTO del pedido
    # original de la orden ("un prequirúrgico, sodio y potasio") para re-escanearlo al fijar
    # el perfil (fix de ERR-076, correcto DENTRO de una orden). Fuera de esta lista, la marca
    # sobrevivía a la frontera entre órdenes y en la orden SIGUIENTE ese texto viejo se
    # re-escaneaba contra el catálogo: los análisis de la orden 1 renacían en la orden 2 y la
    # cuenta salía $24.000 de más. Fue LA vía de ERR-114 — no el modelo: un escritor
    # determinístico leyendo residuo de la orden anterior (diagnóstico instrumentado,
    # 2026-08-15). Sus dos hermanas del mismo carril se limpian por la misma razón.
    "_mixed_request_text", "_pending_ambiguous_items", "_pending_offer_count",
})

_IDENTIFICATION_RETRY_RESET_FIELDS = frozenset({
    "clinic_name", "tax_id", "pickup_address",
    "_client_found", "_client_not_found", "_client_display_name", "_client_address",
    "_handoff_announced", "_asked_if_new_client",
    "_address_confirmation_pending", "_address_confirmed",
    "_client_match_query", "_client_match_options",
    # Los favoritos son POR CLÍNICA: al cambiar de cliente hay que soltarlos o se le
    # ofrecerían a una veterinaria los perfiles de otra.
    "_client_favorite_profiles",
})

# _PROFILE_CUSTOMIZE_TOKENS, _PROFILE_CONFIRM_TOKENS, _CLOSE_PROFILE_TOKENS,
# _CLOSE_PROFILE_PHRASES, _AMBIGUOUS_PROFILE_TOKENS → app/detectors.py (importados arriba).

# _ORDINAL_SELECTIONS → app/menus.py; _strip_question_sentences → app/text.py (3.4a).
# Detectores de identificación de cliente → app/detectors/cliente.py (importados arriba).


def _default_handoff_reply(handoff_area: str | None) -> str:
    if handoff_area == "contabilidad":
        return f"Para este tema te derivamos a contabilidad. {ADVISOR_ASSIGNMENT_LINE}"
    if handoff_area == "operaciones":
        return f"Para este tema te derivamos a atención al cliente. {ADVISOR_ASSIGNMENT_LINE}"
    return ADVISOR_ASSIGNMENT_LINE


# Armadores de menús/replies → app/menus.py (importados arriba).
# _is_profile_customization_request, _is_profile_confirmation, _wants_to_close_custom_profile
# → app/detectors.py (importados arriba).


# _as_text_items → app.text.as_text_items (importado arriba).


def _normalize_phone(value: str | None) -> str:
    digits = re.sub(r"\D", "", value or "")
    if len(digits) > 10 and digits.startswith("57"):
        digits = digits[2:]
    return digits


def _extract_phone_candidate(text: str, allow_unlabeled: bool = False) -> str | None:
    labeled = re.search(
        r"(?i)\b(?:tel[eé]fono|telefono|celular|whatsapp|contacto|n[uú]mero)\b\D*(\+?\d[\d\s().-]{5,}\d)",
        text or "",
    )
    if labeled:
        digits = _normalize_phone(labeled.group(1))
        return digits if len(digits) >= 7 else None

    if not allow_unlabeled:
        return None

    for match in re.finditer(r"\+?\d[\d\s().-]{5,}\d", text or ""):
        digits = _normalize_phone(match.group(0))
        if 7 <= len(digits) <= 10:
            return digits
    return None


# _is_ambiguous_profile_change → app/detectors.py (importado arriba).


# Verbos de AGREGAR/QUITAR análisis: marcan un ajuste PARCIAL del perfil base (no
# empezar de cero). Distinto de "cambiar el análisis por otro" (cambio total).
# Marcadores de "mantener lo de antes, salvo un detalle" (incluye 'más' = agregar algo).
# _ARMED_PROFILE_TOKENS → app/detectors.py (importado arriba).


# _asks_for_armed_profiles → app/detectors.py (importado arriba).


# Armado/resumen de la orden → app/orders.py (importados arriba).
def _select_profiles_from_menu(text: str, options: list[dict]) -> list[dict]:
    """Resuelve TODOS los perfiles que el cliente eligió de la lista recomendada (número,
    ordinal, código o nombre), en el orden en que los dijo.

    ERR-077: el parser ya resolvía "1, 3 y 6" completo; era esta capa la que se quedaba
    con el primero y tiraba el resto sin avisar."""
    return _select_tests_from_menu(text, options)


def _select_profile_from_menu(text: str, options: list[dict]) -> dict | None:
    """Primer perfil elegido, para los call sites que fijan un único perfil base."""
    picks = _select_profiles_from_menu(text, options)
    return picks[0] if picks else None


# Enforcers del armado de la orden → app/enforcers/orden.py (importados arriba).
def _diagnostic_label_profile_turn(session: dict, fields: dict, user_message: str) -> dict | None:
    label = fields.get("_diagnostic_label")
    if not label or fields.get("exam_type"):
        return None

    if _wants_to_close_custom_profile(user_message):
        fields["exam_type"] = f"Perfil {str(label).title()} personalizado"
        fields["_profile_customizing"] = False
        missing = _missing_route_field(session, fields)
        reply = f"Perfecto, cierro el perfil {str(label).title()} así."
        if missing and missing != "exam_type":
            reply += f" {_missing_route_field_question(missing)}"
        return _base_route_response(reply, fields)

    # Pide perfiles ARMADOS (o una recomendación) mientras armaba a medida por etiqueta:
    # ofrecer los perfiles del catálogo de esa categoría, sin re-preguntar datos ya
    # capturados (ERR-045: re-preguntó la especie y después saltó al pago).
    if _asks_for_armed_profiles(user_message) or _wants_profile_recommendation(user_message):
        menu_response = _category_profiles_menu_response(fields, label)
        if menu_response:
            return menu_response

    if not _is_profile_customization_request(user_message):
        return None

    rows = db.get_tests_by_codes_or_names([user_message])
    if not rows:
        return _base_route_response(
            "No identifiqué ese análisis. Dime el nombre exacto o escribe 'cerramos así' para dejar el perfil.",
            fields,
        )

    selected = _as_text_items(fields.get("selected_tests"))
    removed = _as_text_items(fields.get("removed_tests"))
    target = removed if {"quitar", "quita", "sacar", "saca", "retirar", "remover"} & set(_tokenize(user_message)) else selected
    action = "quito" if target is removed else "agrego"
    for row in rows:
        code = str(row.get("code") or row.get("name"))
        if code not in target:
            target.append(code)
        if target is removed and code in selected:
            selected.remove(code)

    fields["selected_tests"] = selected
    fields["removed_tests"] = removed
    return _base_route_response(
        f"Listo, {action} {_format_test_items(rows)}. ¿Agregas o quitas otro análisis, o cerramos así?",
        fields,
    )


def _catalog_overview_choices(tests: list[dict]) -> list[dict]:
    if not tests:
        return []
    preferred = ("Hematología", "Química", "Uroanálisis", "Parasitología", "Coagulación")
    by_category = {str(t.get("category") or "").lower(): t for t in reversed(tests)}
    chosen = []
    used = set()
    for category in preferred:
        row = by_category.get(category.lower())
        if row and row.get("code") not in used:
            chosen.append(row)
            used.add(row.get("code"))
    for row in tests:
        if len(chosen) >= 6:
            break
        if row.get("code") not in used:
            chosen.append(row)
            used.add(row.get("code"))
    return chosen


def _test_catalog_overview_reply(tests: list[dict]) -> str:
    if not tests:
        return "Tenemos varias áreas de análisis. Dime qué necesitas evaluar y te ayudo a ubicar la prueba correcta."

    lines = ["Tenemos varias áreas de análisis. Algunas opciones del catálogo son:"]
    for idx, row in enumerate(tests, start=1):
        category = row.get("category") or ""
        lines.append(f"{idx}. {row.get('code')} {row.get('name')} ({category}) ({_money(row.get('price'))})")
    lines.append("Dime el número, el nombre o el área que necesitas revisar.")
    return "\n".join(lines)


def _is_catalog_overview_question(text: str | None) -> bool:
    tokens = set(_tokenize(text or ""))
    if not tokens:
        return False
    asks_catalog = bool(tokens & {"catalogo", "catálogo", "opciones", "tipos", "tipo", "hacen", "ofrecen", "puedo"})
    asks_analysis = bool(tokens & {"analisis", "análisis", "examen", "examenes", "exámenes", "prueba", "pruebas"})
    return asks_catalog and asks_analysis


# _MAGNITUDE_UNITS y _select_tests_from_menu -> app/menus.py (3.4a).


def _capture_test_menu_selection(session: dict, fields: dict, selected: list[dict]) -> dict:
    """Guarda los análisis elegidos del menú (con su código real) y avanza: pide el
    siguiente dato faltante o, si la orden está completa, muestra el resumen.

    REGLA GENERAL (ERR-076): elegir de un menú REEMPLAZA cuando el menú fue una elección
    desde cero, pero AGREGA cuando el menú se abrió como residuo de un pedido mixto —ahí ya
    hay análisis absorbidos de la MISMA frase del cliente y reemplazarlos los borraba. Vale
    para cualquier tipo de menú (área, categoría de perfiles, el que venga), no para una
    palabra puntual: la señal es de dónde vino el menú, no qué se pidió."""
    fields.pop("_test_menu_options", None)
    fields.pop("_test_menu_adds_to_profile", None)
    if fields.pop("_mixed_request_text", ""):
        _add_tests_to_order(fields, selected, "add")
        fields.pop("_pending_ambiguous_items", None)
        fields.pop("_pending_offer_count", None)
        return _analysis_settled_response(
            session, fields, f"Listo, agrego {_format_test_items(selected)}.")

    fields["selected_tests"] = [t["code"] for t in selected]
    fields["removed_tests"] = []
    if len(selected) == 1:
        fields["exam_type"] = f"{selected[0]['code']} {selected[0]['name']}"
    else:
        fields["exam_type"] = f"Perfil personalizado ({len(selected)} análisis)"
    # Reemplazo total: el perfil base anterior (si lo había) deja de aplicar; sin esto,
    # el resumen/total seguiría saliendo del perfil viejo y no de lo elegido acá.
    for key in ("_selected_profile_code", "_selected_profile_name", "_selected_profile_price",
                "_selected_profile_description", "_profile_detail_offered", "_profile_detail_confirmed"):
        fields.pop(key, None)

    # Mostrar el precio al lado de cada análisis (y el total si son varios), no solo el
    # nombre. Con descuento por volumen, el desglose completo.
    intro = f"Listo, registro {_format_test_items(selected)}."
    if len(selected) >= 2:
        intro += f" {_estimated_total_text(calculate_custom_profile_total(selected))}"
    return _analysis_settled_response(session, fields, intro)


def _capture_menu_addition_to_profile(session: dict, fields: dict, selected: list[dict]) -> dict:
    """El cliente eligió análisis de un menú de área que se mostró para AGREGAR al perfil
    base (no para empezar de cero). Los suma, recalcula y re-ofrece agregar más o avanza.
    Cierra el estado de personalización."""
    fields.pop("_test_menu_options", None)
    fields.pop("_test_menu_adds_to_profile", None)
    fields.pop("_awaiting_additional_test", None)
    fields.pop("_correction_pending", None)
    fields["_profile_customizing"] = False
    _add_tests_to_order(fields, selected, "add")
    return _analysis_settled_response(session, fields, f"Listo, agrego {_format_test_items(selected)}.")


# Enforcers de catálogo/identificación → app/enforcers/catalogo.py (importados arriba).
# Ronda B → app/enforcers/ayudas.py y flujo.py (importados arriba).
def _catalog_overview_response(fields: dict) -> dict:
    tests = db.list_catalog_tests(limit=500)
    choices = _catalog_overview_choices(tests)
    return _test_options_response(fields, choices, _test_catalog_overview_reply(choices))


def _unsupported_final_user_response(fields: dict) -> dict:
    return {
        "reply": FINAL_USER_MESSAGE,
        "phase": "fase_2_recogida_datos",
        "intent": "unknown",
        "service_area": "unknown",
        "requires_handoff": False,
        "handoff_area": None,
        "captured_fields": fields,
        "confidence": 1.0,
        "message_mode": "flow_progress",
        "pending_intents": [],
        "resume_prompt": "",
    }


def _apply_no_owner_shortcut(
    fields: dict, prev_captured: dict, user_message: str, history: list[dict]
) -> None:
    """Paciente sin dueño (callejero/rescatado): si se está pidiendo el propietario y el
    cliente indica que no hay, se registra "Sin propietario" y se avanza, en vez de
    repreguntar en bucle (regla de negocio confirmada 2026-06-23).

    ERR-092 — nunca pisar un propietario YA capturado. `_detect_which_field_is_being_asked`
    lee el último mensaje del bot completo, así que el ACUSE de un campo ("registro Luciano
    como propietario. ¿Alguna observación?") le hace creer que todavía se pide el
    propietario; ahí un "no tengo ninguna observación" (token "ninguna" ∈ _NO_OWNER_TOKENS)
    borraba el nombre que el cliente acababa de dar. El bot decía la verdad al acusarlo y se
    pisaba a sí mismo un turno después, sin que el cliente pudiera notarlo.
    """
    if fields.get("owner_name") or prev_captured.get("owner_name"):
        return
    if _says_no_owner(user_message) and _detect_which_field_is_being_asked(history) == "owner_name":
        fields["owner_name"] = "Sin propietario"


def _reidentifies_after_escalation(user_message: str) -> bool:
    """¿El cliente escalado por 'no te encuentro' está dando un identificador que SÍ existe?

    Se consulta la BASE: solo un match real reabre la conversación. Un detector de texto no
    alcanza — `_provides_new_identifier` exige la palabra 'veterinaria' o un NIT, y el caso
    real es "sí estamos, somos Maxivet", que no tiene ninguna de las dos. Ante cualquier
    duda o error se devuelve False, que mantiene el silencio: falla del lado seguro.
    """
    tax_id = _extract_tax_id_candidate(user_message, allow_unlabeled=True)
    if tax_id:
        try:
            if db.find_clients_by_tax_id(tax_id):
                return True
        except Exception:
            return False
    name = _extract_clinic_name_candidate(user_message)
    if not name:
        return False
    try:
        return bool(db.find_client_matches(name, limit=3))
    except Exception:
        return False


def _escalate_unfound_client(fields: dict, reply: str = CLIENT_NOT_FOUND_MESSAGE) -> dict:
    # El cliente dice no ser nuevo pero no aparece en la base: derivar a un humano
    # en vez de seguir pidiendo el identificador en bucle.
    fields["_handoff_announced"] = True
    # ERR-088: este escalado NO usa `_blocked` (que es el silencio definitivo del cliente
    # particular). Reusarlo lo volvía irreversible: si el cliente se corregía al turno
    # siguiente dando un nombre real, el bot ya no volvía a hablar nunca. En el corpus hay
    # rachas de 9, 6 y 10 turnos al vacío, con el cliente escribiendo "El bot no esta activo".
    fields["_escalated_unfound_client"] = True
    return {
        "reply": reply,
        "phase": "fase_7_escalado",
        "intent": "new_client",
        "service_area": "new_client",
        "requires_handoff": True,
        "handoff_area": "operaciones",
        "captured_fields": fields,
        "confidence": 1.0,
        "message_mode": "flow_progress",
        "pending_intents": [],
        "resume_prompt": "",
    }


def _client_match_options_reply(query: str | None, matches: list[dict], has_more: bool = False) -> str:
    shown = matches[:MAX_CLIENT_MATCH_OPTIONS]
    # Si todas las coincidencias son la misma veterinaria, son sedes/sucursales.
    distinct_names = {_catalog_item_key(m.get("clinic_name")) for m in shown}
    is_branches = len(distinct_names) == 1 and len(shown) > 1

    if is_branches:
        name = shown[0].get("clinic_name") or "esa veterinaria"
        lines = [f"{name} tiene varias sedes registradas. ¿Desde cuál sede solicitas?"]
        for idx, match in enumerate(shown, start=1):
            address = match.get("address") or "sin dirección registrada"
            lines.append(f"{idx}) {address}")
        lines.append("Responde con el número de la sede.")
        return "\n".join(lines)

    label = query or "ese nombre"
    if len(shown) == 1:
        match = shown[0]
        name = match.get("clinic_name") or "Sin nombre"
        address = match.get("address") or "sin dirección registrada"
        return (
            f"Lo más parecido que encuentro a '{label}' es:\n"
            f"1) {name} - {address}\n"
            "¿Es esta? Responde con el número 1, o dime si no es ninguna."
        )
    lines = [f"Encontré varios clientes registrados con '{label}'. ¿Cuál es el correcto?"]
    for idx, match in enumerate(shown, start=1):
        name = match.get("clinic_name") or "Sin nombre"
        address = match.get("address") or "sin dirección registrada"
        lines.append(f"{idx}) {name} - {address}")
    lines.append("Responde con el número, o dime si ninguna es la tuya.")
    return "\n".join(lines)


def _professional_match_options_reply(doctor: str, matches: list[dict]) -> str:
    """El cliente se identificó con el nombre del MÉDICO, no con el de la veterinaria: se le
    propone la clínica donde figura para que confirme. Nunca se identifica solo."""
    shown = matches[:MAX_CLIENT_MATCH_OPTIONS]
    if len(shown) == 1:
        match = shown[0]
        name = match.get("clinic_name") or "Sin nombre"
        address = match.get("address") or "sin dirección registrada"
        return (
            f"{doctor} figura en nuestros registros en:\n"
            f"1) {name} - {address}\n"
            "¿Es esa la veterinaria? Responde con el número 1, o dime si no es ninguna."
        )
    lines = [f"{doctor} figura en varias veterinarias registradas. ¿Desde cuál solicitas?"]
    for idx, match in enumerate(shown, start=1):
        name = match.get("clinic_name") or "Sin nombre"
        address = match.get("address") or "sin dirección registrada"
        lines.append(f"{idx}) {name} - {address}")
    lines.append("Responde con el número, o dime si ninguna es la tuya.")
    return "\n".join(lines)


def _store_client_match_options(fields: dict, query: str, matches: list[dict]) -> None:
    fields["_client_match_query"] = query
    fields["_client_match_options"] = [
        {
            "id": match.get("id"),
            "clinic_name": match.get("clinic_name"),
            "tax_id": match.get("tax_id"),
            "phone": match.get("phone"),
            "address": match.get("address"),
        }
        for match in matches[:MAX_CLIENT_MATCH_OPTIONS]
    ]


def _clear_client_match_options(fields: dict) -> None:
    fields.pop("_client_match_query", None)
    fields.pop("_client_match_options", None)


# Palabras comunes que NO deben tratarse como un nombre de cliente en la búsqueda exacta de
# refuerzo (segundo intento). Evita falsos positivos al probar palabras sueltas del mensaje.
_EXACT_RETRY_STOPWORDS = frozenset({
    "ninguno", "ninguna", "ningun", "ningunos", "ningunas", "tampoco", "esos", "esas",
    "veterinaria", "clinica", "consultorio", "hospital", "laboratorio", "centro",
    "llama", "llamo", "nombre", "mejor", "busca", "buscar", "tengo", "quiero", "registrada",
    "registrado", "registrados", "cliente", "nueva", "nuevo", "somos", "soy",
    "pero", "entonces", "creo", "entiendo", "perdon", "perdón",
})


def _select_client_match(text: str, fields: dict, signal: str | None = None) -> dict | None:
    options = fields.get("_client_match_options") or []
    if not options:
        return None

    for token in _tokenize(text):
        if token.isdigit():
            index = int(token)
            if 1 <= index <= len(options):
                return options[index - 1]
        if token in _ORDINAL_SELECTIONS:
            index = _ORDINAL_SELECTIONS[token]
            if 1 <= index <= len(options):
                return options[index - 1]

    # UNA sola coincidencia listada ("¿Es esta?") y el cliente AFIRMA ("sí, esa está
    # bien", "exacto"): es una selección. Fuente primaria: la lectura semántica de la
    # IA (user_intent_signal=affirm); fallback: tokens afirmativos (ABIERTO-004: sin
    # esto la afirmación quedaba a merced del modelo y descarrilaba la identificación).
    # No aplica si en el mismo mensaje dice ser cliente nuevo/no registrado.
    if (len(options) == 1
            and (signal == "affirm" or _is_affirmative_text(text))
            and not _claims_unregistered_client(text)
            and not _explicitly_says_new_client(text)):
        return options[0]

    text_key = _catalog_item_key(text)
    query_key = _catalog_item_key(fields.get("_client_match_query"))
    if not text_key or text_key == query_key:
        return None
    # Nombre exacto o contenido completo.
    for option in options:
        name_key = _catalog_item_key(option.get("clinic_name"))
        if len(text_key) >= 4 and (text_key == name_key or text_key in name_key or name_key in text_key):
            return option
    # Match por PALABRAS distintivas: el cliente nombra la sede por parte de su nombre
    # ('la de quinta paredes' → 'Puppy Export Quinta Paredes'). Se puntúa cada opción por
    # tokens significativos compartidos y se elige la de mayor coincidencia ÚNICA (si dos
    # sedes empatan por una palabra común, no se elige — se sigue preguntando).
    text_tokens = {t for t in text_key.split("_") if len(t) >= 4}
    if not text_tokens:
        return None
    scored = sorted(
        ((len(text_tokens & set(_catalog_item_key(o.get("clinic_name")).split("_"))), o) for o in options),
        key=lambda s: s[0], reverse=True,
    )
    if scored and scored[0][0] > 0 and (len(scored) == 1 or scored[0][0] > scored[1][0]):
        return scored[0][1]
    return None


# Preguntas laterales (_operational_side_question_answer, _results_pending_response,
# _has_active_route_context y sus tokens) -> app/laterales.py (3.4a).


def _pre_identification_service_info_response(text: str, fields: dict) -> dict | None:
    tokens = set(_tokenize(text))
    if not tokens:
        return None
    if tokens & {"programar", "agendar", "coordinar"} and tokens & {"ruta", "recogida", "retiro", "muestra", "muestras", "meustras"}:
        return None
    if tokens & {"quiero", "necesito"} and tokens & {"programar", "agendar", "coordinar"}:
        return None

    reply = None
    operational_answer = _operational_side_question_answer(text)
    if operational_answer:
        reply = operational_answer
    elif tokens & {"motivo", "motivos"} and tokens & {"muerte", "muerto", "muerta", "fallecio", "falleció"}:
        reply = (
            "Para investigar una posible causa de muerte necesitamos que el equipo revise el caso y la muestra adecuada. "
            "Por acá no te confirmo eso a ciegas; si quieres, te comunico con una persona del equipo."
        )
    elif tokens & {"muerto", "muerta", "muerte", "fallecio", "falleció"}:
        reply = (
            "Ese tipo de caso lo debe revisar una persona del equipo para decirte qué muestra sirve "
            "y si el análisis aplica. Si quieres programar desde una veterinaria registrada, ahí sí te pido el NIT o el nombre."
        )
    elif tokens & {"retirar", "retiran", "recoger", "recogen", "recogida", "motorizado", "motorizados"}:
        reply = (
            "Sí, recogemos muestras con motorizado asignado para clientes registrados en Bogotá. "
            "Si quieres programar una recogida, ahí sí te pido el NIT o el nombre de la veterinaria."
        )
    elif tokens & {"donde", "dónde", "ubicados", "ubicado", "ubicacion", "ubicación", "ubican", "ubica"}:
        # Solo una PREGUNTA explícita de ubicación dispara esta respuesta. La mera mención de
        # "Colombia"/"Bogotá" (ej. en el nombre de una clínica) ya NO la activa: eso desviaba
        # nombres como "Pet Agro Colombia" a una respuesta de cortesía sin buscar el cliente.
        reply = (
            "Somos A3 Laboratorio Clínico Veterinario y estamos en Bogotá, Colombia. "
            "Atendemos clínicas y profesionales veterinarios registrados."
        )
    elif (tokens & {"metodologia", "metodología", "funciona"}) or (
        tokens & {"como", "cómo", "que", "qué"} and tokens & {"necesito", "requiere", "muestra", "muestras"}
    ):
        reply = (
            "La dinámica es simple: nos dices qué análisis necesitas, confirmamos los datos de la muestra "
            "y coordinamos la recogida si eres una veterinaria o profesional registrado. Para programarlo te pido el NIT o el nombre."
        )
    elif tokens & {"mascotas", "colombia", "bogota", "bogotá"} and tokens & {"hacen", "atienden", "analisis", "análisis"}:
        reply = (
            "Sí, hacemos análisis para pacientes veterinarios y atendemos a clínicas y profesionales registrados en Bogotá. "
            "Si quieres programar una recogida, te pido el NIT o el nombre de la veterinaria."
        )

    if not reply:
        return None
    response = _base_route_response(reply, fields)
    response["message_mode"] = "side_question"
    if operational_answer:
        response["_skip_resume"] = True
    return response


def _active_route_smalltalk_response(session: dict, fields: dict) -> dict | None:
    missing = _missing_route_field(session, fields)
    if not missing:
        return None
    if missing == "pickup_address" and fields.get("_address_confirmation_pending"):
        question = "¿Me confirmas si esa dirección de retiro está correcta?"
    else:
        question = _missing_route_field_question(missing)
    response = _base_route_response(f"Todo bien, gracias. Sigamos con la orden: {question}", fields)
    response["message_mode"] = "small_talk"
    return response


def _reset_order_fields(fields: dict) -> None:
    for field in _ORDER_RESET_FIELDS:
        fields.pop(field, None)
    fields.pop("_custom_profile_summary", None)
    fields.pop("_pending_intents", None)


def _carry_over_stable_fields(fields: dict) -> int:
    """Tras reiniciar la orden, recupera los datos estables del cliente (médico,
    dirección, forma de pago) desde el snapshot de la orden anterior o, si falta,
    desde la memoria persistente del chat. Devuelve cuántos campos se recuperaron."""
    snap = fields.get("_prev_order_snapshot") or {}
    mem = fields.get("_client_memory") or {}
    recovered = 0
    for field in _CLIENT_MEMORY_FIELDS:
        if fields.get(field):
            continue
        value = snap.get(field) or mem.get(field)
        if value:
            fields[field] = value
            if field != "pickup_address":
                recovered += 1
    return recovered


def _payment_method_label(value: str | None) -> str:
    return "pago en línea" if value == "pago_linea" else (value or "")


# Sustantivos que designan al cliente/empresa (no al médico). Para disparar un
# cambio de cliente deben venir junto a una señal de cambio (otra, no, me equivoqué…).
# Sucursal/sede nueva NO registrada: requiere un sustantivo de sede + una señal de
# "nueva/registrar", para no confundir la SELECCIÓN de una sede ya registrada
# ("la sede del norte") con el alta de una sede nueva.
def _restart_identification_for_new_client(chat_id: str, session: dict, fields: dict) -> dict:
    """Cambio de cliente. LÓGICA (L50): corregir UN dato no reinicia el pedido. Con una
    orden EN CURSO (no registrada) se conserva TODO lo ya dado (médico, paciente, análisis,
    pago, observaciones) y solo se re-verifica lo que el cambio afecta: identidad y
    dirección. El reset completo solo aplica cuando la orden anterior ya quedó registrada
    (fase terminal): ahí sí es un pedido nuevo desde cero."""
    order_in_progress = (
        session.get("phase_current") not in TERMINAL_PHASES
        and not fields.get("_order_registered")
        and any(fields.get(k) for k in ("patient_name", "requesting_doctor", "exam_type",
                                        "selected_tests", "_selected_profile_code"))
    )
    if order_in_progress:
        return _switch_client_keep_order(
            chat_id, session, fields,
            "Claro, cambiamos de cliente. ¿Me compartes el NIT o el nombre de la nueva "
            "veterinaria para verificarla? Mantengo el resto de la orden (médico, paciente, "
            "análisis y demás) y al final te la confirmo completa.",
        )
    _reset_order_fields(fields)
    for key in _IDENTIFICATION_RETRY_RESET_FIELDS:
        fields.pop(key, None)
    fields.pop("_client_memory", None)
    fields.pop("_stable_confirm_pending", None)
    if session.get("client_id"):
        db.clear_client_from_session(chat_id)
        session["client_id"] = None
    return _base_route_response(
        "Claro, cambiamos de cliente. ¿Me compartes el NIT o el nombre de la nueva "
        "veterinaria o médico veterinario para verificar si está registrado?",
        fields,
    )


def _switch_client_keep_order(chat_id: str, session: dict, fields: dict, reply: str) -> dict:
    """Motor común de 'cambiar la veterinaria/sede SIN perder la orden': descarta solo la
    identificación y la dirección para re-verificar, y MANTIENE el paciente, el análisis,
    el médico, el pago y las observaciones ya cargados. Corregir un dato nunca borra los
    demás (L50)."""
    for key in _IDENTIFICATION_RETRY_RESET_FIELDS:
        fields.pop(key, None)
    fields.pop("_client_memory", None)
    fields.pop("_stable_confirm_pending", None)
    fields.pop("_correction_pending", None)
    # Descartar menús pegados: sin esto, un menú de perfiles/análisis del cliente anterior
    # contamina el contexto y el modelo 'elige' una opción vieja al re-identificar (QA extremo).
    for key in ("_profile_menu_options", "_test_menu_options", "_test_menu_adds_to_profile",
                "_offering_extra_analysis"):
        fields.pop(key, None)
    if session.get("client_id"):
        db.clear_client_from_session(chat_id)
        session["client_id"] = None
    return _base_route_response(reply, fields)


def _switch_branch_keep_order(chat_id: str, session: dict, fields: dict) -> dict:
    """Cambio de SEDE de la misma orden ('esta orden es para la otra sede')."""
    return _switch_client_keep_order(
        chat_id, session, fields,
        "Claro, cambiamos de sede. ¿Me compartes el NIT o el nombre de la otra veterinaria o "
        "sede para verificarla? Mantengo el resto de la orden (paciente, análisis y demás).",
    )


def _start_followup_service_order_response(fields: dict, user_message: str = "") -> dict:
    _carry_over_stable_fields(fields)

    # Reofrecer también el análisis/perfil de la orden anterior: el cliente lo confirma o
    # pide otro. Se copia del snapshot; si luego dice "cambiar análisis", se limpia y se
    # vuelve a pedir. Los datos del PACIENTE no se heredan (se piden de cero en cada orden).
    snap = fields.get("_prev_order_snapshot") or {}

    # Si el cliente, al pedir otra orden, YA indicó cambiar el análisis en el mismo mensaje
    # ('...pero cambiale el análisis a glucosa'), NO se hereda el viejo: queda vacío para
    # pedírselo y capturarlo por el flujo normal de catálogo (que valida contra el catálogo
    # real). No se adivina el análisis de la frase: extraer tokens sueltos arriesga registrar
    # uno equivocado (ej. 'urianálisis' -> 'ALT'). Lee la intención, no fragmentos.
    if user_message and _followup_wants_new_analysis(user_message):
        pass  # no heredar el análisis anterior; se pedirá el nuevo
    elif not fields.get("exam_type") and snap.get("exam_type"):
        for k in ("exam_type", "selected_tests", "removed_tests", "_selected_profile_code",
                  "_selected_profile_name", "_selected_profile_price", "_selected_profile_description"):
            if snap.get(k):
                fields[k] = snap[k]
        # Si el análisis reofrecido es un perfil del catálogo, marcarlo como "ya ofrecido"
        # para que un ajuste parcial ('el mismo pero sin X') active la personalización del
        # perfil base por el camino existente, en vez de empezar de cero.
        if fields.get("_selected_profile_code"):
            fields["_profile_detail_offered"] = True

    # Datos que se heredan de la orden anterior y se confirman en bloque: la
    # veterinaria/cliente (ya identificado) más los estables (dirección, médico, pago).
    clinic = fields.get("clinic_name") or fields.get("_client_display_name")
    reused: list[tuple[str, str]] = []
    if clinic:
        reused.append(("Veterinaria", clinic))
    # Con pedidos la forma de pago NO es un dato de la orden: es del pedido y se pregunta una
    # sola vez al cerrarlo. Mostrarla acá contradice ese flujo y, peor, la vuelve creíble: en
    # la prueba del 2026-08-14 apareció "Forma de pago: contraentrega" en la segunda orden
    # sin que el cliente la hubiera elegido nunca (el modelo la había rellenado sola).
    heredables = ("pickup_address", "requesting_doctor")
    if not PEDIDOS_ENABLED:
        heredables += ("payment_method",)
    for field in heredables:
        value = fields.get(field)
        if value:
            shown = _payment_method_label(value) if field == "payment_method" else value
            reused.append((_FIELD_LABELS[field].capitalize(), shown))
    if fields.get("exam_type"):
        reused.append(("Análisis", fields.get("exam_type")))

    if not reused:
        return _base_route_response(
            "Perfecto, creamos otra orden de servicio para otro paciente. ¿Cuál es el médico solicitante?",
            fields,
        )

    fields["_stable_confirm_pending"] = True
    lines = ["Perfecto, creamos otra orden de servicio. Mantengo estos datos de la orden anterior:"]
    for label, value in reused:
        lines.append(f"- {label}: {value}")
    cambiables = "dirección, médico o análisis" if PEDIDOS_ENABLED else "dirección, médico, forma de pago o análisis"
    lines.append(f"¿Confirmas o quieres cambiar alguno ({cambiables})?")
    return _base_route_response("\n".join(lines), fields)


def _begin_followup_order(fields: dict, user_message: str = "") -> dict:
    """Inicia una orden de seguimiento: guarda el snapshot de la orden anterior, reinicia
    los datos de la orden (paciente/análisis) conservando el cliente, y arranca el
    reofrecimiento de estables. Centraliza el inicio para que funcione tanto desde la fase
    terminal como tras turnos intermedios (charla) que la sacaron de esa fase."""
    fields.pop("_order_registered", None)
    _snap_keys = set(_ROUTE_REQUIRED_FIELDS) | {
        "selected_tests", "removed_tests", "_selected_profile_code",
        "_selected_profile_name", "_selected_profile_price", "_selected_profile_description",
    }
    snapshot = {k: v for k, v in fields.items() if k in _snap_keys and v}
    _reset_order_fields(fields)
    fields["_prev_order_snapshot"] = snapshot
    ai_response = _start_followup_service_order_response(fields, user_message)
    ai_response["captured_fields"]["_pending_intents"] = []
    return ai_response


def _extract_same_as_field(text: str) -> str | None:
    lower = (text or "").lower().strip()
    for keywords, field in _SAME_AS_FIELD_KEYWORDS:
        for kw in keywords:
            if kw in lower:
                return field
    return None


def _extract_same_as_fields(text: str) -> list[str]:
    lower = (text or "").lower().strip()
    fields: list[str] = []
    for keywords, field in _SAME_AS_FIELD_KEYWORDS:
        for kw in keywords:
            idx = lower.find(kw)
            if idx < 0:
                continue
            window = lower[max(0, idx - 15): idx + len(kw) + 15]
            if any(marker in window for marker in ("mismo", "misma", "mismos", "mismas", "igual", "siempre")):
                if field not in fields:
                    fields.append(field)
                break
    return fields


def _resolve_same_as_previous(fields: dict, user_message: str, history: list[dict]) -> dict | None:
    if not _is_same_as_previous(user_message):
        return None

    prev_snapshot = fields.get("_prev_order_snapshot") or {}
    memory = fields.get("_client_memory") or {}
    if not prev_snapshot and not memory:
        return None

    # El dato recordado puede venir del snapshot de la orden anterior o, si falta
    # (p. ej. nueva sesión del mismo chat), de la memoria persistente del cliente.
    def _recall(field_name: str):
        return prev_snapshot.get(field_name) or memory.get(field_name)

    asked_field = _detect_which_field_is_being_asked(history)
    explicit_field = _extract_same_as_field(user_message)
    explicit_fields = [f for f in _extract_same_as_fields(user_message) if f != "patient_name"]
    mentions_change = bool(set(_tokenize(user_message)) & _CHANGE_TOKENS)
    # Si el mensaje trae señal de cambio ("...solo CAMBIA el paciente") y el campo nombrado
    # NO es el que se preguntó, ese campo es lo que CAMBIA, no "el mismo": el "mismo" se
    # refiere al campo PREGUNTADO. Ej. "el mismo, solo cambia el paciente" al pedir el
    # propietario → resolver el PROPIETARIO desde el snapshot (no el paciente).
    if explicit_field == "patient_name" and mentions_change and not fields.get("owner_name") and _recall("owner_name"):
        field = "owner_name"
    elif explicit_field and asked_field and explicit_field != asked_field and mentions_change:
        field = asked_field
    else:
        field = explicit_field or asked_field
    if not field:
        return None

    fields_to_set = explicit_fields if len(explicit_fields) > 1 else [field]
    assigned = [(f, _recall(f)) for f in fields_to_set if _recall(f)]
    if not assigned:
        return None

    for assigned_field, value in assigned:
        fields[assigned_field] = value
    # ERR-084 no aplica acá: este es el carril de "lo mismo que la orden anterior", donde el
    # nombre sale del snapshot y `user_message` es la frase de referencia ("el mismo"), no un
    # nombre propio que pueda confundirse con una especie.
    _apply_implied_animal_fields(fields, user_message)

    next_missing = None
    for f in _ROUTE_REQUIRED_FIELDS:
        if not fields.get(f) and f != "pickup_address":
            next_missing = f
            break
    if not next_missing:
        for f in _ROUTE_REQUIRED_FIELDS:
            if not fields.get(f):
                next_missing = f
                break

    parts = []
    for assigned_field, value in assigned:
        article, same = _FIELD_GRAMMAR.get(assigned_field, ("el", "el mismo"))
        parts.append(f"{article} {_FIELD_LABELS.get(assigned_field, assigned_field)} es {same}: {value}")
    reply = f"Entiendo que {', '.join(parts)}. Lo confirmo para registrar."
    if next_missing and next_missing in _FIELD_LABELS:
        article = _FIELD_GRAMMAR.get(next_missing, ("el", ""))[0]
        reply += f" ¿Cuál es {article} {_FIELD_LABELS[next_missing]}?"

    return {
        "reply": reply,
        "field": assigned[0][0],
        "value": assigned[0][1],
    }


def _clarify_captured_field(ai_response: dict, prev_fields: dict) -> dict:
    fields = ai_response.get("captured_fields", {})
    newly_set = {}
    for field in _FIELD_LABELS:
        new_val = fields.get(field)
        prev_val = prev_fields.get(field)
        if new_val and not prev_val:
            newly_set[field] = new_val

    clarifications = []
    for new_field, new_value in newly_set.items():
        for other_field in _FIELD_LABELS:
            if other_field != new_field and fields.get(other_field):
                other_value = fields[other_field]
                if _same_text(str(new_value), str(other_value)):
                    new_label = _FIELD_LABELS[new_field]
                    clarifications.append(f"Registro {new_label}: {new_value}.")
                    break

    if clarifications:
        clarification = " ".join(clarifications)
        reply = ai_response.get("reply", "")
        if clarification not in reply:
            ai_response["reply"] = f"{clarification} {reply}"

    return ai_response


def _client_found_reply(fields: dict) -> str:
    name = fields.get("_client_display_name") or fields.get("clinic_name") or "el cliente"
    address = fields.get("_client_address") or fields.get("pickup_address")
    if address:
        return f"Perfecto, encontramos {name}. Tenemos como domicilio de retiro: {address}. ¿Es correcta?"
    return f"Perfecto, encontramos {name}, pero no veo dirección registrada. ¿Cuál es la dirección de retiro?"


# _confirms_new_client, _explicitly_says_new_client → app/detectors.py (importados arriba).


def _provides_new_identifier(text: str, prev_fields: dict) -> bool:
    # ¿La respuesta trae un identificador genuino para volver a buscar?
    # Solo un NIT distinto o un nombre con palabra clave de veterinaria/clínica.
    tax_id = _extract_tax_id_candidate(text, allow_unlabeled=True)
    if tax_id and _compact_identifier(tax_id) != _compact_identifier(prev_fields.get("tax_id")):
        return True
    return bool(set(_tokenize(text)) & {
        "veterinaria", "clinica", "clínica", "consultorio", "hospital", "dr", "dra",
    })


def _identifier_retry_from_text(text: str, history: list[dict]) -> tuple[str | None, str | None]:
    tax_id = _extract_tax_id_candidate(text, allow_unlabeled=True)
    if tax_id:
        return tax_id, None

    clinic_name = _extract_clinic_name_candidate(text)
    if clinic_name and _looks_like_identifier_retry(text, history):
        return None, clinic_name
    return None, None


# _is_affirmative_text, _is_negative_text → app/detectors.py (importados arriba).


# Confirmación de la dirección registrada: la gente confirma con deícticos
# ("sí es ese", "esa misma", "esa está bien") y a veces mezcla una pregunta en
# el mismo mensaje. No exigimos longitud corta ni palabras exactas; una negación
# explícita siempre gana.
# _ADDRESS_CONFIRM_TOKENS → app/detectors.py (importado arriba).


# _confirms_address, _rejects_address → app/detectors.py (importados arriba).


def _address_written_by_user(address, user_message: str) -> bool:
    """¿La dirección aparece escrita en el mensaje del usuario? (mayoría de sus tokens
    presentes). Distingue una dirección DICHA por el cliente de una que el modelo arrastró
    del historial de la conversación."""
    addr_tokens = set(_tokenize(str(address or "")))
    if not addr_tokens:
        return False
    msg_tokens = set(_tokenize(user_message or ""))
    return len(addr_tokens & msg_tokens) / len(addr_tokens) >= 0.6


def _confirms_address_now(ai_response: dict, user_message: str) -> bool:
    """¿El cliente confirma la dirección ofrecida? Fuente PRIMARIA: la lectura semántica de la
    IA (`user_intent_signal=affirm`); fallback: tokens. Si la IA leyó otra intención (negar,
    corregir, cambiar de cliente) NO confirma. Molde de `_confirms_order_now` — piloto de la
    Fase 3.3 (invertir el orden de decisión: el LLM decide, el código valida)."""
    signal = ai_response.get("user_intent_signal")
    if signal == "affirm":
        return True
    if signal in {"negate", "correction", "change_client", "new_or_unregistered_client"}:
        return False
    return _confirms_address(user_message)


def _rejects_address_now(ai_response: dict, user_message: str) -> bool:
    """¿El cliente rechaza/corrige la dirección? Señal primaria (`negate`/`correction`),
    tokens de fallback. Un `affirm` de la IA nunca cuenta como rechazo."""
    signal = ai_response.get("user_intent_signal")
    if signal in {"negate", "correction"}:
        return True
    if signal == "affirm":
        return False
    return _rejects_address(user_message)


# _RESULTS_CHOICE_TOKENS, _OTHER_CHOICE_TOKENS, _is_results_choice, _is_other_choice
# → app/detectors.py (importados arriba).


# _is_order_confirmation, _is_correction_request, _expresses_order_request,
# _wants_to_reconsider_option, _accepts_handoff_offer, _confirms_order_now
# → app/detectors.py (importados arriba).
def _option_reconsider_response(fields: dict) -> dict:
    """Reconduce al menú con calidez cuando el usuario se confundió de opción,
    limpiando el estado de identificación para que elija de nuevo desde cero."""
    for field in _IDENTIFICATION_RETRY_RESET_FIELDS:
        fields.pop(field, None)
    fields["_pending_intents"] = []
    return {
        "reply": OPTION_RECONSIDER_MESSAGE,
        "phase": "fase_1_clasificacion",
        "intent": "unknown",
        "service_area": "unknown",
        "requires_handoff": False,
        "handoff_area": None,
        "captured_fields": fields,
        "confidence": 1.0,
        "message_mode": "small_talk",
        "pending_intents": [],
        "resume_prompt": "",
    }


def _escalate_new_client_turn(
    chat_id: str,
    session: dict,
    user_message: str,
    fields: dict,
    started_from_escalation: bool,
    reply: str = CLIENT_NOT_FOUND_MESSAGE,
) -> str:
    ai_response = _escalate_unfound_client(fields, reply)
    ai_response = _finalize_request(
        chat_id,
        session,
        ai_response,
        started_from_escalation,
        session.get("phase_current", ""),
    )
    return _persist_turn(chat_id, user_message, ai_response)


def _unknown_handoff_response(fields: dict | None = None) -> dict:
    return {
        "reply": ADVISOR_ASSIGNMENT_LINE,
        "phase": "fase_7_escalado",
        "intent": "unknown",
        "service_area": "unknown",
        "requires_handoff": True,
        "handoff_area": "operaciones",
        "captured_fields": fields or {},
        "confidence": 1.0,
        "message_mode": "flow_progress",
        "pending_intents": [],
        "resume_prompt": "",
    }


NEW_BRANCH_OFFER_MESSAGE = (
    "Una sucursal o sede nueva no te la puedo registrar yo, eso lo hace una persona "
    "del equipo. ¿Te derivo para que la registren, o seguimos con una sede que ya tengas "
    "registrada?"
)

# Cuando hay una oferta de derivación pendiente ("¿te derivo o seguimos?"), estas
# palabras indican que el usuario ACEPTA que lo derivemos a una persona.
def _menu_choice_context(session: dict, history: list[dict], fields: dict) -> bool:
    """¿Estamos en el punto donde el usuario elige una opción del menú? O bien el
    bot acaba de ofrecer el menú, o la conversación está al inicio sin intención
    ni datos de una orden en curso (no confundir un '2' suelto con la edad, etc.)."""
    last_bot = _last_bot_message(history)
    if "Consultar resultados" in last_bot and "número" in last_bot:
        return True
    return (
        session.get("intent_current", "unknown") in ("", "unknown", None)
        and not session.get("client_id")
        and not any(fields.get(f) for f in _ROUTE_REQUIRED_FIELDS)
    )


# _enforce_results_message -> app/enforcers/resultados.py (3.4a).


def _same_text(left: str | None, right: str | None) -> bool:
    return " ".join(_tokenize(left or "")) == " ".join(_tokenize(right or ""))


def _awaiting_client_identifier(history: list[dict]) -> bool:
    last_bot = _last_bot_message(history).lower()
    return "nit" in last_bot and (
        "veterinaria" in last_bot or "médico" in last_bot or "medico" in last_bot
        or "nombre" in last_bot or "cliente" in last_bot
    )


def _extract_tax_id_candidate(text: str, allow_unlabeled: bool = False) -> str | None:
    value_pattern = r"[0-9][0-9.\s-]{5,}[0-9](?:\s*-?\s*[A-Za-z])?"
    labeled = re.search(rf"\bnit\s*[:#-]?\s*({value_pattern})", text, flags=re.IGNORECASE)
    if labeled:
        return labeled.group(1).strip(" .,:;-")
    if not allow_unlabeled:
        return None
    match = re.search(rf"\b({value_pattern})\b", text)
    if match:
        return match.group(1).strip(" .,:;-")
    return None


def _extract_clinic_name_candidate(text: str) -> str | None:
    if _is_no_identifier_text(text) or _claims_unregistered_client(text):
        return None

    def _clean_candidate(cand: str) -> str | None:
        cand = cand.strip(" .,:;-")
        cand = re.sub(r"(?i)^(?:m[ií]a|m[ií]o|mi|nuestra|nuestro)\s+(?:es|se llama)\s+", "", cand).strip(" .,:;-")
        cand = re.sub(r"(?i)^(?:es|se llama)\s+", "", cand).strip(" .,:;-")
        tokens = _tokenize(cand)
        if cand and any(ch.isalpha() for ch in cand) and len(tokens) <= 4 \
                and not (set(tokens) & _NON_IDENTIFIER_TOKENS) \
                and not set(tokens) <= {"ese", "esa", "eso", "este", "esta", "aquel", "aquella"}:
            return cand
        return None

    reverse = re.search(
        r"(?i)^\s*([a-záéíóúñü0-9][a-záéíóúñü0-9'&.\- ]{1,40}?)\s+"
        r"(?:es|son)\s+(?:mi|mis|la|las|el|los|nuestra|nuestro)?\s*"
        r"(?:veterinaria|cl[ií]nica)\b",
        text.strip(),
    )
    if reverse:
        cand = _clean_candidate(reverse.group(1))
        if cand:
            return cand

    # Nombre tras un marcador claro al final del mensaje ("...soy de adryvete",
    # "somos la veterinaria X"), aunque el resto del mensaje traiga datos del pedido.
    tail = re.search(
        r"(?i)\b(?:somos|soy de|de la veterinaria|de la cl[ií]nica|veterinaria|cl[ií]nica)\s+"
        r"([a-záéíóúñü0-9][a-záéíóúñü0-9'&.\- ]{1,40})\s*$",
        text.strip(),
    )
    if tail:
        cand = _clean_candidate(tail.group(1))
        if cand:
            return cand
    inline = re.search(
        r"(?i)\b(?:veterinaria|cl[ií]nica)\b[^,.;]{0,60}\b(?:es|se llama|llamada)\s+"
        r"([a-záéíóúñü0-9][a-záéíóúñü0-9'&.\- ]{1,40}?)(?=\s*(?:[,.;]|\sy\s+(?:pues|b[aá]sicamente|quiero|necesito|para|tengo)\b|$))",
        text.strip(),
    )
    if inline:
        cand = _clean_candidate(inline.group(1))
        if cand:
            return cand
    inline = re.search(
        r"(?i)\bsoy de\s+([a-záéíóúñü0-9][a-záéíóúñü0-9'&.\- ]{1,40}?)(?=\s*(?:[,.;]|\sy\s+(?:pues|b[aá]sicamente|quiero|necesito|para|tengo)\b|$))",
        text.strip(),
    )
    if inline:
        cand = _clean_candidate(inline.group(1))
        if cand:
            return cand
    if set(_tokenize(text)) & _NON_IDENTIFIER_TOKENS:
        return None
    candidate = re.sub(r"(?i)\bnit\b.*", "", text).strip(" .,:;-")
    candidate = re.sub(
        r"(?i)^(somos|soy de|soy|de la|del|la veterinaria|veterinaria|clínica|clinica)\s+",
        "",
        candidate,
    ).strip(" .,:;-")
    if any(ch.isalpha() for ch in candidate) and len(_tokenize(candidate)) <= 8:
        return candidate
    return None


def _has_client_marker(text: str) -> bool:
    """El mensaje trae un marcador explícito de cliente ("soy de X", "somos la
    veterinaria X"): permite extraer el nombre aunque el bot aún no haya pedido el NIT."""
    return bool(
        re.search(r"(?i)\b(soy de|somos|de la veterinaria|de la cl[ií]nica)\b", text or "")
        or re.search(r"(?i)\b(?:veterinaria|cl[ií]nica)\b[^,.;]{0,60}\b(?:es|se llama|llamada)\b", text or "")
    )


def _apply_identification_fallbacks(
    fields: dict, user_message: str, history: list[dict],
    signal: str | None = None, message_mode: str | None = None,
) -> None:
    waiting_identifier = _awaiting_client_identifier(history)
    if not fields.get("tax_id"):
        tax_id = _extract_tax_id_candidate(user_message, allow_unlabeled=waiting_identifier)
        if tax_id:
            fields["tax_id"] = tax_id
    # El fallback "nombre pelado" (capturar un texto corto como nombre del cliente porque
    # estábamos pidiendo el identificador) es una RED DE SEGURIDAD para cuando el LLM no
    # interpretó el turno. Si el LLM ya leyó el mensaje COMPLETO y entendió que es una
    # pregunta lateral ("¿dónde están?", "¿cuánto cuesta el hemograma?"), se respeta esa
    # lectura: no se fabrica un nombre con la pregunta. Las señales POSITIVAS de
    # identificador (el LLM marcó provides_client_identifier, o hay un marcador "soy de X")
    # sí capturan siempre.
    bare_name_fallback = (
        waiting_identifier
        and message_mode != "side_question"
        and _looks_like_bare_client_name(user_message)
    )
    if (
        (signal == "provides_client_identifier" or _has_client_marker(user_message)
         or bare_name_fallback)
        and not fields.get("tax_id")
    ):
        clinic_name = _extract_clinic_name_candidate(user_message)
        if clinic_name and not _same_text(clinic_name, fields.get("clinic_name")):
            fields["clinic_name"] = clinic_name
            _clear_client_match_options(fields)
            fields.pop("_client_not_found", None)
            fields.pop("_client_found", None)


def _apply_common_order_fallbacks(fields: dict, user_message: str) -> None:
    if not fields.get("exam_type"):
        tokens = set(_tokenize(user_message))
        if "hemograma" in tokens:
            fields["exam_type"] = "hemograma"
        elif {"analisis", "análisis", "examen", "prueba"} & tokens and "sangre" in tokens:
            fields["exam_type"] = "análisis de sangre"


# _NO_OWNER_TOKENS, _NO_OWNER_PHRASES → app/detectors.py (importados arriba).


# _says_no_owner → app/detectors.py (importado arriba).


def _merge_existing_route_fields(prev_fields: dict, fields: dict) -> None:
    preserve_fields = set(_ROUTE_REQUIRED_FIELDS) | {"selected_tests", "removed_tests"}
    for field in preserve_fields:
        if (fields.get(field) is None or fields.get(field) == "") and prev_fields.get(field):
            fields[field] = prev_fields[field]


def _compact_identifier(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", (value or "").lower())


def _looks_like_identifier_retry(text: str, history: list[dict]) -> bool:
    tokens = set(_tokenize(text))
    if not tokens:
        return False
    if _awaiting_client_identifier(history):
        return True
    if tokens & {"veterinaria", "clinica", "clínica", "consultorio", "hospital", "dr", "dra"}:
        return True
    blocked = _CONTINUE_TOKENS | _AFFIRMATIVE_TOKENS | _NEGATIVE_TOKENS | {"cliente", "nuevo"}
    return len(tokens) <= 4 and not (tokens & blocked)


def _apply_identification_retry(fields: dict, prev_fields: dict, user_message: str, history: list[dict]) -> None:
    if not prev_fields.get("_client_not_found"):
        return

    tax_id, clinic_name = _identifier_retry_from_text(user_message, history)
    if tax_id:
        if _compact_identifier(tax_id) == _compact_identifier(prev_fields.get("tax_id")):
            return
    elif clinic_name:
        if _same_text(clinic_name, prev_fields.get("clinic_name")):
            return
    else:
        fields["tax_id"] = None
        fields["clinic_name"] = None
        _clear_client_match_options(fields)
        return

    for field in _IDENTIFICATION_RETRY_RESET_FIELDS:
        fields.pop(field, None)
    fields["tax_id"] = tax_id
    fields["clinic_name"] = None if tax_id else clinic_name


def _store_client_context(fields: dict, client: dict) -> None:
    fields["_client_found"] = True
    fields["_client_not_found"] = False
    fields["_client_display_name"] = client.get("clinic_name", "")
    fields["_client_address"] = client.get("address") or ""
    fields["_client_phone"] = client.get("phone") or ""
    # Correo de facturación: es por donde la DIAN entrega la factura electrónica. Sin esto,
    # `_try_invoice_in_alegra` creaba el contacto en Alegra siempre sin correo.
    fields["_client_email"] = client.get("email") or ""
    # NIT canónico del cliente (de la BD): necesario para facturar en Alegra cuando el
    # cliente se identificó por NOMBRE. Sin esto, `_try_invoice_in_alegra` recibía
    # tax_id=None y la facturación se saltaba en silencio aunque el cliente tuviera NIT.
    if client.get("tax_id"):
        fields["tax_id"] = client.get("tax_id")
    # Perfiles que esta clínica más pide, precargados UNA vez por conversación. Se guardan en
    # el estado en vez de consultarse en cada turno para no agregar I/O al camino caliente, y
    # para que `flow.py` siga sin tocar la base. Se limpian al cambiar de cliente, junto con
    # el resto del contexto (pedido de A3 del 06/05).
    favoritos = db.list_favorite_profiles(client.get("id"))
    if favoritos:
        fields["_client_favorite_profiles"] = favoritos
    else:
        fields.pop("_client_favorite_profiles", None)


def _limit_to_single_question(text: str) -> str:
    if not text:
        return text
    if text.count("?") <= 1:
        return text
    first_q = text.find("?")
    return text[: first_q + 1].strip()


def _question_keys(text: str) -> set[str]:
    questions = re.findall(r"¿([^?]+)\?", text or "")
    if not questions and "?" in (text or ""):
        questions = (text or "").split("?")[:-1]
    return {" ".join(_tokenize(question)) for question in questions if _tokenize(question)}


def _rephrased_repeated_question(reply: str) -> str:
    tokens = set(_tokenize(reply))
    if "nit" in tokens and ("nombre" in tokens or "veterinaria" in tokens):
        return "Para avanzar, puedes compartir una de estas dos opciones: 1) el NIT, o 2) el nombre exacto de la veterinaria o médico veterinario."
    if {"direccion", "dirección", "domicilio"} & tokens:
        return "Para avanzar, puedes responder: 1) sí, esa dirección está bien, o 2) enviarme la dirección correcta."
    if {"analisis", "análisis", "examen", "perfil"} & tokens:
        return "Para avanzar, puedes decirme: 1) el análisis o perfil que desean, o 2) si quieres ver opciones del catálogo."
    if {"canino", "felino", "especie"} & tokens:
        return "Para seguir, contame: ¿el paciente es canino (perro), felino (gato) u otra especie? Decime cuál y continuamos."
    if {"macho", "hembra"} & tokens or "sexo" in tokens:
        return "Para seguir, ¿el paciente es macho o hembra?"
    if "contraentrega" in tokens or ("pago" in tokens and {"linea", "línea"} & tokens):
        return "Para cerrar, ¿prefieres el pago contraentrega con el motorizado o pago en línea?"
    if {"medico", "médico", "solicitante"} & tokens:
        return "Para avanzar, dime el nombre del médico solicitante de la orden."
    if {"raza", "edad", "propietario", "observaciones"} & tokens:
        return "Para avanzar, dime ese dato de la orden o indícame si no aplica."
    return "Para seguir con la orden necesito ese dato. Si ahora no lo tienes a mano, dime y lo retomamos, o con gusto te comunico con alguien del equipo."


def _avoid_repeated_question(session: dict, ai_response: dict, history: list[dict], prev_fields: dict) -> dict:
    if ai_response.get("requires_handoff") or ai_response.get("phase") in TERMINAL_PHASES:
        return ai_response

    fields = ai_response.get("captured_fields", {})
    # Si en este turno se capturó un dato de ruta NUEVO, hubo progreso: aunque el reply
    # repita la pregunta del campo pendiente, no es un bucle. No reescribir, para no pisar
    # el reconocimiento del dato que el cliente adelantó fuera de orden (R25).
    if any(fields.get(f) and fields.get(f) != prev_fields.get(f) for f in _ROUTE_REQUIRED_FIELDS):
        return ai_response

    # Mientras se arma o personaliza un perfil, repetir "¿agregás otro análisis?"
    # es parte natural de la selección, no un bucle. No reescribir esas preguntas.
    selecting_tests = (
        (fields.get("selected_tests") is not None and not fields.get("exam_type"))
        or fields.get("_profile_customizing")
    )
    if selecting_tests:
        return ai_response

    reply_keys = _question_keys(ai_response.get("reply", ""))
    if not reply_keys:
        return ai_response

    for msg in history:
        if msg.get("role") == "bot" and reply_keys & _question_keys(msg.get("content", "")):
            # ERR-060b: no adivinar el campo por palabras sueltas en el TEXTO del reply (una
            # respuesta que solo re-confirma el sexo ya capturado mientras re-pregunta la raza
            # contiene "macho"/"sexo" y disparaba el canned de sexo por error, tapando la raza
            # real pendiente -> bucle infinito). La fuente de verdad es el campo REALMENTE
            # pendiente (_missing_route_field), no el texto que el modelo eligió para redactar.
            missing = _missing_route_field(session, fields)
            if missing:
                ai_response["reply"] = _missing_route_field_question(missing)
            else:
                ai_response["reply"] = _rephrased_repeated_question(ai_response["reply"])
            break
    return ai_response


def _repeats_last_bot_question(ai_response: dict, history: list[dict], fields: dict) -> bool:
    """Señal determinista de estancamiento (ABIERTO-002): el modelo vuelve a hacer la
    MISMA pregunta que el bot acaba de hacer. Sirve de respaldo al anti-bucle para no
    depender solo de que la IA marque unclear/off_topic. Excluye la selección de
    análisis, donde repetir '¿agregás otro?' es parte normal del flujo (L12)."""
    if ai_response.get("requires_handoff") or ai_response.get("phase") in TERMINAL_PHASES:
        return False
    selecting_tests = (
        (fields.get("selected_tests") is not None and not fields.get("exam_type"))
        or fields.get("_profile_customizing")
    )
    if selecting_tests:
        return False
    reply_keys = _question_keys(ai_response.get("reply", ""))
    if not reply_keys:
        return False
    last_bot = next((m.get("content", "") for m in reversed(history) if m.get("role") == "bot"), "")
    return bool(reply_keys & _question_keys(last_bot))


def _avoid_redundant_client_identity_question(session: dict, ai_response: dict) -> dict:
    if ai_response.get("intent") != "route_scheduling" or ai_response.get("requires_handoff"):
        return ai_response
    fields = ai_response.get("captured_fields", {})
    if not (session.get("client_id") or fields.get("_client_found")):
        return ai_response
    if not _asks_for_client_identity(ai_response.get("reply", "")):
        return ai_response

    missing = _missing_route_field(session, fields)
    if missing and missing != "client":
        ai_response["reply"] = _missing_route_field_question(missing)
    else:
        ai_response["reply"] = "Ya tengo el cliente identificado. ¿Qué análisis o perfil desean?"
    return ai_response


_FORBIDDEN_ROUTE_QUESTION_TOKENS = frozenset({
    "ciudad", "pais", "país", "prioridad", "urgente", "referencia",
    "preparacion", "preparación", "ayuno", "tubo",
})


def _avoid_forbidden_route_question(session: dict, ai_response: dict) -> dict:
    if ai_response.get("intent") != "route_scheduling" or ai_response.get("requires_handoff"):
        return ai_response
    if not ({"?", "¿"} & set(ai_response.get("reply", ""))):
        return ai_response
    if not (set(_tokenize(ai_response.get("reply", ""))) & _FORBIDDEN_ROUTE_QUESTION_TOKENS):
        return ai_response

    missing = _missing_route_field(session, ai_response.get("captured_fields", {}))
    if missing:
        ai_response["reply"] = _missing_route_field_question(missing)
    return ai_response


def _avoid_redundant_route_field_question(session: dict, ai_response: dict) -> dict:
    if ai_response.get("intent") != "route_scheduling" or ai_response.get("requires_handoff"):
        return ai_response
    if ai_response.get("phase") in TERMINAL_PHASES:
        return ai_response

    fields = ai_response.get("captured_fields", {})
    reply = ai_response.get("reply", "")
    for field in _ROUTE_REQUIRED_FIELDS:
        if fields.get(field) and _reply_asks_for_route_field(reply, field):
            missing = _missing_route_field(session, fields)
            if missing and missing != field:
                ai_response["reply"] = _missing_route_field_question(missing)
            break
    return ai_response


# _resume_route_after_lateral_turn -> app/laterales.py (3.4a).


# Datos del paciente que deben responderse con un valor concreto: si en su lugar
# llega un saludo o small talk, hay que reencauzar en vez de capturar basura.
# exam_type queda fuera (lo gobierna el flujo de catálogo/perfil); cliente,
# dirección, pago y observaciones tienen su propio manejo dedicado.
# Señales baratas de respuesta off-topic: saludos y cortesía social. Si TODA la
# respuesta cabe acá, no contesta el dato pedido. Ningún valor válido de los campos
# guardados (canino/felino, macho/hembra, nombres, edad con unidad) cae en este set.
# Frases sociales completas: aunque el mensaje traiga conectores, si contiene una de
# estas claramente no responde el dato pedido.
# Variantes y errores de tipeo comunes de los campos enumerados. Si el modelo no
# captura la respuesta (p. ej. "kanino", "perrito", "masho"), la recuperamos nosotros
# para no repreguntar en bucle. Valores genuinamente ambiguos (ej. "Kany") quedan
# para que el modelo confirme con el usuario.
# El modelo de dominio de animales (especie/sexo) vive en app/species.py (re-exportado arriba).


def _recover_enumerated_answer(
    ai_response: dict, prev_fields: dict, user_message: str, history: list[dict]
) -> dict:
    """Si el bot pidió un campo enumerado (especie/sexo) y el usuario respondió con
    una variante o error de tipeo reconocible que el modelo NO capturó, lo captura
    normalizado para que el flujo avance en vez de repreguntar lo mismo."""
    if ai_response.get("intent") != "route_scheduling" or ai_response.get("requires_handoff"):
        return ai_response
    fields = ai_response.get("captured_fields", {})
    asked = _detect_which_field_is_being_asked(history)
    if asked not in ("species", "sex"):
        return ai_response
    # El modelo ya capturó algo nuevo para ese campo: respetarlo.
    if fields.get(asked) and fields.get(asked) != prev_fields.get(asked):
        return ai_response

    table = _RECOVERABLE_SPECIES if asked == "species" else _RECOVERABLE_SEX
    for token in (t.translate(_ACCENT_TRANSLATION) for t in _tokenize(user_message)):
        if token in table:
            fields[asked] = table[token]
            ai_response["captured_fields"] = fields
            return ai_response
    return ai_response


# ERR-084: campos cuya respuesta es el nombre de una PERSONA (o de una mascota). Si el bot
# preguntó uno de estos, lo que llega es un nombre — nunca una declaración de especie.
_PERSON_NAME_FIELDS = ("requesting_doctor", "owner_name", "patient_name")


def _recover_implied_animal_fields(ai_response: dict, prev_fields: dict, user_message: str,
                                   history: list[dict]) -> dict:
    if ai_response.get("intent") != "route_scheduling" or ai_response.get("requires_handoff"):
        return ai_response
    # ERR-084: la inferencia corría en TODOS los turnos, así que un apellido que además es
    # palabra de animal inventaba especie y sexo y salteaba esas dos preguntas. Casos reales:
    # "José Toro" como médico (orden A3-2026-169: paciente registrado Bovino Macho sin que
    # nadie lo dijera) y "Jorge Toro" como propietario, que convirtió en Bovino un Equino
    # que el cliente YA había declarado. Impacto clínico: los rangos de referencia del
    # laboratorio dependen de la especie.
    last_bot = _last_bot_message(history)
    if any(_reply_asks_for_route_field(last_bot, field) for field in _PERSON_NAME_FIELDS):
        return ai_response
    fields = ai_response.get("captured_fields", {})
    _apply_implied_animal_fields(fields, user_message)
    ai_response["captured_fields"] = fields
    return ai_response


# ERR-074: el cliente que NO sabe la raza (mestizos de la calle, rescatados) quedaba en bucle
# infinito, porque `breed` es obligatorio en ROUTE_REQUIRED_FIELDS y no había forma de decir
# "no aplica": el modelo dejaba el campo vacío a propósito y el enforcer lo re-pedía sin fin.
_UNKNOWN_ANSWER_PHRASES = (
    "no se", "no lo se", "no sabemos", "no sabria", "no sabe", "ni idea", "no tengo idea",
    "desconozco", "no tengo ni idea", "sin raza", "no aplica", "no la se", "no sé",
    "no tenemos", "no la conocemos", "no sabria decirte", "no idea",
    # ERR-083 (QA en vivo 2026-07-22): "Nose" escrito JUNTO es un solo token y el
    # substring "no se" no lo cubre — el bot repreguntaba la raza.
    "nose", "nolose",
    # Negar que TENGA raza es tan común como no saberla (QA real: "Ni tiene raza").
    # Negar que TENGA raza es tan común como no saberla (QA real: "Ni tiene raza").
    # OJO: "mestizo" y "criollo" NO van acá — son razas reales del catálogo, ambiguas
    # entre especies pero razas al fin.
    "no tiene raza", "ni tiene raza", "no tiene", "ninguna", "ninguno", "sin determinar",
    "no esta definida", "no aplica raza", "sin definir",
)
BREED_UNKNOWN = "Sin determinar"


def _says_does_not_know(user_message: str) -> bool:
    text = " ".join(_tokenize(user_message)).translate(_ACCENT_TRANSLATION)
    return any(phrase.translate(_ACCENT_TRANSLATION) in text for phrase in _UNKNOWN_ANSWER_PHRASES)


def _recover_unknown_breed(ai_response: dict, user_message: str, history: list[dict]) -> dict:
    """Si el bot pidió la RAZA y el cliente dice que no la sabe, se registra 'Sin determinar'
    y la orden avanza. Sin esto la orden nunca cerraba (ERR-074)."""
    if ai_response.get("intent") != "route_scheduling" or ai_response.get("requires_handoff"):
        return ai_response
    # `_detect_which_field_is_being_asked` no sirve acá: hace match por substring y "especie"
    # se evalúa antes que "raza", así que un cierre como "anoto Axolote como especie. ¿Cuál es
    # la raza del paciente?" resolvía a species y el guard nunca disparaba.
    if not _reply_asks_for_route_field(_last_bot_message(history), "breed"):
        return ai_response
    fields = ai_response.get("captured_fields", {})
    if fields.get("breed") or not _says_does_not_know(user_message):
        return ai_response
    fields["breed"] = BREED_UNKNOWN
    ai_response["captured_fields"] = fields
    return ai_response


def _recover_patient_name_answer(ai_response: dict, prev_fields: dict, user_message: str,
                                 history: list[dict]) -> dict:
    """Si el bot pidió el NOMBRE del paciente, la respuesta es el nombre — aunque coincida con
    una palabra del dominio animal ('Toro', 'Oso', 'Lobo', 'Puma').

    ERR-075: el prompt instruye que 'toro'/'vaca' son ESPECIE y nunca raza, así que el modelo
    leía 'Toro' como bovino y dejaba `patient_name` vacío → bucle infinito. La inferencia de
    especie se sigue aplicando desde otras frases ('es un toro de 3 años'), no desde esta
    respuesta puntual."""
    if ai_response.get("intent") != "route_scheduling" or ai_response.get("requires_handoff"):
        return ai_response
    if not _reply_asks_for_route_field(_last_bot_message(history), "patient_name"):
        return ai_response
    fields = ai_response.get("captured_fields", {})
    if fields.get("patient_name"):
        return ai_response
    tokens = _tokenize(user_message)
    if len(tokens) != 1 or tokens[0].translate(_ACCENT_TRANSLATION) not in _RECOVERABLE_SPECIES:
        return ai_response
    fields["patient_name"] = _titlecase_value(tokens[0])
    # La especie no se infiere de esta respuesta: el cliente estaba dando el nombre.
    if not prev_fields.get("species"):
        fields["species"] = prev_fields.get("species")
    ai_response["captured_fields"] = fields
    return ai_response


def _recover_breed_and_species(ai_response: dict, prev_fields: dict) -> dict:
    """Normaliza la RAZA contra el catálogo e infiere la especie cuando la raza es inequívoca
    ('Holstein' → Bovino), para no preguntar un dato que el cliente ya dio implícito.

    Solo llena vacíos: nunca pisa una especie que el cliente dijo, nunca vacía la raza y nunca
    toca `reply`. Raza ambigua (Criollo, Mestizo) o desconocida → todo queda como estaba."""
    if ai_response.get("intent") != "route_scheduling" or ai_response.get("requires_handoff"):
        return ai_response
    fields = ai_response.get("captured_fields", {})
    match = _resolve_breed(fields.get("breed"))
    if match.breed:
        fields["breed"] = match.breed
    if match.species and not fields.get("species") and not prev_fields.get("species"):
        fields["species"] = match.species
    ai_response["captured_fields"] = fields
    return ai_response


_AMBIGUOUS_SPECIES_TOKENS = frozenset({
    "animal", "animalito", "mascota", "pequeno", "pequeño", "chiquito", "chiquita", "casa",
})


def _clarify_ambiguous_species(ai_response: dict, prev_fields: dict, user_message: str, history: list[dict]) -> dict:
    if ai_response.get("intent") != "route_scheduling" or ai_response.get("requires_handoff"):
        return ai_response
    if _detect_which_field_is_being_asked(history) != "species":
        return ai_response
    tokens = {t.translate(_ACCENT_TRANSLATION) for t in _tokenize(user_message)}
    if not tokens & _AMBIGUOUS_SPECIES_TOKENS or tokens & set(_RECOVERABLE_SPECIES):
        return ai_response
    fields = ai_response.get("captured_fields", {})
    fields["species"] = prev_fields.get("species")
    ai_response["captured_fields"] = fields
    if "ubicarlo bien" in _last_bot_message(history).lower():
        ai_response["reply"] = "Necesito la especie concreta para seguir: ¿canino, felino u otra especie como conejo, ave o reptil?"
    else:
        ai_response["reply"] = "Para ubicarlo bien, dime una opción: ¿canino/perro, felino/gato u otra especie específica?"
    return ai_response


# "Dr./Dra./Doctor X" dentro de una frase. Fallback para cuando el bot pide el médico y el
# usuario lo da envuelto en ruido (ej. "voy a pedir varias órdenes, soy el Dr. Gastón Alcojor")
# y el modelo se queda con el anuncio sin capturar el dato.
_DOCTOR_NAME_RE = re.compile(
    r"\b(?:dr|dra|doctor|doctora)\.?\s+([A-Za-zÁÉÍÓÚÑáéíóúñ]+(?:\s+[A-Za-zÁÉÍÓÚÑáéíóúñ]+){0,2})",
    re.IGNORECASE,
)


def _recover_doctor_from_text(ai_response: dict, prev_fields: dict, user_message: str, history: list[dict]) -> dict:
    """Fallback: si el bot pidió el médico solicitante y el modelo NO lo capturó, pero el
    mensaje trae 'Dr./Dra./Doctor <nombre>', tomarlo. Tokens como red, no como autoridad."""
    if ai_response.get("intent") != "route_scheduling" or ai_response.get("requires_handoff"):
        return ai_response
    if _detect_which_field_is_being_asked(history) != "requesting_doctor":
        return ai_response
    fields = ai_response.get("captured_fields", {})
    if fields.get("requesting_doctor") and fields.get("requesting_doctor") != prev_fields.get("requesting_doctor"):
        return ai_response  # el modelo ya capturó algo nuevo: respetarlo
    match = _DOCTOR_NAME_RE.search(user_message or "")
    if match:
        fields["requesting_doctor"] = f"Dr. {match.group(1).strip().title()}"
        ai_response["captured_fields"] = fields
    return ai_response


def _apply_handoff_guardrails(ai_response: dict) -> dict:
    intent = ai_response.get("intent", "unknown")
    needs_handoff = bool(ai_response.get("requires_handoff")) or intent in _HANDOFF_INTENTS
    if not needs_handoff:
        ai_response["reply"] = _limit_to_single_question(ai_response.get("reply", ""))
        return ai_response

    ai_response["requires_handoff"] = True
    ai_response["phase"] = "fase_7_escalado"

    if intent == "accounting":
        ai_response["handoff_area"] = "contabilidad"
        ai_response["service_area"] = "accounting"
    elif intent == "new_client":
        ai_response["handoff_area"] = ai_response.get("handoff_area") or "operaciones"
        ai_response["service_area"] = "new_client"
    elif intent == "route_scheduling":
        payment_method = (ai_response.get("captured_fields") or {}).get("payment_method")
        if payment_method == "pago_linea":
            ai_response["handoff_area"] = ai_response.get("handoff_area") or "contabilidad"
            ai_response["reply"] = PAYMENT_ONLINE_HANDOFF_MESSAGE
        ai_response["service_area"] = "route_scheduling"

    cleaned_reply = _strip_question_sentences(ai_response.get("reply", ""))
    if not cleaned_reply:
        cleaned_reply = _default_handoff_reply(ai_response.get("handoff_area"))
    ai_response["reply"] = cleaned_reply
    return ai_response


def _consecutive_affirmatives(history: list[dict]) -> int:
    count = 0
    for msg in reversed(history):
        if msg["role"] != "user":
            continue
        words = set(msg["content"].lower().strip().split())
        if words & _AFFIRMATIVE_TOKENS and len(words) <= 4:
            count += 1
        else:
            break
    return count


# Tope de veces que se re-ofrece un mismo término pendiente antes de descartarlo. Sin esto,
# un término que el cliente nunca resuelve trabaría la orden para siempre (ERR-074 enseñó que
# un campo obligatorio sin salida de emergencia es un bucle infinito).
_MAX_PENDING_OFFERS = 3


def _pending_analysis_blocks_closure(ai_response: dict, fields: dict) -> bool:
    """ERR-076 — garantía de DINERO: la orden no puede cerrarse con algo que el cliente pidió
    y quedó sin resolver (un perfil con varias variantes). Vale más repreguntar que facturar
    de menos. Tras `_MAX_PENDING_OFFERS` intentos se descarta con acuse explícito."""
    pending = list(fields.get("_pending_ambiguous_items") or [])
    if not pending:
        return False
    offers = int(fields.get("_pending_offer_count") or 0) + 1
    if offers > _MAX_PENDING_OFFERS:
        fields.pop("_pending_ambiguous_items", None)
        fields.pop("_pending_offer_count", None)
        return False
    fields["_pending_offer_count"] = offers
    return True


def _prevent_incomplete_route_closure(session: dict, ai_response: dict, fields: dict) -> dict:
    if ai_response.get("intent") != "route_scheduling" or ai_response.get("phase") not in TERMINAL_PHASES:
        return ai_response

    if _pending_analysis_blocks_closure(ai_response, fields):
        pendiente = (fields.get("_pending_ambiguous_items") or [""])[0]
        ai_response["reply"] = (
            f"Antes de cerrar: me quedó pendiente lo de '{pendiente}'. "
            "¿Cuál de las opciones que te mostré prefieres? Si no lo necesitan, decime "
            "'sin eso' y sigo."
        )
        ai_response["phase"] = "fase_2_recogida_datos"
        ai_response["service_area"] = "route_scheduling"
        ai_response["requires_handoff"] = False
        ai_response["handoff_area"] = None
        ai_response["message_mode"] = "flow_progress"
        return ai_response

    missing = _missing_route_field(session, fields)
    if not missing:
        return ai_response

    ai_response["reply"] = _missing_route_field_question(missing)
    ai_response["phase"] = "fase_2_recogida_datos"
    ai_response["intent"] = "route_scheduling"
    ai_response["service_area"] = "route_scheduling"
    ai_response["requires_handoff"] = False
    ai_response["handoff_area"] = None
    ai_response["message_mode"] = "flow_progress"
    return ai_response


# Sin "dia/día/semana" en singular: aparecen en charla común ("buen día") y hacían
# creer que el cliente dio la unidad. La edad en días/semanas se dice en plural.
# Enforcers de anclaje → app/enforcers/grounding.py (importados abajo con alias).
# _enforce_selected_tests_are_catalog_codes → app/enforcers/dinero.py (importado abajo como alias).

# ERR-094: campos cuyo valor nuevo se puede leer del mismo mensaje de corrección. Se excluyen
# los que tienen carril propio: exam_type y selected_tests pasan por el catálogo (nada que
# afecte dinero se toma de texto libre), payment_method es un enum y observations es libre.
_CORRECTABLE_INLINE_FIELDS = frozenset({
    "patient_name", "owner_name", "requesting_doctor",
    "species", "breed", "sex", "patient_age", "pickup_address",
})

# Conectores con que la gente introduce el valor nuevo: "cambia el paciente A Rocky",
# "la edad ES 5 años", "el médico AHORA ES la Dra. Laura", "el paciente SE LLAMA Rocky".
_CORRECTION_VALUE_RE = re.compile(
    r"(?i)\b(?:se\s+llama|ahora\s+es|deber[íi]a\s+ser|ser[íi]a|es|por|a|:)\s+([^,;]{2,45})\s*$"
)

# Ruido que queda pegado adelante del valor cuando la frase repite el nombre del campo
# ("cambia la raza a un mestizo" -> "un mestizo" -> "mestizo").
_CORRECTION_VALUE_NOISE_RE = re.compile(
    r"(?i)^(?:un|una|el|la|los|las|de|del)\s+"
)


def _extract_correction_value(field: str, text: str) -> str | None:
    """Valor nuevo dentro del propio mensaje de corrección, o None si no se puede leer.

    Antes solo entendía `patient_name` y solo con "se llama / paciente es / ahora es", así
    que "cambia el nombre del paciente a Rocky" no matcheaba: el campo se limpiaba y el bot
    RE-PREGUNTABA un dato que el cliente acababa de dar (QA 2026-07-27). Para el resto de los
    campos devolvía None siempre, o sea que corregir la edad o el médico en la confirmación
    costaba un turno extra sí o sí.
    """
    if field not in _CORRECTABLE_INLINE_FIELDS:
        return None
    match = _CORRECTION_VALUE_RE.search(text or "")
    if not match:
        return None
    value = match.group(1).strip(" .,:;-\"'¿?¡!")
    value = _CORRECTION_VALUE_NOISE_RE.sub("", value).strip()
    if not value or len(value) < 2:
        return None
    # La edad sin unidad no sirve ("cambiala a 5"): que la pida el flujo normal.
    if field == "patient_age" and not _age_has_unit(value):
        return None
    return value


# _format_tests_total, _catalog_price_answer y _price_answer_for_order -> app/orders.py (3.4a).


# _confirmation_analysis_adjustment y _enforce_confirmation_step -> app/enforcers/confirmacion.py (3.4a).


def _apply_route_closure_summary(ai_response: dict) -> dict:
    if ai_response.get("message_mode") == "cancellation":
        return ai_response
    if ai_response.get("intent") != "route_scheduling" or ai_response.get("phase") != "fase_6_cierre":
        return ai_response
    # La orden YA está registrada: este turno no es su cierre. Sin este guard, la función
    # regeneraba el bloque "Quedó registrado…" en CUALQUIER turno posterior que siguiera en
    # fase de cierre con los campos completos, y como corre casi al final del pipeline PISA
    # el reply que hubieran puesto el modelo o los enforcers.
    # Con PEDIDOS_ENABLED es peor: `payment_method` deja de ser requerido, así que "campos
    # completos" se cumple siempre, y el mensaje del cierre del PEDIDO ("Listo, cerramos el
    # pedido con N órdenes…") terminaba sobrescrito por el cierre de la orden vieja.
    # Es el tercer sitio del mismo guard: los otros dos son `_finalize_request` y
    # `_enforce_confirmation_step`. `_begin_followup_order` limpia la marca, así que el
    # cierre de la orden SIGUIENTE se muestra normalmente.
    fields = ai_response.get("captured_fields", {})
    if fields.get("_order_registered") or ai_response.get(_SKIP_REQUEST_CREATION):
        return ai_response
    summary = _route_closure_summary(fields)
    if summary:
        ai_response["reply"] = summary
    return ai_response


def _append_courier_notification(reply: str, courier: dict | None) -> str:
    # Por ahora solo se muestra el nombre del motorizado: los teléfonos en la base
    # están sin cargar (traen IDs internos, no números). Cuando se carguen los
    # teléfonos reales, acá se puede volver a anexar el número.
    if not courier:
        return reply
    name = (courier.get("name") or "").strip()
    if not name:
        return reply
    return f"{reply}\n\nMotorizado asignado: {name}."


def _replace_courier_commitment(reply: str) -> str:
    old = "Nuestro motorizado pasará a recoger la muestra."
    if old in reply:
        return reply.replace(old, NO_COURIER_HANDOFF_MESSAGE)
    return f"{reply}\n\n{NO_COURIER_HANDOFF_MESSAGE}"


# Marca efímera del turno (no viaja a captured_fields ni a la base): este turno llega a fase
# terminal pero NO corresponde a una orden nueva. La usa el cierre del pedido. SIN prefijo `_`
# a propósito: no es estado de la conversación, así que no va al catálogo de flags de state.py.
_SKIP_REQUEST_CREATION = "skip_request_creation"


def _current_pedido_id(chat_id: str, session: dict) -> str | None:
    """Pedido abierto del chat; lo abre si es la primera orden. Un fallo de la base no puede
    tumbar el cierre de la orden: se devuelve None y la orden queda suelta, que es el
    comportamiento previo a la decisión 011."""
    try:
        abierto = db.get_open_pedido(chat_id)
        if abierto:
            return abierto["id"]
        nuevo = db.create_pedido(session.get("client_id"), chat_id, session.get("channel") or "telegram")
        return nuevo["id"] if nuevo else None
    except Exception as exc:  # noqa: BLE001
        logger.warning("pedidos: no se pudo abrir/recuperar el pedido de %s: %s", chat_id, exc)
        return None


def _finalize_request(chat_id: str, session: dict, ai_response: dict, started_from_escalation: bool, previous_phase: str) -> dict:
    """Crea la solicitud en BD cuando el turno cierra/escala una orden nueva y
    decora el reply con el motorizado asignado y el número de orden."""
    new_phase = ai_response["phase"]
    should_create_request = (
        new_phase in TERMINAL_PHASES
        and previous_phase not in TERMINAL_PHASES
        and not started_from_escalation
        and ai_response.get("message_mode") != "cancellation"
        # El cierre de un PEDIDO llega a fase terminal pero no es una orden nueva: sus
        # órdenes ya se registraron al confirmarlas una por una (decisión 011).
        and not ai_response.get(_SKIP_REQUEST_CREATION)
        # EL HECHO, no el movimiento: si esta orden YA tiene su registro, no se vuelve a
        # crear, diga lo que diga la fase. Las condiciones de arriba deducen "es una orden
        # nueva" de una transición de fase, y la fase la propone el modelo: alcanza con que
        # rebote (cierre → confirmación → cierre) para que la misma orden se guarde otra vez.
        # Con datos reales llegó a duplicarse cinco veces (A3-2026-901 a 905). Estuvo tapado
        # mientras los atajos de palabras fijas congelaban la conversación en fase terminal;
        # al liberarlos para que el bot entienda a la gente, quedó a la vista.
        # `_begin_followup_order` limpia esta marca, así que "otra orden" sigue funcionando.
        and not (ai_response.get("captured_fields") or {}).get("_order_registered")
    )
    if not should_create_request:
        return ai_response

    # Con pedidos, la orden se cuelga del pedido abierto del chat (se abre en la primera) y
    # NO se factura acá: la factura sale una sola vez, al cerrar el pedido, con todas las
    # órdenes juntas (decisión 011). Sin el flag, todo sigue como antes.
    pedido_id = None
    if PEDIDOS_ENABLED and ai_response.get("intent") == "route_scheduling":
        pedido_id = _current_pedido_id(chat_id, session)

    order_info = db.create_request(chat_id, session, ai_response, pedido_id=pedido_id)
    if ALEGRA_ENABLED and not pedido_id and ai_response.get("intent") == "route_scheduling" and order_info:
        _try_invoice_in_alegra(order_info, ai_response)
    # Marca que ya se registró una ORDEN DE RECOGIDA real, para reconocer un pedido de
    # "otra orden" más adelante aunque la conversación haya salido de la fase terminal.
    # Solo aplica a route_scheduling: un escalado de cliente nuevo / pagos / opción 4 NO
    # es una orden, y marcarlo hacía que un "sí, soy nuevo" disparara el flujo de
    # seguimiento ("creamos otra orden... ¿médico?") en vez de escalar.
    if ai_response.get("intent") == "route_scheduling":
        ai_response.setdefault("captured_fields", {})["_order_registered"] = True
    if ai_response.get("intent") == "route_scheduling" and session.get("client_id"):
        courier = db.get_courier_for_client(session["client_id"])
        if courier:
            ai_response["reply"] = _append_order_number(ai_response["reply"], order_info)
            ai_response["reply"] = _append_courier_notification(ai_response["reply"], courier)
        else:
            ai_response["reply"] = _replace_courier_commitment(ai_response["reply"])
            ai_response["reply"] = _append_order_number(ai_response["reply"], order_info)
            ai_response["phase"] = "fase_7_escalado"
            ai_response["requires_handoff"] = True
            ai_response["handoff_area"] = "operaciones"
        # Cierre cordial al final: ofrecer otra orden o terminar (en todos los casos).
        # Con pedidos el cierre pregunta además por el pago, porque la orden se registró sin
        # forma de pago y el pedido todavía está abierto (decisión 011).
        prompt = PEDIDO_CLOSING_PROMPT if pedido_id else CLOSING_PROMPT
        ai_response["reply"] = f"{ai_response['reply']}\n\n{prompt}"
        if pedido_id:
            campos = ai_response.setdefault("captured_fields", {})
            campos["_pedido_id"] = pedido_id
            # Se acumulan las líneas de cada orden para facturarlas juntas al cerrar el
            # pedido. Se guarda el `profile` ya resuelto (con códigos y precios del catálogo)
            # y no una referencia a la orden: así la factura no depende de releer eventos.
            perfil = (order_info or {}).get("event_payload", {}).get("profile")
            if perfil:
                acumulado = list(campos.get("_pedido_profiles") or [])
                acumulado.append(perfil)
                campos["_pedido_profiles"] = acumulado
            # Y una ficha de la orden para el resumen final. Se arma acá porque es el único
            # momento con TODO junto: `requests` no guarda `requesting_doctor` (vive en el
            # evento) y los precios ya vienen resueltos en `perfil`. Releerlo después
            # obligaría a cruzar `requests` con `request_events`.
            ordenes = list(campos.get("_pedido_ordenes") or [])
            ordenes.append({
                "order_number": (order_info or {}).get("order_number"),
                "patient_name": campos.get("patient_name"),
                "species": campos.get("species"),
                "requesting_doctor": campos.get("requesting_doctor"),
                "exam_type": campos.get("exam_type"),
                "total": int((perfil or {}).get("total_estimated") or 0),
            })
            campos["_pedido_ordenes"] = ordenes
    _record_favorite_profile(session, order_info, ai_response.get("captured_fields", {}))
    return ai_response


def _record_favorite_profile(session: dict, order_info: dict | None, fields: dict) -> None:
    """Registra qué pidió esta clínica, para reofrecérselo la próxima vez.

    Pedido de A3 del 06/05. Se hace acá porque el `event_payload["profile"]` ya viene
    resuelto contra el catálogo (códigos, nombres y precios reales) y corre una sola vez por
    orden gracias al guard de `_order_registered`. Nunca lanza: es un extra sobre el cierre.
    """
    client_id = session.get("client_id")
    perfil = (order_info or {}).get("event_payload", {}).get("profile") or {}
    if not client_id or not perfil:
        return
    # Los ítems del favorito: el perfil base (si lo hay) más los análisis agregados.
    items = []
    base = perfil.get("base_profile") or {}
    if base.get("code"):
        items.append({"code": base.get("code"), "name": base.get("name"),
                      "price": base.get("price"), "item_type": "profile"})
    for test in (perfil.get("added_tests") or []):
        items.append({"code": test.get("code"), "name": test.get("name"),
                      "price": test.get("price"), "item_type": "analysis"})
    if not items:
        return
    nombre = base.get("name") or fields.get("exam_type") or "Perfil frecuente"
    try:
        db.record_custom_profile_use(client_id, items, str(nombre)[:120])
    except Exception as exc:  # noqa: BLE001
        logger.warning("favoritos: no se pudo registrar el uso del cliente %s: %s", client_id, exc)


def _merge_sin_borrar(prev_fields: dict, fields: dict) -> dict:
    """Fusión para el CIERRE del pedido: lo nuevo pisa lo viejo, pero un None del modelo NO
    borra un dato ya capturado. El schema emite todas las claves en cada turno; en el turno
    de cierre ("sigamos con la forma de pago") el modelo mandó exam_type=None, la fusión naif
    lo dejó borrar la orden, y con la orden "incompleta" un empuje posterior pisó la pregunta
    del pago con "¿Qué análisis o perfil desean?" (prueba en vivo 2026-08-15 22:48)."""
    merged = dict(prev_fields)
    merged.update({k: v for k, v in fields.items() if v is not None})
    return merged


def _enforce_open_pedido_close(session: dict, ai_response: dict, prev_fields: dict,
                               user_message: str) -> dict:
    """Cierre del PEDIDO abierto, SEÑAL-PRIMERO (decisión 011).

    Corre DESPUÉS del modelo a propósito. El cliente no dice la palabra que uno espera: para
    terminar puede escribir "listo", "terminala", "ya está", "no va más", "eso sería todo";
    y para el pago, "que sea contra entrega", "pagamos cuando lleguen" o "en efectivo". Una
    lista de tokens nunca cubre eso — el modelo sí lo entiende, y acá se actúa sobre lo que
    entendió: su `user_intent_signal` y el `payment_method` que capturó.

    Los detectores de texto quedan solo como RED, para el turno en que el modelo no marca
    señal (misma jerarquía que el resto del pipeline: la señal manda, el token respalda).
    """
    if not PEDIDOS_ENABLED or not prev_fields.get("_pedido_id"):
        return ai_response

    fields = ai_response.get("captured_fields", {})
    signal = ai_response.get("user_intent_signal")

    # Pedir otra orden gana siempre: el pedido sigue abierto y se le cuelga una orden más.
    if signal == "another_order" or _explicitly_wants_another_order(user_message):
        return ai_response

    # ¿Dio la forma de pago? La fuente primaria es lo que capturó el MODELO; el detector de
    # texto es la red para cuando no la marcó.
    #
    # GUARD DE DINERO: el pago solo vale como orden de cerrar si el cliente lo expresó EN ESTE
    # turno, o si el pedido ya venía esperándolo (le preguntamos y esta es la respuesta). Un
    # `payment_method` ARRASTRADO en captured_fields no alcanza: cerrar y facturar con un valor
    # que el cliente nunca eligió es cobrarle de una forma que no pidió. En la prueba del
    # 2026-08-14 el modelo rellenó "contraentrega" solo, sin que el bot preguntara nunca —
    # bastaba con eso para cerrar el pedido entero y emitir la factura.
    # Si YA le preguntamos, lo que el modelo entendió ES la respuesta y vale con su lectura
    # semántica ("pagamos cuando lleguen"). Si NO le preguntamos, el pago tiene que estar en
    # lo que el cliente ACABA de escribir: un campo que apareció solo no cierra nada.
    esperando_pago = bool(prev_fields.get("_pedido_awaiting_payment"))
    pago_en_el_texto = _payment_method_from_text(user_message)
    payment_method = fields.get("payment_method") or pago_en_el_texto
    if payment_method and (esperando_pago or pago_en_el_texto):
        return _close_pedido_turn(session, _merge_sin_borrar(prev_fields, fields), payment_method)

    # Terminó de cargar órdenes pero todavía no dijo cómo paga: se le pregunta UNA vez.
    # Señales con las que el cliente da por terminada la carga. `cancel` entra porque el
    # modelo la usa para "cerrame eso" / "terminala ahí": con la orden YA registrada no puede
    # anular nada, así que en este contexto significa cerrar el pedido, no cancelarlo.
    wants_to_finish = signal in ("farewell", "negate", "cancel") or _is_farewell(user_message)
    if wants_to_finish and not prev_fields.get("_pedido_awaiting_payment"):
        fields = _merge_sin_borrar(prev_fields, fields)
        fields["_pedido_awaiting_payment"] = True
        return {
            **ai_response,
            # A3 pidió (reunión 28/07) poder dejar una observación del PEDIDO antes de cerrar.
            # Va en el mismo turno que el pago para no agregar un paso más: el cliente que no
            # tiene nada que observar responde solo la forma de pago y sigue de largo.
            "reply": PEDIDO_CLOSING_QUESTION,
            # NO es fase terminal: la orden ya está registrada y lo único que falta es cobrar
            # el pedido. Con `fase_6_cierre` acá, `_finalize_request` leía "entró a cierre" y
            # registraba OTRA orden con los mismos datos — en la prueba con sinónimos llegó a
            # duplicar la misma orden cuatro veces.
            "phase": "fase_2_recogida_datos",
            "intent": "route_scheduling",
            "service_area": "route_scheduling",
            "requires_handoff": False,
            "handoff_area": None,
            "captured_fields": fields,
            "message_mode": "flow_progress",
            _SKIP_REQUEST_CREATION: True,
        }
    return ai_response


_PEDIDO_STALE_HOURS = 1
_ultimo_barrido: list[float] = []


def _sweep_stale_pedidos() -> None:
    """Cierra y factura los pedidos abandonados (decisión 011).

    Disparo OPORTUNISTA: se ejecuta al inicio de un turno, no por cron — el proyecto no tiene
    scheduler y el laboratorio tiene tráfico durante el día, así que alcanza. Si no hay
    tráfico, el pedido queda visible en el dashboard igual, que es la red.

    Nunca lanza: un fallo acá no puede tumbar el turno de un cliente que está escribiendo.
    """
    ahora = time.time()
    # Como mucho una vez cada 10 minutos, para no consultar en cada mensaje.
    if _ultimo_barrido and ahora - _ultimo_barrido[-1] < 600:
        return
    _ultimo_barrido.append(ahora)
    del _ultimo_barrido[:-1]
    try:
        pendientes = db.list_stale_pedidos(_PEDIDO_STALE_HOURS)
    except Exception as exc:  # noqa: BLE001
        logger.warning("pedidos: falló el barrido de abandonados: %s", exc)
        return
    for pedido in pendientes:
        pedido_id = pedido.get("id")
        try:
            ordenes = db.list_pedido_requests(pedido_id)
            db.close_pedido(pedido_id, pedido.get("payment_method"))
            # Se avisa SIEMPRE, con o sin factura: operaciones tiene que saber que este
            # pedido se cerró solo, porque el cliente nunca confirmó la forma de pago.
            logger.warning(
                "pedidos: %s (%s) cerrado por inactividad tras %sh con %s orden(es) — "
                "revisar con operaciones: el cliente no confirmó el cierre",
                pedido.get("pedido_number") or pedido_id, pedido.get("external_chat_id"),
                _PEDIDO_STALE_HOURS, len(ordenes),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("pedidos: no se pudo cerrar el abandonado %s: %s", pedido_id, exc)


def _pedido_summary(ordenes: list[dict], fields: dict, payment_method: str) -> str:
    """Resumen del PEDIDO completo: cada orden con su paciente, médico y análisis, y el
    TOTAL consolidado (decisión 011).

    A3 lo pidió así en la reunión del 28/07: con tres pacientes en una sola factura, un
    renglón por orden no alcanza — la veterinaria necesita ver qué se le está cobrando por
    cada uno antes de confirmar.

    Se usan las fichas de `_pedido_ordenes`, que `_finalize_request` arma al cerrar cada
    orden: es el único momento con todo junto, porque `requests` no guarda
    `requesting_doctor` (vive en el evento) y los precios ya vienen resueltos ahí. Si esas
    fichas faltan, se cae a las filas de `requests`, que al menos tienen paciente y análisis.
    """
    fichas = list(fields.get("_pedido_ordenes") or [])
    filas = fichas or ordenes
    lineas, total = [], 0

    for orden in filas:
        etiqueta = orden.get("order_number") or "(sin número)"
        paciente = orden.get("patient_name") or "paciente"
        especie = orden.get("species")
        lineas.append(f"\n{etiqueta} · {paciente}" + (f" ({especie})" if especie else ""))
        if orden.get("requesting_doctor"):
            lineas.append(f"  Médico: {orden['requesting_doctor']}")
        lineas.append(f"  Análisis: {orden.get('exam_type') or 'sin especificar'}")
        subtotal = int(orden.get("total") or 0)
        total += subtotal
        if subtotal:
            lineas.append(f"  Subtotal: {_money(subtotal)}")

    encabezado = (f"Listo, cerramos el pedido con {len(ordenes)} "
                  f"{'orden' if len(ordenes) == 1 else 'órdenes'}:")
    cierre = [f"\nForma de pago: {payment_method}"]
    if total:
        cierre.append(f"TOTAL DEL PEDIDO: {_money(total)}")
    return "\n".join([encabezado, *lineas, *cierre])


def _close_pedido_turn(session: dict, fields: dict, payment_method: str) -> dict:
    """Cierra el pedido: registra la forma de pago, emite UNA factura con todas sus órdenes
    y devuelve el resumen del pedido. Es el final del camino de la decisión 011."""
    pedido_id = fields.get("_pedido_id")
    try:
        db.close_pedido(pedido_id, payment_method)
        ordenes = db.list_pedido_requests(pedido_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("pedidos: no se pudo cerrar el pedido %s: %s", pedido_id, exc)
        ordenes = []
    cuerpo = _pedido_summary(ordenes, fields, payment_method)

    if ALEGRA_ENABLED:
        _try_invoice_pedido(pedido_id, fields)

    fields.pop("_pedido_id", None)
    fields.pop("_pedido_profiles", None)
    fields.pop("_pedido_ordenes", None)
    fields.pop("_pedido_awaiting_payment", None)
    fields["_pedido_cerrado"] = True
    return {
        "reply": f"{cuerpo}\n\nQuedamos atentos. 🙂",
        # El pedido se cierra en fase terminal, pero sin crear una orden nueva: las órdenes
        # ya se registraron una por una al confirmarlas.
        _SKIP_REQUEST_CREATION: True,
        "phase": "fase_6_cierre",
        "intent": "route_scheduling",
        "service_area": "route_scheduling",
        "requires_handoff": False,
        "handoff_area": None,
        "captured_fields": fields,
        "confidence": 1.0,
        "message_mode": "flow_progress",
        "pending_intents": [],
        "resume_prompt": "",
    }


def _record_invoice_failure(request_id: str, reason: str, detail: str = "") -> None:
    """Deja rastro persistente de una orden que quedó SIN facturar.

    Antes un fallo de Alegra solo escribía un warning en el log y se perdía: nadie
    podía saber después qué órdenes quedaron sin factura. Ahora queda como evento
    `alegra_failed` en request_events, consultable desde el dashboard. Nunca lanza:
    si ni siquiera se puede registrar el fallo, se cae al log y sigue."""
    logger.warning("Alegra: orden %s sin facturar (%s) %s", request_id, reason, detail)
    if not request_id:
        return
    try:
        db.create_request_event(
            request_id, "alegra_failed", {"reason": reason, "detail": detail[:500]}
        )
    except Exception as e:  # noqa: BLE001 — registrar el fallo nunca puede tumbar el cierre
        logger.warning("Alegra: además falló registrar el evento de %s: %s", request_id, e)


def _try_invoice_pedido(pedido_id: str | None, fields: dict) -> None:
    """UNA factura para todo el pedido (decisión 011): concatena las líneas de todas sus
    órdenes. Igual que la facturación por orden, es complementaria — cualquier fallo se
    registra y se ignora, nunca rompe el cierre ni la recogida.

    El pedido queda en 'cerrado' y NO pasa a 'facturado' si Alegra falla: esa diferencia es
    justamente lo que permite ver después qué pedidos quedaron sin factura."""
    if not pedido_id:
        return
    try:
        lines = []
        fichas = fields.get("_pedido_ordenes") or []
        for i, perfil in enumerate(fields.get("_pedido_profiles") or []):
            # Cada línea lleva el paciente de SU orden: la factura del pedido junta varios.
            paciente = (fichas[i] or {}).get("patient_name") if i < len(fichas) else None
            lines.extend(billing.build_invoice_lines(perfil, paciente))
        if not lines:
            logger.warning("pedidos: %s sin líneas facturables", pedido_id)
            return
        nit = fields.get("tax_id")
        if not nit:
            # Puerta del dinero (Ronda 3, bloque_partido: pedido cerrado SIN factura): si
            # algún carril de identificación no copió el NIT al estado, se re-resuelve
            # contra la base con el nombre YA identificado antes de renunciar a facturar.
            nombre = fields.get("clinic_name") or fields.get("_client_display_name")
            cliente = db.find_client_exact(nombre) if nombre else None
            nit = (cliente or {}).get("tax_id")
        if not nit:
            logger.warning("pedidos: %s sin NIT del cliente, no se factura", pedido_id)
            return
        name = fields.get("clinic_name") or fields.get("_client_display_name") or "Cliente A3"
        date = datetime.now(APP_TIMEZONE).date().isoformat()
        extra = {"email": fields.get("_client_email"), "phone": fields.get("_client_phone")}
        result = billing.invoice_order(nit, name, lines, date, {k: v for k, v in extra.items() if v})
        if result and result.get("invoice_id"):
            db.mark_pedido_invoiced(pedido_id, str(result["invoice_id"]))
        else:
            logger.warning("pedidos: %s cerrado sin factura (Alegra no devolvió id)", pedido_id)
    except alegra.AlegraError as e:
        logger.warning("pedidos: %s cerrado sin factura (Alegra): %s", pedido_id, e)
    except Exception as e:  # noqa: BLE001 — facturar jamás debe tumbar el cierre
        logger.warning("pedidos: %s cerrado sin factura (inesperado): %s", pedido_id, e)


def _try_invoice_in_alegra(order_info: dict, ai_response: dict) -> None:
    """Factura la orden en Alegra (borrador) al cerrarla. La facturación es complementaria:
    cualquier fallo se registra y se ignora — nunca rompe el cierre ni la recogida del cliente.
    Guarda los IDs de Alegra como evento `alegra_invoiced`, y todo camino que termine sin
    factura queda como `alegra_failed` (no toca el esquema de Supabase)."""
    request_id = order_info.get("request_id")
    try:
        fields = ai_response.get("captured_fields", {})
        profile = (order_info.get("event_payload") or {}).get("profile")
        lines = billing.build_invoice_lines(profile, fields.get("patient_name"))
        if not lines:
            _record_invoice_failure(request_id, "sin_lineas_facturables")
            return
        nit = fields.get("tax_id")
        if not nit:
            _record_invoice_failure(request_id, "cliente_sin_nit")
            return
        name = fields.get("clinic_name") or fields.get("_client_display_name") or "Cliente A3"
        date = datetime.now(APP_TIMEZONE).date().isoformat()
        extra = {"email": fields.get("_client_email"), "phone": fields.get("_client_phone")}
        result = billing.invoice_order(nit, name, lines, date, {k: v for k, v in extra.items() if v})
        if result and result.get("invoice_id"):
            db.create_request_event(request_id, "alegra_invoiced", result)
        else:
            _record_invoice_failure(request_id, "alegra_sin_factura")
    except alegra.AlegraError as e:
        _record_invoice_failure(request_id, "error_alegra", str(e))
    except Exception as e:  # noqa: BLE001 — la facturación jamás debe tumbar el cierre
        _record_invoice_failure(request_id, "error_inesperado", str(e))


def _remember_client_fields(fields: dict) -> None:
    """Guarda en la memoria persistente del chat los datos estables del cliente
    presentes en este turno. Se reofrecen luego cuando dice 'el mismo de siempre'."""
    memory = dict(fields.get("_client_memory") or {})
    for field in _CLIENT_MEMORY_FIELDS:
        value = fields.get(field)
        if value:
            memory[field] = value
    if memory:
        fields["_client_memory"] = memory


def _observe_state_health(fields: dict, new_phase: str = "") -> None:
    """Fase 3.2 (modo DETECCIÓN, no bloqueo): observa la salud del estado tras cada
    turno sin alterar el flujo. Loggea (1) banderas incoherentes (dos que no pueden
    coexistir = "banderas pegadas"), (2) flags de control fantasma/typos, y (3)
    transiciones de fase fuera del grafo documentado — las tres son la raíz de los
    bucles y del contexto perdido (clusters 3 y 6). Hacerlas visibles ANTES de imponer
    la FSM. Nunca lanza: si el observador falla, el turno sigue igual."""
    try:
        st = state.ConversationState(fields if isinstance(fields, dict) else {})
        try:
            st.assert_valid()
        except AssertionError as exc:
            logger.warning("estado incoherente tras el turno: %s", exc)
            if FSM_ENFORCE:
                healed = st.heal()
                if healed:
                    logger.warning("FSM_ENFORCE: estado reparado: %s", healed)
        unknown = st.unknown_flags()
        if unknown:
            logger.warning(
                "flags de control desconocidas (posible typo/fantasma): %s", sorted(unknown)
            )
        prev_phase = _turn_prev_phase.get()
        if prev_phase and new_phase and not state.is_legal_transition(prev_phase, new_phase):
            logger.warning("transición de fase no prevista: %s -> %s", prev_phase, new_phase)
    except Exception:  # pragma: no cover - defensivo, nunca debe romper el turno
        logger.debug("observador de estado falló (ignorado)", exc_info=True)


def _persist_turn(chat_id: str, user_message: str, ai_response: dict) -> str:
    db.save_message(chat_id, user_message, "user")
    db.save_message(chat_id, ai_response["reply"], "bot")
    fields = ai_response.get("captured_fields", {})
    fields["_pending_intents"] = ai_response.get("pending_intents", [])
    _remember_client_fields(fields)
    _observe_state_health(fields, ai_response.get("phase", ""))
    ai_response["captured_fields"] = fields
    db.update_session(chat_id, ai_response)
    return ai_response["reply"]


_CAMPOS_PACIENTE = ("species", "breed", "sex", "patient_age", "owner_name")


def _order_boundary_response(session: dict, ai_response: dict, prev: dict,
                             user_message: str) -> dict | None:
    """FRONTERA DE ORDEN humana (ERR-117, decisión del usuario 2026-08-15): el cliente marca
    el cambio de paciente como le sale, no con el protocolo registrar→"otra orden".

    Dos disparadores, por SEÑAL + ESTADO (nunca por lista de palabras — L65):
    A. Pide OTRA ORDEN a mitad de la actual (señal `another_order` o el detector de red).
    B. Describe un paciente NUEVO en bloque: cambió el nombre Y ≥2 datos más del paciente en
       el mismo turno, con la orden actual ya cargada (paciente + análisis). Antes esto se
       leía como CORRECCIÓN y sobrescribía el formulario: en el QA de estrés un cliente cargó
       5 pacientes y se registraron CERO órdenes.

    Devuelve None si no hay frontera. Si la hay:
    - orden actual COMPLETA → respuesta en fase_6_cierre con los campos ACTUALES (el
      `_finalize_request` de siempre la registra, igual que un "sí") y `boundary_next` con
      los datos del paciente nuevo para abrir la siguiente sin repreguntar nada.
    - orden actual INCOMPLETA → pregunta determinística del campo que falta, nombrando al
      paciente — nunca un bucle.
    El llamador la resuelve por fuera del pipeline: es determinística de punta a punta y los
    enforcers posteriores (captura de códigos del mensaje, confirmación) no deben tocarla —
    los códigos del paciente NUEVO no pueden engancharse a la orden que se está cerrando.
    """
    if ai_response.get("intent") != "route_scheduling":
        return None
    if prev.get("_order_registered") or not (session.get("client_id") or prev.get("_client_found")):
        return None
    fields = ai_response.get("captured_fields") or {}
    signal = ai_response.get("user_intent_signal")

    # CANCELACIÓN de la orden EN CURSO (QA de estrés, ERR-119.2): "no, mejor esa no,
    # borrala". Sin carril, el modelo improvisaba ("¿la dejo en pausa?") sin limpiar NADA, y
    # esta misma frontera después insistía en cerrar la orden cancelada — duplicaciones.
    # Señal-primero; solo aplica a una orden a medio cargar (lo registrado no se toca acá).
    if (signal == "cancel" and prev.get("patient_name")
            and not prev.get("_order_registered")):
        actual = dict(prev)
        nombre = actual.get("patient_name")
        # Los ESTABLES (médico, dirección) sobreviven a la cancelación: viajan por el
        # snapshot igual que en el followup — lo descartado es el PACIENTE y su análisis.
        _snap = {k: v for k, v in actual.items() if k in _CLIENT_MEMORY_FIELDS and v}
        _reset_order_fields(actual)
        actual["_prev_order_snapshot"] = _snap
        _carry_over_stable_fields(actual)
        actual["_pending_intents"] = []
        return _base_route_response(
            f"Listo, descarto la orden de {nombre} — no queda registrada. "
            "¿Cargamos otra orden, o cerramos el pedido?", actual)

    quiere_otra = signal == "another_order" or _wants_new_order_strict(user_message)
    nombre_nuevo = bool(fields.get("patient_name") and prev.get("patient_name")
                        and str(fields["patient_name"]).strip().lower()
                        != str(prev["patient_name"]).strip().lower())
    cambiados = sum(1 for f in _CAMPOS_PACIENTE
                    if fields.get(f) and fields.get(f) != prev.get(f))
    orden_cargada = bool(prev.get("patient_name") and (
        prev.get("exam_type") or prev.get("selected_tests") or prev.get("_selected_profile_code")))
    es_bloque = (nombre_nuevo and cambiados >= 2 and orden_cargada
                 and signal != "correction" and not _is_correction_request(user_message))
    if not (quiere_otra or es_bloque):
        return None

    actual = dict(prev)
    falta = _missing_route_field(session, actual)
    # El cliente ya pasó a otro paciente: si lo único pendiente es la observación, la orden
    # queda "sin observaciones" — hacerlo volver a un campo opcional sería el protocolo
    # robótico que el usuario pidió eliminar.
    if falta == "observations":
        actual["observations"] = "sin observaciones"
        falta = _missing_route_field(session, actual)

    if falta:
        paciente = actual.get("patient_name") or "este paciente"
        resp = _base_route_response(
            f"¡Con gusto cargamos otra! Para cerrar la de {paciente} me falta un dato. "
            f"{_missing_route_field_question(falta)}", actual)
        return resp

    cerrado = _base_route_response("(cierre por frontera)", actual)
    cerrado["phase"] = "fase_6_cierre"
    siguiente: dict = {}
    if es_bloque or quiere_otra:
        for k in ("patient_name",) + _CAMPOS_PACIENTE:
            v = fields.get(k)
            if v and v != prev.get(k):
                siguiente[k] = v
        # El análisis dicho en la MISMA frase es del paciente NUEVO, y se resuelve DEL
        # MENSAJE contra el catálogo — no de los campos del modelo: en el turno del bloque el
        # modelo suele estructurar solo al paciente, la orden nueva nacía sin análisis, y con
        # la orden vacía la frontera SIGUIENTE no disparaba — en el maratón de 10 eso corrió
        # todos los análisis una orden (+1) y perdió los de la primera de la cascada.
        try:
            especie = siguiente.get("species") or fields.get("species") or prev.get("species")
            codes = _profile_codes_from_text(user_message)
            perfiles = db.get_catalog_profiles_by_codes(codes, especie) if codes else []
            cod_perfil = {str(p.get("code")) for p in perfiles}
            if perfiles:
                p0 = perfiles[0]
                siguiente["_selected_profile_code"] = p0.get("code")
                siguiente["_selected_profile_name"] = p0.get("name")
                siguiente["_selected_profile_price"] = int(p0.get("price") or 0)
                siguiente["exam_type"] = p0.get("name")
            rows = db.list_catalog_tests(limit=5000)
            codigos_test = {str(r.get("code")) for r in rows}
            # Códigos literales del mensaje + análisis NOMBRADOS con el criterio estricto
            # del anclaje (`names_test`: contenido distintivo, nunca palabras de área). La
            # resolución difusa de bloque entero quedó descartada — agarraba matches
            # espurios (un '161' que nadie pidió); `names_test` es la vara ya probada.
            tests = [c for c in codes if c not in cod_perfil and c in codigos_test]
            for r in rows:
                cod = str(r.get("code"))
                if cod not in tests and cod not in cod_perfil and catalog.names_test(user_message, r):
                    tests.append(cod)
            if tests:
                siguiente["selected_tests"] = tests
                if not perfiles:
                    siguiente["exam_type"] = f"Perfil personalizado ({len(tests)} análisis)"
        except Exception:  # sin catálogo, la orden nueva pedirá el análisis normalmente
            pass
    cerrado["boundary_next"] = siguiente
    return cerrado


def _consume_boundary_next(session: dict, ai_response: dict) -> None:
    """Abre la orden SIGUIENTE tras el cierre por frontera: snapshot + reset + estables (sin
    reofrecimiento en bloque: el cliente está en racha) + los datos que ya dio del paciente
    nuevo, y la pregunta del primer campo que falte."""
    siguiente = ai_response.pop("boundary_next", None)
    if siguiente is None:
        return
    fields = ai_response.get("captured_fields") or {}
    fields.pop("_order_registered", None)
    _snap_keys = set(_ROUTE_REQUIRED_FIELDS) | {
        "selected_tests", "removed_tests", "_selected_profile_code",
        "_selected_profile_name", "_selected_profile_price", "_selected_profile_description",
    }
    snapshot = {k: v for k, v in fields.items() if k in _snap_keys and v}
    _reset_order_fields(fields)
    fields["_prev_order_snapshot"] = snapshot
    _carry_over_stable_fields(fields)
    fields.update(siguiente)
    fields["_pending_intents"] = []

    falta = _missing_route_field(session, fields)
    nombre = siguiente.get("patient_name")
    intro = f"Sigo con {nombre}: " if nombre else "Vamos con la siguiente orden. "
    pregunta = _missing_route_field_question(falta) if falta else "¿Qué análisis o perfil desean?"
    # El reply del cierre trae el "¿Necesitas cargar otra orden…?" al final: se reemplaza por
    # la continuación — el cliente YA dijo que va otra.
    reply = ai_response.get("reply") or ""
    for cola in (PEDIDO_CLOSING_PROMPT, CLOSING_PROMPT):
        reply = reply.replace(cola, "").rstrip()
    ai_response["reply"] = f"{reply}\n\n{intro}{pregunta}"
    ai_response["phase"] = "fase_2_recogida_datos"
    ai_response["captured_fields"] = fields


def _enforce_comprehension_recheck(session: dict, ai_response: dict, prev_captured: dict,
                                   user_message: str, history: list[dict]) -> dict:
    """PARTE 2 — coherencia pregunta↔captura (pedido del usuario, 2026-08-15): "si no
    entiende, que repregunte antes de avanzar a una etapa". Dispara solo ante INCOHERENCIA,
    nunca por defecto, para no volver el flujo cargoso:

    1. El modelo marcó `provides_requested_data` pero NINGÚN dato de la orden cambió — dice
       que el cliente dio el dato y no capturó nada: contradicción.
    2. `confidence` baja (<0.45) con el turno sin captura: el propio modelo admite que no
       entendió — el schema siempre tuvo este campo y nadie lo leía.

    En ambos casos se repregunta nombrando el dato pedido, determinístico. Si el turno
    capturó algo, puso un menú, o trae una señal con carril propio (corrección, cierre,
    otra orden…), este guard no interviene."""
    if ai_response.get("intent") != "route_scheduling" or ai_response.get("requires_handoff"):
        return ai_response
    fields = ai_response.get("captured_fields") or {}
    if not (session.get("client_id") or fields.get("_client_found")):
        return ai_response
    signal = ai_response.get("user_intent_signal")
    if signal in ("correction", "farewell", "another_order", "cancel", "change_client",
                  "negate", "affirm"):
        return ai_response
    asked = _detect_which_field_is_being_asked(history)
    if not asked or asked == "client" or fields.get(asked):
        return ai_response
    _campos_orden = _ROUTE_ORDER_FIELDS_BEFORE_PAYMENT + ("selected_tests",
                                                          "_selected_profile_code",
                                                          "payment_method")
    progreso = any(fields.get(f) and fields.get(f) != prev_captured.get(f)
                   for f in _campos_orden)
    if (progreso or fields.get("_test_menu_options") or fields.get("_profile_menu_options")
            or fields.get("_awaiting_additional_test")):
        return ai_response
    # Una respuesta lateral legítima (precio, horario) responde y retoma: no se pisa.
    if "$" in (ai_response.get("reply") or ""):
        return ai_response
    conf = ai_response.get("confidence")
    dice_que_dio = signal == "provides_requested_data"
    confianza_baja = isinstance(conf, (int, float)) and conf < 0.45
    if not (dice_que_dio or confianza_baja):
        return ai_response
    ai_response["reply"] = ("Perdona, creo que no te entendí bien. "
                            + _missing_route_field_question(asked))
    ai_response["phase"] = "fase_2_recogida_datos"
    ai_response["message_mode"] = "flow_progress"
    return ai_response


def _candado_provenancia_tests(fields: dict, prev_captured: dict, user_message: str) -> None:
    """Candado de provenancia (ERR-114): los análisis de la orden solo CRECEN por lo que el
    cliente acaba de decir o elegir. Un código nuevo respecto del estado previo se acepta
    solo si (1) está literal en el mensaje, (2) el mensaje lo NOMBRA (catalog.names_test),
    (3) sale del menú activo, o (4) el cliente dijo "el de siempre". El resto se revierte en
    silencio.

    Debe correr sobre la salida de CADA llamada al modelo — hay DOS `generate_turn` en
    process_turn (el principal y el del camino de identificación), y por el segundo, sin
    candado, los `selected_tests` de la ORDEN ANTERIOR que el modelo re-emite desde el
    historial entraban a la orden nueva: $24.000 de más en análisis nunca pedidos (prueba en
    vivo 2026-08-14 21:21, reproducido en replay)."""
    emitidos = _as_text_items(fields.get("selected_tests"))
    previos = set(_as_text_items(prev_captured.get("selected_tests")))
    nuevos = [c for c in emitidos if c not in previos]
    if not nuevos or _is_same_as_previous(user_message):
        return
    menu_ok = {str(o.get("code")) for o in (prev_captured.get("_test_menu_options") or [])
               if o.get("code")}
    sospechosos = [c for c in nuevos if c not in (user_message or "") and c not in menu_ok]
    if sospechosos:
        try:
            rows = {str(r.get("code")): r for r in db.list_catalog_tests(limit=5000)}
            sospechosos = [c for c in sospechosos
                           if not (c in rows and catalog.names_test(user_message, rows[c]))]
        except Exception:  # sin catálogo no se puede validar: no tocar nada
            sospechosos = []
    if sospechosos:
        kept = [c for c in emitidos if c not in set(sospechosos)]
        fields["selected_tests"] = kept or prev_captured.get("selected_tests")


def process_turn(
    chat_id: str,
    user_message: str,
    on_progress: Callable[[str], None] | None = None,
    channel: str = "telegram",
) -> str | None:
    session = db.get_or_create_session(chat_id, channel=channel)
    session["channel"] = channel
    history = db.get_recent_messages(chat_id, limit=8)
    started_from_escalation = session.get("phase_current") == "fase_7_escalado"
    # Fase de entrada del turno, para que el observador de la FSM (3.2) detecte saltos.
    _turn_prev_phase.set(session.get("phase_current", "") or "")

    # Cliente final/particular ya identificado: A3 no le presta servicio y el
    # agente deja de responder (sin saludo, sin procesar el turno).
    # Barrido oportunista de pedidos abandonados (decisión 011). Va acá porque es el
    # único punto que se ejecuta seguro con tráfico; se autolimita a una vez cada 10 min.
    if PEDIDOS_ENABLED:
        _sweep_stale_pedidos()

    prev_fields = session.get("captured_fields") or {}
    if prev_fields.get("_blocked"):
        return None

    # ERR-088: el escalado por "no encuentro tu registro" SÍ se puede deshacer, pero solo
    # con un identificador que exista en la base. Cualquier otro mensaje mantiene el
    # silencio, para no pisar al humano que ya tomó la conversación tras el handoff.
    if prev_fields.get("_escalated_unfound_client"):
        if not _reidentifies_after_escalation(user_message):
            return None
        reopened = {k: v for k, v in prev_fields.items()
                    if k not in ("_escalated_unfound_client", "_handoff_announced")}
        reopened.pop("_client_not_found", None)
        reopened.pop("_asked_if_new_client", None)
        session["captured_fields"] = reopened

    # Primer mensaje: saludo exacto, sin llamar al AI
    if len(history) == 0:
        db.save_message(chat_id, user_message, "user")
        db.save_message(chat_id, WELCOME_MESSAGE, "bot")
        return WELCOME_MESSAGE

    # Despedida después de fase terminal: cerrar sin llamar al AI.
    # Con un PEDIDO abierto este atajo CEDE: el pedido todavía no se cobró ni se facturó, y
    # el cliente puede decir que terminó de mil formas ("listo", "terminala", "ya está", "no
    # va más") que ninguna lista de palabras cubre. El turno pasa al modelo y lo resuelve
    # `_enforce_open_pedido_close` con la señal de intención (decisión 011).
    _pedido_abierto = PEDIDOS_ENABLED and (session.get("captured_fields") or {}).get("_pedido_id")
    # CIERRE DETERMINÍSTICO del pedido (QA de estrés 2026-08-15): con el pedido abierto, la
    # orden actual YA registrada y la forma de pago en el mensaje, se cierra ACÁ, sin pasar
    # por el modelo ni el pipeline. En el estrés, "Contraentrega." en ese estado terminaba en
    # "¿Qué análisis o perfil desean?" — el modelo re-emitía nulls y algún empuje pisaba el
    # cierre. El pago dicho con la orden cerrada no tiene otra lectura posible.
    _campos_pedido = session.get("captured_fields") or {}
    if (_pedido_abierto and _campos_pedido.get("_order_registered")
            and _payment_method_from_text(user_message)):
        db.save_message(chat_id, user_message, "user")
        _cierre = _close_pedido_turn(session, dict(_campos_pedido),
                                     _payment_method_from_text(user_message))
        return _persist_turn(chat_id, user_message, _cierre)
    if session.get("phase_current") in TERMINAL_PHASES and _is_farewell(user_message) and not _pedido_abierto:
        db.save_message(chat_id, user_message, "user")
        db.save_message(chat_id, FAREWELL_REPLY, "bot")
        return FAREWELL_REPLY

    if session.get("phase_current") in TERMINAL_PHASES and _is_greeting_only(user_message):
        db.save_message(chat_id, user_message, "user")
        db.save_message(chat_id, POST_TERMINAL_GREETING_REPLY, "bot")
        return POST_TERMINAL_GREETING_REPLY

    # Consulta del número de orden: responder con el dato real de la BD, nunca inventarlo
    if _is_order_number_query(user_message):
        db.save_message(chat_id, user_message, "user")
        if session.get("client_id"):
            order = db.get_last_order_for_client(session["client_id"])
            reply = _order_number_reply(order)
        else:
            reply = ORDER_NUMBER_NEEDS_CLIENT_MESSAGE
        db.save_message(chat_id, reply, "bot")
        return reply

    prev_captured = session.get("captured_fields") or {}
    pending = prev_captured.get("_pending_intents", [])

    if not session.get("client_id") and _is_final_user_text(user_message):
        fields = dict(prev_captured)
        fields["_blocked"] = True
        return _persist_turn(chat_id, user_message, _unsupported_final_user_response(fields))

    if session.get("intent_current") == "route_scheduling" and _looks_off_topic_smalltalk(user_message):
        response = _active_route_smalltalk_response(session, dict(prev_captured))
        if response:
            return _persist_turn(chat_id, user_message, response)

    # Opción 2 del menú (consultar resultados): aún no se resuelve por este medio.
    # Se intercepta acá para no arrastrar el flujo de programación de recogida.
    if _is_results_choice(user_message) and _menu_choice_context(session, history, prev_captured):
        return _persist_turn(
            chat_id, user_message,
            _results_pending_response(dict(prev_captured), prev_captured.get("_pending_intents")),
        )

    # Opción 4 del menú: derivar de forma determinística en vez de dejar que el
    # flujo dominante de recogida absorba el mensaje.
    if _is_other_choice(user_message) and _menu_choice_context(session, history, prev_captured):
        ai_response = _unknown_handoff_response(dict(prev_captured))
        ai_response = _finalize_request(
            chat_id,
            session,
            ai_response,
            started_from_escalation,
            session.get("phase_current", ""),
        )
        return _persist_turn(chat_id, user_message, ai_response)

    # El usuario se confundió de opción mientras se le pedía el NIT/nombre: no tratar
    # su mensaje como identificador; reconducir al menú con calidez.
    if (
        not session.get("client_id")
        and _awaiting_client_identifier(history)
        and _wants_to_reconsider_option(user_message)
    ):
        return _persist_turn(chat_id, user_message, _option_reconsider_response(dict(prev_captured)))

    if (
        not session.get("client_id")
        and prev_captured.get("_client_match_options")
        and set(_tokenize(user_message)) & {"dije", "dicho"}
    ):
        query = prev_captured.get("_client_match_query") or prev_captured.get("clinic_name")
        reply = "Sí, lo tengo. " + _client_match_options_reply(query, prev_captured.get("_client_match_options") or [])
        return _persist_turn(chat_id, user_message, _base_route_response(reply, dict(prev_captured)))

    # Reorden 3.3 (C3): el atajo pre-LLM de "no estoy registrado" se DEGRADÓ — el turno
    # llega al modelo y el handler post-modelo escala señal-primero
    # (new_or_unregistered_client OR _claims_unregistered_client, paridad completa con
    # guards de lista de coincidencias). La protección ERR-037 queda como BYPASS abajo:
    # el atajo de servicio no intercepta a quien declara no estar registrado.

    if (
        not session.get("client_id")
        and not any(prev_captured.get(k) for k in ("clinic_name", "tax_id", "_client_match_options"))
        and not (_has_client_marker(user_message) or _extract_tax_id_candidate(user_message, allow_unlabeled=True))
        # Si ya pedimos el NIT/nombre, lo que diga el usuario es su identificación: que el
        # LLM lea el mensaje COMPLETO (no que un token suelto como "Colombia" lo desvíe a
        # una respuesta de cortesía). El atajo de servicio solo aplica al contacto inicial.
        and not _awaiting_client_identifier(history)
        # ERR-037 (bypass del reorden C3): "no estamos registrados, ¿recogen muestras?"
        # NO se responde con la frase del motorizado — va al modelo para que el handler
        # de cliente nuevo escale a recepción (regla de negocio invariante).
        and not _claims_unregistered_client(user_message)
    ):
        info_response = _pre_identification_service_info_response(user_message, dict(prev_captured))
        if info_response:
            if not info_response.pop("_skip_resume", False):
                info_response = _resume_route_after_lateral_turn(session, info_response)
            return _persist_turn(chat_id, user_message, info_response)

    if session.get("intent_current") == "route_scheduling" and (session.get("client_id") or prev_captured.get("_client_found")):
        # Precio REAL del catálogo primero: un análisis puntual, el total de los elegidos o
        # el perfil ya seleccionado. Va antes de la respuesta genérica ("depende del análisis")
        # para que "¿cuánto sale el hemograma?" o "¿cuánto serían todos?" se respondan con valor.
        # Si el mensaje ADEMÁS pide/ordena los análisis ("quiero X y Y, ¿cuánto el total?"),
        # NO es solo una consulta: el pipeline captura la selección y el total sale del
        # cálculo estructurado (QA-6: la respuesta de precio se tragaba la elección).
        price_fields = dict(prev_captured)
        price_answer = _catalog_price_answer(price_fields, user_message)
        if (price_answer and not _payment_method_from_text(user_message)
                and not _expresses_order_request(user_message)):
            response = _base_route_response(price_answer, price_fields)
            response["message_mode"] = "side_question"
            response = _resume_route_after_lateral_turn(session, response)
            return _persist_turn(chat_id, user_message, response)
        operational_answer = _operational_side_question_answer(user_message)
        if operational_answer and not _payment_method_from_text(user_message):
            response = _base_route_response(operational_answer, dict(prev_captured))
            response["message_mode"] = "side_question"
            response = _resume_route_after_lateral_turn(session, response)
            return _persist_turn(chat_id, user_message, response)
        # Con el reofrecimiento de datos estables pendiente, la respuesta del cliente es
        # sobre ESOS datos, no una pregunta de catálogo. "Todo igual menos el TIPO de
        # ANÁLISIS" caía acá por las palabras "tipo" + "análisis" y se le contestaba con el
        # muestrario general, sin limpiar el perfil de la orden anterior; ese perfil heredado
        # después apagaba los cuatro enforcers que debían ofrecer el menú (prueba real, chat 4).
        if _is_catalog_overview_question(user_message) and not prev_captured.get("_stable_confirm_pending"):
            fields = dict(prev_captured)
            analysis_in_progress = bool(
                fields.get("_selected_profile_code") or _as_text_items(fields.get("selected_tests"))
            )
            # Con un análisis/perfil en curso, una pregunta de catálogo NUNCA pisa la
            # orden: el menú queda marcado para AGREGAR (chat 4: el muestrario general
            # borraba selected_tests y el agregado se perdía del total).
            if analysis_in_progress:
                area_resp = _area_options_for_profile_addition(fields, user_message)
                if area_resp:
                    return _persist_turn(chat_id, user_message, area_resp)
                choices = _catalog_overview_choices(db.list_catalog_tests(limit=500))
                if choices:
                    _store_test_menu_options(fields, choices)
                    fields["_test_menu_adds_to_profile"] = True
                    return _persist_turn(
                        chat_id, user_message,
                        _base_route_response(_test_catalog_overview_reply(choices), fields),
                    )
                return _persist_turn(
                    chat_id, user_message,
                    _base_route_response(_test_catalog_overview_reply([]), fields),
                )
            # Área específica nombrada ('¿qué análisis de orina hacen?') → opciones de
            # ESA área, no el muestrario general de todas las áreas.
            area, area_tests = db.find_tests_by_area(user_message, fields.get("species"), limit=10)
            if area and area_tests:
                return _persist_turn(
                    chat_id, user_message,
                    _test_options_response(fields, area_tests, _test_area_suggestion_reply(area, area_tests)),
                )
            return _persist_turn(chat_id, user_message, _catalog_overview_response(fields))

    # Reorden 3.3 (C2): el atajo pre-LLM de cambio de cliente/sede por tokens se DEGRADÓ —
    # el turno llega al modelo y el handler post-modelo actúa señal-primero (change_client)
    # con los mismos tokens de red y guards. La protección contra la selección espuria por
    # menú pegado vive ahora en el handler: la acción parte de prev_captured con menús
    # limpios, así lo que el modelo 'capture' inducido por el menú no sobrevive al turno.

    # Selección de un perfil de la lista recomendada ('no sé / qué me recomiendas'): el
    # cliente elige por número, ordinal, código o nombre. Se captura el perfil REAL con su
    # código y precio (para que el resumen muestre el valor), sin depender del modelo.
    if prev_captured.get("_profile_menu_options"):
        chosen_profiles = _select_profiles_from_menu(user_message, prev_captured["_profile_menu_options"])
        if chosen_profiles:
            # ERR-077: puede elegir VARIOS ("1, 3 y 6"). El primero es el perfil base y los
            # demás se registran como adicionales, con su precio, en el mismo turno.
            return _persist_turn(
                chat_id, user_message,
                _capture_profile_menu_selection(
                    session, prev_captured, chosen_profiles[0], user_message,
                    extra_profiles=chosen_profiles[1:],
                ),
            )
        # Sin selección clara: seguir el pipeline normal (puede haber preguntado otra cosa).

    # Selección de análisis de la lista mostrada: si el bot ofreció opciones de análisis
    # y el cliente elige ('el primero', 'el 2', '1601', 'parcial de orina'), capturar el
    # análisis REAL del catálogo de forma determinística, sin depender del modelo (que
    # entraba en bucle y terminaba guardando el texto genérico, ej. "Orina").
    if prev_captured.get("_test_menu_options"):
        _selected_tests = _select_tests_from_menu(user_message, prev_captured["_test_menu_options"])
        if _selected_tests:
            # Menú mostrado para AGREGAR a un perfil base ('qué análisis de orina tienen'
            # durante el ajuste): sumar al perfil, no reemplazarlo.
            if prev_captured.get("_test_menu_adds_to_profile"):
                return _persist_turn(
                    chat_id, user_message,
                    _capture_menu_addition_to_profile(session, prev_captured, _selected_tests),
                )
            return _persist_turn(
                chat_id, user_message,
                _capture_test_menu_selection(session, prev_captured, _selected_tests),
            )
        # Sin selección clara: si el mensaje es largo o abre otra orden, no es una selección
        # del menú — quedó obsoleto y se descarta para que un número incidental ('2 años') no
        # elija una opción vieja (QA extremo: menú de coagulación pegado agregaba PTT).
        if len(_tokenize(user_message)) > 6 or _wants_another_service_order(user_message):
            prev_captured.pop("_test_menu_options", None)
            prev_captured.pop("_test_menu_adds_to_profile", None)
        # (preguntó otra cosa): seguir el pipeline normal.

    # Respuesta a la oferta '¿agregar otro análisis/perfil o seguimos con el pago?' (Parte B):
    # se repite tras cada agregado hasta que el cliente decida seguir. Determinístico para no
    # caer en el bucle histórico (RESUELTO-017).
    if prev_captured.get("_offering_extra_analysis") and not prev_captured.get("payment_method"):
        extra_resp = _handle_extra_analysis_answer(session, prev_captured, user_message)
        if extra_resp is not None:
            return _persist_turn(chat_id, user_message, extra_resp)
        # extra_resp None: el cliente dio el método de pago -> seguir el pipeline normal.

    # Pedido de recomendación de análisis ('no sé / qué me recomiendas') en cualquier punto
    # de una ruta con especie ya conocida. Va ANTES de los detectores de corrección, que
    # confundían 'no sé... perro' con una corrección del paciente ('no' = corregir, 'perro'
    # = paciente) y borraban el paciente en vez de recomendar. Limpia el análisis previo
    # (clave en multiorden: no arrastrar un perfil de otra especie) y ofrece perfiles de la
    # especie. No aplica a un ajuste PARCIAL ('el mismo pero sin X').
    if (session.get("intent_current") == "route_scheduling"
            and (session.get("client_id") or prev_captured.get("_client_found"))
            and prev_captured.get("species")
            and not prev_captured.get("_profile_menu_options")
            and not _wants_partial_analysis_change(user_message)
            and (_wants_profile_recommendation(user_message)
                 or (_doesnt_know_what_to_ask(user_message)
                     and _detect_which_field_is_being_asked(history) == "exam_type"))):
        # Si nombró una categoría del catálogo (ej. 'recomiéndame un prequirúrgico'),
        # ofrecer los perfiles armados de ESA categoría, no la lista genérica (ERR-045).
        category_response = _category_profiles_menu_response(prev_captured, user_message)
        if category_response:
            return _persist_turn(chat_id, user_message, category_response)
        rec_profiles = db.list_catalog_profiles_for_species(prev_captured.get("species"), limit=6)
        if rec_profiles:
            _clear_field_for_correction(prev_captured, "exam_type")
            _store_profile_menu_options(prev_captured, rec_profiles)
            return _persist_turn(
                chat_id, user_message,
                _base_route_response(
                    _format_profile_recommendation(prev_captured.get("species"), rec_profiles,
                                                   prev_captured.get("_client_favorite_profiles")),
                    prev_captured,
                ),
            )

    diagnostic_profile_response = _diagnostic_label_profile_turn(session, prev_captured, user_message)
    if diagnostic_profile_response:
        return _persist_turn(chat_id, user_message, diagnostic_profile_response)

    # Confirmación en bloque de datos estables al iniciar una orden de seguimiento.
    # Se reofrecieron médico/dirección/pago de la orden anterior: el usuario confirma
    # o pide cambiar uno. Determinístico, sin llamar al AI.
    if prev_captured.get("_stable_confirm_pending"):
        prev_captured.pop("_stable_confirm_pending", None)
        # Cambio de cliente: la orden es para OTRA veterinaria. Descartar la
        # identificación anterior y volver a verificar contra el registro.
        if _wants_to_change_client(user_message):
            return _persist_turn(
                chat_id, user_message,
                _restart_identification_for_new_client(chat_id, session, prev_captured),
            )
        # Cambio TOTAL de análisis ('otro análisis', 'cambiemos el perfil', 'analisis quiero
        # el 653'): limpiar el PAQUETE reofrecido de la orden anterior —exam_type, perfil y
        # sus AGREGADOS— y dejar que el flujo capture el nuevo. El ajuste PARCIAL ('el mismo
        # pero sin X') NO entra acá: lo maneja la personalización del perfil base.
        #
        # `_replaces_offered_analysis` decide con lo que el sistema ya sabe (el campo al que
        # apunta el mensaje o un CÓDIGO distinto del heredado), no con verbos: con "analisis
        # quiero el 653" ningún detector de verbos disparaba, el enforcer fijaba el 653 como
        # base y los agregados de la orden ANTERIOR sobrevivían — la orden salió $24.000 más
        # cara con análisis que el cliente nunca pidió en ella (prueba en vivo 2026-08-14).
        if (_wants_to_change_analysis(user_message)
                or _replaces_offered_analysis(user_message, prev_captured.get("_selected_profile_code"))):
            _clear_field_for_correction(prev_captured, "exam_type")
            # No retornamos: el resto del mensaje puede traer datos del paciente; el flujo
            # sigue capturando y, al llegar al análisis vacío, recomienda o pregunta.
        if _is_correction_request(user_message) or _is_negative_text(user_message):
            field = _detect_correction_field(user_message)
            # ERR-099: cambiar de cliente NO es editar un texto. Re-abre la identificación
            # contra la base para que el NIT, la dirección y el motorizado se re-resuelvan.
            if field == "clinic_name":
                return _persist_turn(
                    chat_id, user_message,
                    _restart_identification_for_new_client(chat_id, session, prev_captured),
                )
            if field:
                _clear_field_for_correction(prev_captured, field)
                return _persist_turn(
                    chat_id, user_message,
                    _base_route_response(_missing_route_field_question(field), prev_captured),
                )
            return _persist_turn(
                chat_id, user_message,
                _base_route_response(
                    "Claro, ¿qué dato quieres cambiar: el médico, la dirección o la forma de pago?",
                    prev_captured,
                ),
            )
        # Confirmación PELADA: el único caso inequívoco, y el único que este atajo responde
        # con plantilla. Si el mensaje trae algo MÁS que el "sí", no se decide acá.
        #
        # Este bloque es determinístico y corre ANTES del modelo, así que solo ve palabras
        # sueltas: con "Si análisis quiero perfil 653" se quedaba con el "Si" inicial, contestaba
        # la plantilla y tiraba el resto de la oración — el 653 se perdía y la orden seguía con
        # el perfil HEREDADO que el cliente acababa de pedir cambiar (plata mal cobrada).
        # Pedido del usuario (2026-08-14): "no tiene que entender una palabra puntual, tiene que
        # entender el contexto de toda la oración". Un mensaje compuesto es justamente lo que el
        # modelo sabe leer y este atajo no: se le cede el turno y los enforcers de catálogo
        # resuelven el código contra el catálogo real, igual que en cualquier otra vía.
        if _is_bare_confirmation(user_message):
            missing = _missing_route_field(session, prev_captured)
            question = _missing_route_field_question(missing) if missing else "¿Qué análisis o perfil desean?"
            guide = "Listo. Para esta orden cambia normalmente el paciente, el propietario y el análisis. "
            return _persist_turn(chat_id, user_message, _base_route_response(guide + question, prev_captured))
        # (Un "Sí, análisis quiero el 653" —confirma Y pide otro análisis— ya soltó el paquete
        # heredado en el chequeo de arriba: `_replaces_offered_analysis` cubre ese caso.)
        # Respuesta con datos del paciente u otra cosa: seguir el pipeline normal
        # (los datos estables ya están cargados y se conservan al fusionar).

    # "el de siempre" / "el mismo" para un campo del que NO hay dato recordado: pedirlo
    # normal, en vez de que el modelo reofrezca otro dato disponible (p. ej. la dirección).
    if (
        session.get("intent_current") == "route_scheduling"
        and session.get("phase_current") not in TERMINAL_PHASES
        and (session.get("client_id") or prev_captured.get("_client_found"))
        and _is_same_as_previous(user_message)
        # 'Antes quiero cambiar el cliente' matchea _is_same_as_previous por la palabra
        # 'antes' (= 'el de antes'), pero es un CAMBIO DE CLIENTE, no un 'el de siempre'.
        # Al degradar el atajo pre-LLM de cambio de cliente (reorden C2), este bloque quedó
        # expuesto a esos mensajes: ceder para que la señal del modelo mande (ERR-072).
        and not _wants_to_change_client(user_message)
        # Solo para un "el de siempre / el mismo" CORTO: si la frase es larga, puede traer
        # el dato concreto (ej. "...soy el Dr. Gastón") — dejar que el LLM y los fallbacks lo
        # capturen en vez de cortar acá y repreguntar.
        and len(_tokenize(user_message)) <= 6
    ):
        asked = _detect_which_field_is_being_asked(history)
        mem = prev_captured.get("_client_memory") or {}
        snap = prev_captured.get("_prev_order_snapshot") or {}
        if asked and not mem.get(asked) and not snap.get(asked):
            ai_response = _base_route_response(_missing_route_field_question(asked), dict(prev_captured))
            return _persist_turn(chat_id, user_message, ai_response)

    # Flujo B — captura de datos del cliente nuevo en curso (Sección 9).
    # Compatibilidad: sesiones viejas con el flujo B de cliente nuevo (removido).
    # Se limpian sus marcas y se sigue el flujo normal, que escala si no está registrado.
    if prev_captured.get("_nc_capturing"):
        for key in [k for k in list(prev_captured) if k.startswith("_nc_")]:
            prev_captured.pop(key, None)

    # Confirmación editable de la orden (Sección 7.1): si el usuario pide corregir,
    # se limpia ese campo y se repregunta, sin volver a llamar al AI. La respuesta
    # afirmativa sigue el pipeline normal (el cierre lo permite _enforce_confirmation_step).
    if (session.get("phase_current") == CONFIRMATION_PHASE
            and session.get("intent_current") == "route_scheduling"
            and _wants_to_change_client(user_message)):
        return _persist_turn(
            chat_id, user_message,
            _restart_identification_for_new_client(chat_id, session, prev_captured),
        )

    if (session.get("phase_current") == CONFIRMATION_PHASE
            and session.get("intent_current") == "route_scheduling"
            and (_is_correction_request(user_message) or _wants_to_change_analysis(user_message))
            # Si el mensaje trae CÓDIGOS del catálogo ("No, para P2 cargá los códigos 1101 y
            # 1701"), este bloque determinístico no puede resolverlos y lo tragaba con la
            # repregunta genérica "¿Qué dato quieres corregir?" (QA de estrés 2026-08-15,
            # masivo_5 — de ahí cascadeó contaminación cruzada). Con códigos, el turno pasa
            # al modelo y los carriles de catálogo los resuelven contra la base.
            and not _profile_codes_from_text(user_message)):
        field = _detect_correction_field(user_message)
        # ERR-099: en el resumen, "quiero cambiar el cliente / soy Animal Pets" reescribía
        # solo clinic_name y dejaba client_id, tax_id, pickup_address y motorizado del
        # cliente anterior — la orden se facturaba a uno y el retiro iba a la puerta de otro.
        # La identidad se re-verifica contra la base; el resto de la orden se conserva.
        if field == "clinic_name":
            return _persist_turn(
                chat_id, user_message,
                _restart_identification_for_new_client(chat_id, session, prev_captured),
            )
        if field:
            _clear_field_for_correction(prev_captured, field)
            correction_value = _extract_correction_value(field, user_message)
            if correction_value:
                prev_captured[field] = correction_value
                ai_response = _base_route_response(
                    _route_confirmation_summary(prev_captured) or _missing_route_field_question(field),
                    prev_captured,
                )
            else:
                ai_response = _base_route_response(_missing_route_field_question(field), prev_captured)
        elif (_removes_the_additions(user_message)
                and prev_captured.get("_selected_profile_code")
                and _as_text_items(prev_captured.get("selected_tests"))):
            # "En esta orden no quiero los agregados": el cliente cita el RÓTULO que el bot
            # imprime en el resumen. Se quitan los agregados (el perfil base queda) y se
            # re-muestra el resumen con el total recalculado. Antes caía en la repregunta
            # genérica "¿Qué dato quieres corregir?" (prueba en vivo 2026-08-14). Solo dispara
            # si HAY agregados: sin ellos, la frase es ambigua y sigue la repregunta de abajo.
            prev_captured["selected_tests"] = None
            summary = _route_confirmation_summary(prev_captured)
            ai_response = _base_route_response(
                f"Listo, quito los agregados.\n{summary}" if summary else CORRECTION_PROMPT,
                prev_captured,
            )
        else:
            ai_response = _base_route_response(CORRECTION_PROMPT, prev_captured)
        # Mientras se edita el resumen seguimos en la fase de confirmación, para que el
        # "sí" posterior cierre por el camino determinístico (que exige previous_phase
        # == CONFIRMATION_PHASE). _base_route_response deja fase_2 y rompía el cierre.
        ai_response["phase"] = CONFIRMATION_PHASE
        # Marca que estamos editando el resumen: cuando el dato corregido llegue y la
        # orden vuelva a estar completa, se re-muestra el resumen antes del "sí".
        ai_response["captured_fields"]["_correction_pending"] = True
        return _persist_turn(chat_id, user_message, ai_response)

    if session.get("phase_current") in TERMINAL_PHASES and session.get("intent_current") == "route_scheduling":
        # Con un PEDIDO abierto, un mensaje que trae la forma de pago NO es una pregunta
        # lateral aunque la mencione: "les pagamos cuando pasen a recoger" describe CUÁNDO
        # paga, no pregunta el horario. Este atajo lo leía como consulta de logística y
        # respondía sobre la hora, dejando el pedido sin cobrar (QA de pago 6/7).
        if not (_pedido_abierto and _payment_method_from_text(user_message)):
            operational_answer = _operational_side_question_answer(user_message)
        else:
            operational_answer = None
        if operational_answer:
            ai_response = _base_route_response(f"{operational_answer}\n\n{CLOSING_PROMPT}", dict(prev_captured))
            ai_response["phase"] = session.get("phase_current")
            ai_response["message_mode"] = "side_question"
            return _persist_turn(chat_id, user_message, ai_response)

        # Con un PEDIDO abierto este atajo CEDE. Decide por lista de palabras y responde
        # "quedamos atentos" sin que el modelo vea el turno: con pedidos eso deja el pedido
        # abierto y SIN FACTURAR justo cuando el cliente dijo que terminó. Medido: era la
        # causa de 6 de los 10 fallos del QA semántico de cierre (decisión 011).
        close_words = {"cierra", "cerrar", "cerramos", "cierralo", "ciérralo", "cerrada", "cerrado"}
        if not _pedido_abierto and not _explicitly_wants_another_order(user_message) and (
            _is_order_confirmation(user_message) or set(_tokenize(user_message)) & close_words
        ):
            if _is_affirmative_text(user_message):
                reply = "Perfecto, quedamos atentos. Si necesitas otra orden, dime 'otra orden para otro paciente'."
            else:
                reply = "La orden ya quedó registrada. Si necesitas otra orden, dime 'otra orden para otro paciente'."
            ai_response = _base_route_response(reply, dict(prev_captured))
            ai_response["phase"] = session.get("phase_current")
            return _persist_turn(chat_id, user_message, ai_response)

        if _wants_another_service_order(user_message):
            if _wants_to_change_client(user_message):
                return _persist_turn(
                    chat_id, user_message,
                    _restart_identification_for_new_client(chat_id, session, prev_captured),
                )
            return _persist_turn(chat_id, user_message, _begin_followup_order(prev_captured, user_message))
        # Con un PEDIDO abierto, un "no, nada más" NO es una despedida: es el cliente
        # diciendo que terminó de cargar órdenes, o sea el momento exacto de cobrar. Este
        # atajo cede y el turno sigue al modelo (decisión 011).
        if _is_negative_text(user_message) and not _pedido_abierto:
            db.save_message(chat_id, user_message, "user")
            db.save_message(chat_id, FAREWELL_REPLY, "bot")
            return FAREWELL_REPLY
        tokens = set(_tokenize(user_message))
        if tokens & {"reptil", "reptiles"} or (tokens & {"hacen", "atienden"} and tokens & _ANALYSIS_TOKENS):
            return _persist_turn(chat_id, user_message, _unknown_handoff_response(dict(prev_captured)))

    # Reorden 3.3 (C1): el atajo pre-LLM de "otra orden" por tokens se DEGRADÓ — el turno
    # llega al modelo y el handler post-modelo actúa señal-primero (another_order) con los
    # mismos tokens de red y guards. El manejo DENTRO de fase terminal (bloque de arriba)
    # no cambia: es parte del cierre aprobado.

    if session.get("client_id") and prev_captured.get("_client_not_found"):
        db.clear_client_from_session(chat_id)
        session["client_id"] = None

    if session.get("client_id") and prev_captured and not prev_captured.get("_client_found"):
        client = db.get_client_by_id(session["client_id"])
        if client:
            _store_client_context(prev_captured, client)
            session["captured_fields"] = prev_captured

    # Nueva orden en misma sesión: fase terminal + no es despedida -> limpiar datos de la orden anterior
    just_closed_order = False
    if session.get("phase_current") in TERMINAL_PHASES:
        _prev_snapshot = {k: v for k, v in prev_captured.items() if k in _ROUTE_REQUIRED_FIELDS and v}
        _reset_order_fields(prev_captured)
        prev_captured["_prev_order_snapshot"] = _prev_snapshot
        session["phase_current"] = "fase_1_clasificacion"
        session["intent_current"] = "unknown"
        pending = []
        # El usuario no se despidió ni pidió explícitamente otra orden: si su mensaje es
        # una consulta que no encaja en los 4 servicios, NO debemos reabrir el flujo de
        # orden (arrastraba "¿Cuál es el médico solicitante?"). Se marca para derivar
        # tras conocer la señal del modelo.
        just_closed_order = True

    consecutive_aff = _consecutive_affirmatives(history)
    if consecutive_aff >= 2:
        session["_force_close_hint"] = (
            f"ALERTA DE BUCLE: el usuario lleva {consecutive_aff} respuestas afirmativas seguidas. "
            "Ya tienes los datos necesarios. Cierra el flujo ahora con fase_6_cierre. No hagas más preguntas."
        )

    # Inyectar catálogo cuando se está eligiendo el tipo de análisis
    catalog_ctx = None
    prev_intent = session.get("intent_current", "")
    prev_fields = session.get("captured_fields") or {}
    selected = prev_fields.get("selected_tests")
    removed = prev_fields.get("removed_tests")
    # El perfil sigue "en construcción" solo si aún no hay exam_type cerrado, o si se
    # está personalizando activamente un perfil base. Una vez que exam_type queda fijado
    # el perfil está cerrado: hay que avanzar a paciente/médico, no seguir pidiendo análisis.
    building_profile = (selected is not None or removed is not None) and (
        not prev_fields.get("exam_type") or prev_fields.get("_profile_customizing")
    )
    if prev_intent == "route_scheduling":
        if building_profile:
            # Modo perfil personalizado: catálogo de análisis individuales + resumen calculado
            catalog_ctx = db.get_individual_tests_context(prev_fields.get("species"))
            if prev_fields.get("_selected_profile_code"):
                added_rows = db.get_tests_by_codes_or_names(selected or [])
                removed_rows = db.get_tests_by_codes_or_names(removed or [])
                base_price = int(prev_fields.get("_selected_profile_price") or 0)
                totals = calculate_profile_adjusted_total(
                    base_price,
                    [r["price"] for r in added_rows],
                    [r["price"] for r in removed_rows],
                )
                session["_custom_profile_summary"] = (
                    f"PERFIL BASE EN PERSONALIZACIÓN: {prev_fields.get('_selected_profile_name')}. "
                    f"Base {_money(totals['base'])}. "
                    f"Agregados: {_format_test_items(added_rows)}. "
                    f"Quitados: {_format_test_items(removed_rows)}. "
                    f"Total {_money(totals['total'])}."
                )
            elif selected:
                added_rows = db.get_tests_by_codes(selected)
                totals = calculate_custom_profile_total(added_rows)
                session["_custom_profile_summary"] = (
                    f"PERFIL PERSONALIZADO EN CONSTRUCCIÓN ({totals['count']} análisis): {_format_test_items(added_rows)}. "
                    f"Subtotal {_money(totals['subtotal'])}. Total {_money(totals['total'])}."
                )
        elif not prev_fields.get("exam_type"):
            catalog_ctx = db.get_catalog_context(prev_fields.get("species"))
            # Los ANÁLISIS sueltos también, no solo los perfiles: este es el momento en que el
            # cliente pide el análisis, y sin ellos el modelo negaba códigos que SÍ existen
            # ("el 2019" → "no tengo registrado el 2019"; el 2019 es Parvovirus Canino Vcheck).
            # Medido con qa_cobertura_catalogo.py: 4 de 4 códigos de análisis negados. No era
            # un problema de especie — uno de los negados estaba etiquetado 'ambos'.
            tests_ctx = db.get_individual_tests_context(prev_fields.get("species"))
            if tests_ctx:
                catalog_ctx = f"{catalog_ctx}\n\n{tests_ctx}" if catalog_ctx else tests_ctx
            labels = db.list_diagnostic_labels()
            if labels:
                catalog_ctx = (catalog_ctx or "") + (
                    "\nPerfiles sugeridos por necesidad diagnóstica (etiquetas): " + ", ".join(labels)
                )

    if (
        session.get("intent_current") == "route_scheduling"
        and (prev_captured.get("_prev_order_snapshot") or prev_captured.get("_client_memory"))
        and session.get("phase_current") not in TERMINAL_PHASES
    ):
        same_resolution = _resolve_same_as_previous(prev_captured, user_message, history)
        if same_resolution:
            fields = dict(prev_captured)
            fields[same_resolution["field"]] = same_resolution["value"]
            if "_prev_order_snapshot" not in fields and prev_captured.get("_prev_order_snapshot"):
                fields["_prev_order_snapshot"] = prev_captured["_prev_order_snapshot"]
            # "El mismo / esa misma" cuando hay dirección registrada o recordada CONFIRMA la
            # dirección de retiro. Sin esto, la bandera _address_confirmation_pending quedaba
            # pegada y el bot volvía a pedir la dirección turnos después (RESUELTO-010).
            if fields.get("pickup_address") and fields.get("_address_confirmation_pending"):
                fields["_address_confirmation_pending"] = False
                fields["_address_confirmed"] = True
            ai_response = _base_route_response(same_resolution["reply"], fields)
            ai_response["captured_fields"] = fields
            return _persist_turn(chat_id, user_message, ai_response)

    # Memoria: solo reofrecer el dato del PRÓXIMO campo que falta, y solo si está
    # recordado. Así "el de siempre" para el médico no reofrece la dirección (#3).
    memory = prev_captured.get("_client_memory") or {}
    if memory and session.get("intent_current") == "route_scheduling":
        next_missing = _missing_route_field(session, prev_captured)
        if next_missing in _CLIENT_MEMORY_FIELDS and memory.get(next_missing):
            label = _FIELD_LABELS.get(next_missing, next_missing)
            session["_client_memory_hint"] = (
                f"DATO RECORDADO para {label}: {memory[next_missing]}. Si el usuario dice "
                f"'el de siempre', 'el mismo' o no lo recuerda, reofrécelo y pide confirmación. "
                f"Para cualquier otro campo que no tengas recordado, pídelo normal, sin reofrecer otro dato."
            )

    ai_response = ai.generate_turn(
        session=session,
        history=history,
        user_message=user_message,
        pending_intents=pending,
        catalog_context=catalog_ctx,
    )

    fields = ai_response.get("captured_fields", {})

    # Estado explícito: arrastra las flags de control del turno anterior (Fase 3.1).
    # Reemplaza la copia manual inline; el comportamiento es idéntico (ver state.carry_over).
    state.ConversationState(fields).carry_over(prev_captured)

    # CANDADO DE PROVENANCIA (ERR-114 — la lógica de estados por orden que pidió el usuario,
    # 2026-08-15): los análisis de la orden solo pueden CRECER por lo que el cliente acaba de
    # decir o elegir. El modelo re-emite los `selected_tests` de la ORDEN ANTERIOR en cada
    # turno porque los ve en el historial ("Agregados: 1405-Sodio…" en el resumen de la orden
    # 1) y por distintas vías con excepciones terminaban dentro de la orden nueva: $24.000 de
    # más en análisis nunca pedidos. Acá, en el ÚNICO punto donde entra la salida del modelo,
    # un código nuevo solo se acepta si (1) está literal en el mensaje, (2) el mensaje lo
    # NOMBRA (catalog.names_test), (3) sale del menú activo, o (4) el cliente dijo "el de
    # siempre". Lo demás se revierte en silencio. Los caminos determinísticos de más abajo
    # agregan por sus propias vías (mensaje + catálogo) y no pasan por este filtro.
    _candado_provenancia_tests(fields, prev_captured, user_message)

    # FRONTERA DE ORDEN (ERR-117): si el cliente pidió otra orden o describió un paciente
    # nuevo en bloque, el turno se resuelve acá, determinístico y FUERA del pipeline — los
    # enforcers de captura no pueden enganchar los códigos del paciente nuevo a la orden que
    # se está cerrando, ni la confirmación pisar el cierre con su resumen.
    _frontera = _order_boundary_response(session, ai_response, prev_captured, user_message)
    if _frontera is not None:
        if _frontera.get("phase") == "fase_6_cierre":
            _frontera = _apply_route_closure_summary(_frontera)
            _frontera = _finalize_request(chat_id, session, _frontera,
                                          started_from_escalation,
                                          session.get("phase_current", ""))
            _consume_boundary_next(session, _frontera)
        return _persist_turn(chat_id, user_message, _frontera)

    _merge_existing_route_fields(prev_captured, fields)
    _apply_common_order_fallbacks(fields, user_message)

    _apply_no_owner_shortcut(fields, prev_captured, user_message, history)

    signal = ai_response.get("user_intent_signal")

    # Recién cerramos una orden y el usuario hace una consulta que no encaja en los 4
    # servicios (señal off_topic/unclear) sin pedir otra orden: derivar de una a una
    # persona, en vez de reabrir el flujo y soltar "¿Cuál es el médico solicitante?".
    if (
        just_closed_order
        and signal in ("off_topic", "unclear")
        and not _explicitly_wants_another_order(user_message)
    ):
        ai_response = _unknown_handoff_response(fields)
        ai_response = _finalize_request(
            chat_id, session, ai_response, started_from_escalation, session.get("phase_current", ""),
        )
        return _persist_turn(chat_id, user_message, ai_response)

    # 3.3 — change_client SEÑAL-PRIMERO (reorden C2): el atajo pre-LLM por tokens se
    # degradó a este handler; la señal cubre todos los fraseos ("esta cuenta es de otra
    # clínica") y los tokens quedan de RED. Guards portados del atajo: confirmación y
    # terminal tienen manejo propio. La acción parte de PREV_CAPTURED con menús limpios
    # (no de fields): un menú pegado inducía al modelo a 'elegir' un perfil espurio en
    # el mismo turno del cambio (QA extremo) — nada capturado en este turno sobrevive.
    # Cambio de SEDE (misma orden, otra sucursal) mantiene paciente y análisis; cambio
    # de CLIENTE con orden en curso conserva la orden y re-verifica identidad (L50).
    # La RED de tokens de este handler NO puede pisar otra señal con handler propio ni
    # actuar recién cerrada la orden: "sangre de otro peludo DE LA CLÍNICA" post-cierre
    # matchea _wants_to_change_client (falso positivo) y robaba el turno de another_order
    # (QA real 2026-07-18). La fase de ENTRADA (_turn_prev_phase) preserva el guard del
    # atajo original: el bloque de fase terminal ya mutó session["phase_current"].
    _change_by_tokens = (
        _wants_to_change_client(user_message)
        and signal != "another_order"
        and _turn_prev_phase.get() not in TERMINAL_PHASES
    )
    if (
        (signal == "change_client" or _change_by_tokens)
        and ai_response.get("intent") == "route_scheduling"
        and not ai_response.get("requires_handoff")
        and session.get("phase_current") not in TERMINAL_PHASES
        and session.get("phase_current") != CONFIRMATION_PHASE
        and (session.get("client_id") or fields.get("_client_found"))
        and not prev_captured.get("_client_match_options")
    ):
        base_fields = dict(prev_captured)
        state.ConversationState(base_fields).clear_menus()
        # El cambio de cliente resuelve cualquier oferta/espera abierta de análisis.
        base_fields.pop("_offering_extra_analysis", None)
        base_fields.pop("_awaiting_additional_test", None)
        is_branch = bool(set(_tokenize(user_message)) & _BRANCH_NOUN_TOKENS)
        switch = _switch_branch_keep_order if is_branch else _restart_identification_for_new_client
        return _persist_turn(chat_id, user_message, switch(chat_id, session, base_fields))

    # 3.3 — another_order SEÑAL-PRIMERO (reorden C1): tras una orden registrada, cualquier
    # fraseo de "necesito otra orden" lo lee el modelo; los tokens quedan de RED para
    # cuando la señal no venga. El atajo pre-LLM por tokens se degradó a este handler
    # (guards portados: _stable_confirm_pending tiene manejo propio; la sesión
    # parcialmente reiniciada cuenta por intent_current). Misma acción determinística:
    # _begin_followup_order (nueva orden conservando cliente y datos estables).
    if (
        (signal == "another_order" or _explicitly_wants_another_order(user_message))
        and ai_response.get("intent") == "route_scheduling"
        and not ai_response.get("requires_handoff")
        and (prev_captured.get("_order_registered") or just_closed_order)
        and not prev_captured.get("_stable_confirm_pending")
        and (session.get("client_id") or fields.get("_client_found")
             or session.get("intent_current") == "route_scheduling")
    ):
        if _wants_to_change_client(user_message):
            return _persist_turn(
                chat_id, user_message,
                _restart_identification_for_new_client(chat_id, session, prev_captured),
            )
        return _persist_turn(chat_id, user_message, _begin_followup_order(prev_captured, user_message))

    # Oferta de derivación pendiente ("¿te derivo o seguimos?"): resolver según la
    # respuesta. Si acepta, derivar a una persona; si quiere seguir, limpiar el flag
    # y continuar el pipeline normal con la respuesta de la IA.
    if prev_captured.get("_handoff_offer_pending"):
        fields.pop("_handoff_offer_pending", None)
        if _accepts_handoff_offer(user_message, signal):
            ai_response = _unknown_handoff_response(fields)
            ai_response = _finalize_request(
                chat_id, session, ai_response, started_from_escalation, session.get("phase_current", ""),
            )
            return _persist_turn(chat_id, user_message, ai_response)

    # Anti-bucle: si la IA marca que no entiende / está fuera de tema varios turnos
    # seguidos, derivar a una persona en vez de seguir dando vueltas (rompe el bucle
    # pase lo que pase). Cualquier turno que SÍ encaja reinicia el contador.
    elif signal in ("unclear", "off_topic") or _repeats_last_bot_question(ai_response, history, fields):
        # Si en este turno se capturó algún dato NUEVO de la orden, hubo progreso real
        # (el cliente está dando datos del paciente aunque sea en otro orden del que pedimos):
        # NO cuenta como turno perdido. El anti-bucle solo debe disparar cuando NO hay avance,
        # para no escalar a un humano a alguien que sí está colaborando con la orden.
        progressed = sum(1 for k in _ROUTE_REQUIRED_FIELDS if fields.get(k)) > \
            sum(1 for k in _ROUTE_REQUIRED_FIELDS if prev_captured.get(k))
        if progressed:
            fields["_offtrack_count"] = 0
        else:
            offtrack = (prev_captured.get("_offtrack_count") or 0) + 1
            if offtrack >= 3:
                fields.pop("_offtrack_count", None)
                ai_response = _unknown_handoff_response(fields)
                ai_response = _finalize_request(
                    chat_id, session, ai_response, started_from_escalation, session.get("phase_current", ""),
                )
                return _persist_turn(chat_id, user_message, ai_response)
            fields["_offtrack_count"] = offtrack
    elif prev_captured.get("_offtrack_count"):
        fields["_offtrack_count"] = 0

    # Sucursal/sede nueva no registrada (en cualquier punto): en vez de cortar, OFRECER
    # derivar a un humano para registrarla o seguir con una sede ya registrada. Fuente
    # primaria: la IA (user_intent_signal=new_branch); fallback: tokens de sede + "nueva".
    if (
        not started_from_escalation
        and not prev_captured.get("_handoff_offer_pending")
        and (signal == "new_branch" or _wants_new_branch(user_message))
    ):
        fields["_handoff_offer_pending"] = "branch"
        return _persist_turn(chat_id, user_message, _base_route_response(NEW_BRANCH_OFFER_MESSAGE, fields))

    asked_field = _detect_which_field_is_being_asked(history)
    payment_answer = _payment_method_from_text(user_message)
    if (
        session.get("intent_current") == "route_scheduling"
        and payment_answer
        and asked_field != "payment_method"
    ):
        # El mismo mensaje puede resolver la confirmación de dirección pendiente
        # ("si, correcta. ... y contraentrega"): resolverla ANTES de decidir qué falta,
        # para no re-preguntar una dirección que el cliente acaba de confirmar (QA-2).
        if fields.get("_address_confirmation_pending") and _confirms_address_now(ai_response, user_message):
            fields["_address_confirmation_pending"] = False
            fields["_address_confirmed"] = True
            fields["pickup_address"] = (fields.get("pickup_address")
                                        or prev_captured.get("pickup_address")
                                        or prev_captured.get("_client_address"))
        # Este atajo es para una forma de pago SUELTA fuera de turno. Si el mensaje además
        # trae datos nuevos de la orden (datos en bloque), NO pisar la respuesta del
        # modelo: el pipeline los captura y pregunta lo que falte (QA-2).
        new_route_fields = [
            k for k in _ROUTE_REQUIRED_FIELDS
            if k != "payment_method" and fields.get(k) and not prev_captured.get(k)
        ]
        missing = _missing_route_field(session, fields)
        if missing and missing != "payment_method" and not new_route_fields:
            fields["payment_method"] = prev_captured.get("payment_method")
            return _persist_turn(
                chat_id,
                user_message,
                _base_route_response(_missing_route_field_question(missing), fields),
            )

    if (
        session.get("intent_current") == "route_scheduling"
        and asked_field == "payment_method"
        and payment_answer
    ):
        fields["payment_method"] = payment_answer
        ai_response["captured_fields"] = fields
        ai_response["intent"] = "route_scheduling"
        ai_response["service_area"] = "route_scheduling"
        ai_response["phase"] = "fase_6_cierre"
        ai_response["requires_handoff"] = payment_answer == "pago_linea"
        ai_response["handoff_area"] = "contabilidad" if payment_answer == "pago_linea" else None

    client = None
    skip_client_lookup = False
    if not session.get("client_id"):
        # El bot ya preguntó "¿eres cliente nuevo?": la siguiente respuesta es sí/no
        # a esa pregunta, no un nuevo nombre para volver a buscar. Sin esto, cualquier
        # mensaje corto ("Registrame", "Qué hacemos") se toma como veterinaria y la
        # búsqueda entra en bucle infinito de "no encuentro".
        # Si el usuario dice claramente que es nuevo/no registrado/independiente,
        # derivar AUNQUE el mensaje mencione "veterinaria" (palabra que de otro modo
        # se confunde con un identificador y mantiene el bucle de "compárteme el NIT").
        # Fuente primaria: la lectura semántica de la IA (user_intent_signal); las listas
        # de tokens quedan como red de seguridad (fallback) si la IA no clasificó.
        signal = ai_response.get("user_intent_signal")
        # PRIORIDAD: si el bot mostró una lista de coincidencias y el mensaje resuelve a
        # una de ellas (número, ordinal "la primera", o el nombre listado), eso es una
        # SELECCIÓN — no "soy cliente nuevo" ni una veterinaria nueva — aunque traiga un
        # "exacto"/"sí" de confirmación. El código ya entiende el ordinal
        # (_select_client_match); sin esta prioridad, el "exacto" disparaba el escalado a
        # cliente nuevo y "la primera" se re-buscaba como nombre (bug "exacto, es la
        # primera"). La selección en sí se resuelve más abajo con la lista aún intacta.
        picks_from_match_list = bool(
            fields.get("_client_match_options")
            and _select_client_match(user_message, fields, signal)
        )
        # Una afirmación pelada ("sí", "Si la uno") NO es "soy cliente nuevo" salvo que el
        # bot acabe de preguntarlo. Sin este contexto, una selección del menú de bienvenida
        # ("la uno" = programar) escalaba por error a recepción (L46: entender por contexto,
        # no por longitud). La mención explícita de "cliente nuevo" sí cuenta siempre.
        bot_asked_new = _asks_if_new_client(_last_bot_message(history))
        # Con una lista de coincidencias pendiente, "ninguno de esos" / "no es ninguna" significa
        # "ninguna de la lista", NO "soy cliente nuevo": no se escala todavía, se repregunta el
        # nombre exacto (abajo) y solo si no existe se ofrece el alta de cliente nuevo.
        has_pending_matches = bool(fields.get("_client_match_options"))
        says_new_client = (
            not picks_from_match_list
            and not has_pending_matches
            and (
                signal == "new_or_unregistered_client"
                or _claims_unregistered_client(user_message)
                or _explicitly_says_new_client(user_message)
                or (bot_asked_new and _confirms_new_client(user_message))
            )
        )
        gives_identifier = (
            signal == "provides_client_identifier"
            or _provides_new_identifier(user_message, prev_captured)
        )
        if says_new_client and not gives_identifier:
            fields["clinic_name"] = None
            fields["tax_id"] = None
            fields.pop("_client_found", None)
            fields.pop("_client_not_found", None)
            _clear_client_match_options(fields)
            return _escalate_new_client_turn(
                chat_id,
                session,
                user_message,
                fields,
                started_from_escalation,
                CLIENT_NEW_REGISTRATION_MESSAGE,
            )
        if (
            prev_captured.get("_client_not_found")
            and prev_captured.get("_asked_if_new_client")
            and _asks_if_new_client(_last_bot_message(history))
            and (says_new_client or not gives_identifier)
        ):
            if _is_final_user_text(user_message):
                fields["clinic_name"] = None
                fields["tax_id"] = None
                _clear_client_match_options(fields)
                fields["_blocked"] = True
                return _persist_turn(chat_id, user_message, _unsupported_final_user_response(fields))
            return _escalate_new_client_turn(chat_id, session, user_message, fields, started_from_escalation)

        # Con una selección de la lista pendiente, NO reinterpretar el mensaje como un
        # nombre/NIT nuevo: los fallbacks borrarían la lista y tomarían el ordinal como
        # nombre. La selección se resuelve intacta en el bloque _client_match_options.
        if not picks_from_match_list:
            _apply_identification_fallbacks(
                fields, user_message, history, signal, ai_response.get("message_mode")
            )
        _apply_identification_retry(fields, prev_captured, user_message, history)

        if _is_final_user_text(user_message):
            fields["clinic_name"] = None
            fields["tax_id"] = None
            _clear_client_match_options(fields)
            fields["_blocked"] = True
            ai_response = _unsupported_final_user_response(fields)
            fields = ai_response["captured_fields"]
            skip_client_lookup = True
        else:
            if (
                prev_captured.get("_client_not_found")
                and not prev_captured.get("_handoff_announced")
                and not fields.get("tax_id")
                and not fields.get("clinic_name")
            ):
                fields["_asked_if_new_client"] = True
                if says_new_client:
                    return _escalate_new_client_turn(chat_id, session, user_message, fields, started_from_escalation)
                ai_response = _base_route_response(CLIENT_IDENTIFIER_RETRY_MESSAGE, fields)
                skip_client_lookup = True

            if not skip_client_lookup and fields.get("_client_match_options"):
                previous_query = fields.get("_client_match_query")
                tax_id_now = fields.get("tax_id")
                # NIT nuevo (distinto al que generó la lista) → descartar y re-buscar.
                # Si el NIT es el mismo que generó la lista (sedes), tratar como selección.
                if tax_id_now and _compact_identifier(tax_id_now) != _compact_identifier(previous_query):
                    _clear_client_match_options(fields)
                else:
                    selected_client = _select_client_match(user_message, fields, signal)
                    current_query = fields.get("clinic_name")
                    if selected_client:
                        client = selected_client
                        fields["clinic_name"] = client.get("clinic_name") or fields.get("clinic_name")
                        fields["tax_id"] = client.get("tax_id") or fields.get("tax_id")
                        _clear_client_match_options(fields)
                    else:
                        # No eligió ninguna de la lista parcial. Se pide DE NUEVO el nombre exacto
                        # (o el NIT); en el próximo turno se busca por coincidencia EXACTA y, si no
                        # existe, se pregunta si es cliente nuevo (para escalar a recepción).
                        _clear_client_match_options(fields)
                        fields["clinic_name"] = None
                        fields["_awaiting_exact_name"] = True
                        ai_response = _base_route_response(
                            "Entiendo. ¿Me confirmas el nombre exacto de la veterinaria o médico "
                            "veterinario (o el NIT) para verificarlo en el registro?",
                            fields,
                        )
                        skip_client_lookup = True

            if not client and not skip_client_lookup:
                ai_response = _enforce_client_identification_gate(session, ai_response, history)
                fields = ai_response.get("captured_fields", fields)

    address_reask_needed = None
    if not skip_client_lookup and prev_captured.get("_address_confirmation_pending"):
        # Si el flujo ya avanzó más allá de la dirección EN TURNOS ANTERIORES, quedó
        # confirmada de hecho: bajamos el flag para no reinterpretar un "no" posterior
        # (p. ej. de observaciones) como rechazo de la dirección. Solo cuenta lo previo:
        # lo capturado en ESTE turno no da por respondida una pregunta que el bot acaba
        # de hacer (ERR-046: "quiero un análisis de orina" confirmaba la dirección sola).
        progressed = any(
            prev_captured.get(f)
            for f in ("requesting_doctor", "patient_name", "species", "exam_type")
        )
        # Un BLOQUE de datos nuevos del paciente en ESTE turno (varios campos a la vez) también
        # es avance claro: el cliente no está respondiendo la dirección, está adelantando la
        # orden ('Luna, gata, hembra, 3 años, dueña Ana, doctora Sofia'). No confundir con
        # ERR-046 (un solo dato/intención no confirma la dirección): exige 3+ campos nuevos.
        new_block = sum(
            1 for f in ("requesting_doctor", "patient_name", "species", "sex",
                        "patient_age", "owner_name", "breed")
            if fields.get(f) and fields.get(f) != prev_captured.get(f)
        )
        if new_block >= 3:
            progressed = True
        registered_address = prev_captured.get("pickup_address") or prev_captured.get("_client_address")
        if progressed and (fields.get("pickup_address") or prev_captured.get("pickup_address")):
            fields["_address_confirmation_pending"] = False
            fields["_address_confirmed"] = True
        elif _rejects_address_now(ai_response, user_message):
            fields["pickup_address"] = None
            fields["_address_confirmation_pending"] = False
            fields["_address_confirmed"] = False
            ai_response = _base_route_response(
                "¿Cuál es la dirección correcta donde debemos retirar la muestra?",
                fields,
            )
        elif _confirms_address_now(ai_response, user_message):
            fields["pickup_address"] = registered_address
            fields["_address_confirmation_pending"] = False
            fields["_address_confirmed"] = True
        elif fields.get("pickup_address") and registered_address and \
                fields.get("pickup_address") != registered_address:
            # Dio OTRA dirección en el mismo mensaje: esa es la corrección y vale
            # como confirmada.
            fields["_address_confirmation_pending"] = False
            fields["_address_confirmed"] = True
        elif registered_address:
            # Respondió otra cosa (adelantó un dato, preguntó algo): lo capturado se
            # CONSERVA y el pipeline responde a lo que dijo, pero al FINAL del turno la
            # pregunta vuelve a ser la dirección pendiente — se re-pregunta, no se asume
            # (ERR-046). La inyección ocurre tras los guardrails de análisis para que un
            # menú/sugerencia no la pise.
            fields["_address_confirmation_pending"] = True
            address_reask_needed = registered_address

    # ERR-081 (chat real 10): el bot preguntó "¿cuál es la dirección correcta?" y el cliente
    # respondió con el NOMBRE de otra sede ("Centro veterinario La Uribe"). El modelo lo
    # capturó como clinic_name, pero con client_id ya en sesión nada volvía a buscar: la
    # orden quedaba con el nombre nuevo y el client_id/dirección del cliente VIEJO
    # (identidad cruzada: retiro y facturación al cliente equivocado). En esa ventana
    # —dirección rechazada y aún sin respuesta— un nombre de veterinaria distinto se
    # re-identifica contra la base antes de seguir.
    if (not skip_client_lookup and session.get("client_id")
            and prev_captured.get("_client_found")
            and not fields.get("pickup_address") and not prev_captured.get("pickup_address")
            and fields.get("clinic_name")
            and fields.get("clinic_name") != prev_captured.get("clinic_name")):
        new_name = fields.get("clinic_name")
        if on_progress is not None:
            on_progress(CLIENT_LOOKUP_PROGRESS_MESSAGE)
        exact = db.find_client_exact(new_name)
        matches = [exact] if exact else db.find_client_matches(new_name, limit=MAX_CLIENT_MATCH_OPTIONS + 1)
        if len(matches) == 1:
            new_client = matches[0]
            db.link_client_to_session(chat_id, new_client["id"])
            session["client_id"] = new_client["id"]
            _store_client_context(fields, new_client)
            fields["clinic_name"] = new_client.get("clinic_name") or new_name
            if fields.get("_client_address"):
                # Confirmar la dirección de la sede NUEVA (mismo paso aprobado del flujo).
                fields["pickup_address"] = fields.get("_client_address")
                fields["_address_confirmation_pending"] = True
                fields["_address_confirmed"] = False
            ai_response = _base_route_response(_client_found_reply(fields), fields)
            skip_client_lookup = True
        elif matches:
            # Varias sedes posibles: se limpia la identificación y se reusa el flujo de
            # selección existente (el cliente elige y el próximo turno re-vincula).
            db.clear_client_from_session(chat_id)
            session["client_id"] = None
            has_more = len(matches) > MAX_CLIENT_MATCH_OPTIONS
            shown = matches[:MAX_CLIENT_MATCH_OPTIONS]
            _store_client_match_options(fields, new_name, shown)
            ai_response = _base_route_response(
                _client_match_options_reply(new_name, shown, has_more=has_more), fields)
            skip_client_lookup = True
        else:
            # No existe una sede con ese nombre: NO se pisa el cliente identificado; se
            # aclara y se vuelve a pedir la dirección pendiente.
            fields["clinic_name"] = prev_captured.get("clinic_name")
            ai_response = _base_route_response(
                "No encuentro una sede registrada con ese nombre. "
                "¿Me confirmas la dirección donde debemos retirar la muestra?",
                fields,
            )
            skip_client_lookup = True

    # Buscar cliente cuando el AI capturó nombre o NIT por primera vez
    client_status_changed = False
    if client and not session.get("client_id"):
        db.link_client_to_session(chat_id, client["id"])
        session["client_id"] = client["id"]
        _store_client_context(fields, client)
        client_status_changed = True
    elif not session.get("client_id") and not skip_client_lookup and (fields.get("clinic_name") or fields.get("tax_id")):
        if on_progress is not None:
            on_progress(CLIENT_LOOKUP_PROGRESS_MESSAGE)
        if fields.get("tax_id"):
            tax_matches = db.find_clients_by_tax_id(fields.get("tax_id"))
            if len(tax_matches) > 1:
                _store_client_match_options(fields, fields.get("tax_id"), tax_matches)
                ai_response = _base_route_response(
                    _client_match_options_reply(fields.get("tax_id"), tax_matches),
                    fields,
                )
                skip_client_lookup = True
            elif len(tax_matches) == 1:
                client = tax_matches[0]

        if not client and not skip_client_lookup and fields.get("clinic_name"):
            if prev_captured.get("_awaiting_exact_name"):
                # SEGUNDO intento (el cliente rechazó la lista y le repreguntamos el nombre):
                # SOLO match EXACTO. Si el nombre coincide exacto con un registrado, se identifica;
                # si no, queda como no encontrado y abajo se pregunta si es cliente nuevo. Se prueba
                # el nombre que leyó el LLM y, de refuerzo (a veces lo captura con ruido), las
                # palabras significativas del mensaje. NUNCA match parcial aquí.
                fields.pop("_awaiting_exact_name", None)
                # El nombre real suele ser una SECUENCIA de palabras envuelta en ruido
                # ('Sisi es animal Pets' → 'animal pets'): se prueban también los pares y
                # tríos consecutivos de palabras significativas, no solo tokens sueltos
                # (ERR-066: 'Animal Pets' fallaba dos veces con el nombre correcto adentro).
                sig = [t for t in _tokenize(user_message)
                       if len(t) >= 3 and t not in _EXACT_RETRY_STOPWORDS]
                ngrams = [" ".join(sig[i:j]) for i in range(len(sig))
                          for j in (i + 3, i + 2) if j <= len(sig)]
                for cand in [fields.get("clinic_name")] + ngrams + [t for t in sig if len(t) >= 4]:
                    client = db.find_client_exact(cand)
                    if client:
                        break
            else:
                # PRIMER intento. Se identifica directo SOLO si hay match EXACTO. Si las
                # coincidencias son PARCIALES (una o varias), se muestran para que el cliente
                # elija o diga que ninguna es la suya (→ posible cliente nuevo). Una coincidencia
                # parcial ÚNICA no se asume como correcta (ej. "Pets Colombia" ≠ "Vets&Pets ...").
                exact = db.find_client_exact(fields.get("clinic_name"))
                if exact:
                    client = exact
                else:
                    matches = db.find_client_matches(fields.get("clinic_name"), limit=MAX_CLIENT_MATCH_OPTIONS + 1)
                    if not matches:
                        # ERR-068 (gemelo de ERR-066, primer intento): el nombre capturado
                        # vino ENVUELTO en ruido de ráfaga ('Sisi cómo no / Animal pets') y
                        # ni el exacto ni el parcial matchean. Probar los n-gramas
                        # significativos del mensaje: exacto primero, parcial de refuerzo.
                        sig = [t for t in _tokenize(user_message)
                               if len(t) >= 3 and t not in _EXACT_RETRY_STOPWORDS]
                        for cand in [" ".join(sig[i:j]) for i in range(len(sig))
                                     for j in (i + 3, i + 2) if j <= len(sig)]:
                            exact2 = db.find_client_exact(cand)
                            if exact2:
                                client = exact2
                                break
                            m2 = db.find_client_matches(cand, limit=MAX_CLIENT_MATCH_OPTIONS + 1)
                            if m2:
                                matches = m2
                                break
                    if not client and not matches:
                        # Red SEMÁNTICA (la solución GENERAL): que la IA lea TODO el mensaje
                        # —frases, ruido, ráfagas, cualquier orden— y extraiga el nombre/NIT
                        # limpios; el código solo verifica contra la BD. Una llamada corta,
                        # solo cuando todo lo determinístico falló (patrón interpret_route_field).
                        try:
                            extracted = ai.extract_client_identifier(user_message)
                        except Exception:
                            extracted = {}
                        clean_name = (extracted.get("name") or "").strip()
                        clean_nit = (extracted.get("tax_id") or "").strip()
                        if clean_nit:
                            tax_hits = db.find_clients_by_tax_id(clean_nit)
                            if len(tax_hits) == 1:
                                client = tax_hits[0]
                        if not client and clean_name and clean_name.lower() != str(fields.get("clinic_name") or "").lower():
                            client = db.find_client_exact(clean_name)
                            if not client:
                                matches = db.find_client_matches(clean_name, limit=MAX_CLIENT_MATCH_OPTIONS + 1)
                    if not client and not matches:
                        # El cliente se identificó con el nombre del MÉDICO ("el médico es Diana
                        # Sacristán"), no con el de la veterinaria. El agente busca clínicas en
                        # `clients` y esos nombres viven en `clients_a3_professionals`, así que
                        # no se encontraban nunca aunque estuvieran cargados. Se propone su
                        # clínica para que confirme — nunca se identifica solo.
                        doctor = (fields.get("requesting_doctor") or fields.get("clinic_name") or "").strip()
                        doctor_hits = db.find_clients_by_professional(doctor, limit=MAX_CLIENT_MATCH_OPTIONS)
                        if doctor_hits:
                            _store_client_match_options(fields, doctor, doctor_hits)
                            ai_response = _base_route_response(
                                _professional_match_options_reply(doctor, doctor_hits), fields)
                            skip_client_lookup = True
                    if client or skip_client_lookup:
                        pass
                    elif matches:
                        has_more = len(matches) > MAX_CLIENT_MATCH_OPTIONS
                        shown = matches[:MAX_CLIENT_MATCH_OPTIONS]
                        _store_client_match_options(fields, fields.get("clinic_name"), shown)
                        ai_response = _base_route_response(
                            _client_match_options_reply(fields.get("clinic_name"), shown, has_more=has_more),
                            fields,
                        )
                        skip_client_lookup = True

        if not skip_client_lookup:
            if client:
                _clear_client_match_options(fields)
                db.link_client_to_session(chat_id, client["id"])
                session["client_id"] = client["id"]
                _store_client_context(fields, client)
            else:
                fields["_client_found"] = False
                fields["_client_not_found"] = True
            client_status_changed = True

    # Si el cliente acaba de ser identificado (o no encontrado), resolver en el mismo turno
    if client_status_changed:
        if fields.get("_client_not_found"):
            if prev_captured.get("_asked_if_new_client"):
                if prev_captured.get("_handoff_announced"):
                    # Ya se notificó la derivación en un turno anterior.
                    # No repetir el mismo mensaje: dejar que el AI responda la nueva consulta.
                    fields["_handoff_announced"] = True
                elif _confirms_new_client(user_message):
                    return _escalate_new_client_turn(chat_id, session, user_message, fields, started_from_escalation)
                else:
                    fields["_asked_if_new_client"] = True
                    ai_response = {
                        "reply": CLIENT_RETRY_NOT_FOUND_MESSAGE,
                        "phase": "fase_2_recogida_datos",
                        "intent": ai_response.get("intent", "unknown"),
                        "service_area": "unknown",
                        "requires_handoff": False,
                        "handoff_area": None,
                        "captured_fields": fields,
                        "confidence": 1.0,
                        "message_mode": "flow_progress",
                        "pending_intents": [],
                        "resume_prompt": "",
                    }
            else:
                # Primera vez que no se encuentra -> preguntar antes de escalar
                fields["_asked_if_new_client"] = True
                ai_response = {
                    "reply": CLIENT_SEARCH_FAILED_MESSAGE,
                    "phase": "fase_2_recogida_datos",
                    "intent": ai_response.get("intent", "unknown"),
                    "service_area": "unknown",
                    "requires_handoff": False,
                    "handoff_area": None,
                    "captured_fields": fields,
                    "confidence": 1.0,
                    "message_mode": "flow_progress",
                    "pending_intents": [],
                    "resume_prompt": "",
                }
        else:
            registered_address = fields.get("_client_address")
            supplied_address = fields.get("pickup_address")
            if client.get("clinic_name") and not fields.get("clinic_name"):
                fields["clinic_name"] = client.get("clinic_name")
            # Una dirección solo vale como "dada por el usuario" si la escribió en SU mensaje.
            # Si el modelo la arrastró del historial (p. ej. el resumen del cliente ANTERIOR
            # tras un cambio de cliente), se descarta y se confirma la del cliente nuevo — la
            # recogida en la dirección equivocada es un error de logística real (L50).
            if (supplied_address and registered_address
                    and not _same_text(supplied_address, registered_address)
                    and not _address_written_by_user(supplied_address, user_message)):
                supplied_address = None
                fields["pickup_address"] = None
            if registered_address and (not supplied_address or _same_text(supplied_address, registered_address)):
                fields["pickup_address"] = registered_address
                fields["_address_confirmation_pending"] = True
                fields["_address_confirmed"] = False
                reply = _client_found_reply(fields)
                operational_answer = _operational_side_question_answer(user_message)
                if operational_answer:
                    reply = f"{operational_answer}\n\n{reply}"
                ai_response = _base_route_response(reply, fields)
            elif supplied_address:
                fields["_address_confirmation_pending"] = False
                fields["_address_confirmed"] = True
                ai_response["captured_fields"] = fields
            else:
                updated_session = {**session, "captured_fields": fields}
                ai_response = ai.generate_turn(
                    session=updated_session,
                    history=history,
                    user_message=user_message,
                    pending_intents=pending,
                    catalog_context=catalog_ctx,
                )
                new_fields = ai_response.get("captured_fields", {})
                for k, v in fields.items():
                    if k.startswith("_"):
                        new_fields[k] = v
                fields = new_fields
                # SEGUNDA llamada al modelo del turno: mismo candado que la primera. Por acá,
                # sin filtro, re-entraban los análisis de la orden anterior (ERR-114).
                _candado_provenancia_tests(fields, prev_captured, user_message)

    was_results = ai_response.get("intent") == "results"
    ai_response = _enforce_results_message(session, ai_response, user_message)
    if was_results:
        # El turno de resultados se resuelve acá (mensaje fijo, o mensaje fijo +
        # retomando la recogida pendiente). No sigue el resto del pipeline.
        return _persist_turn(chat_id, user_message, ai_response)

    # La recomendación de perfiles ('no sé / qué me recomiendas' o cambio total de análisis)
    # corre PRIMERO: si no, un guess del modelo (ej. exam_type='Perfil Renal') lo capturaba
    # _enforce_diagnostic_label_help y bloqueaba la recomendación real por especie.
    ai_response = _enforce_profile_recommendation_help(session, ai_response, user_message, history)
    fields = ai_response.get("captured_fields", fields)
    # Un exam_type nuevo tiene que estar anclado a lo que el cliente dijo (QA-5): corre
    # ANTES de las ayudas de catálogo para que no trabajen sobre un análisis inventado.
    ai_response = _enforce_exam_type_grounding(ai_response, prev_captured, user_message, history)
    fields = ai_response.get("captured_fields", fields)
    ai_response = _enforce_multiple_tests_capture(session, ai_response, prev_captured, user_message)
    fields = ai_response.get("captured_fields", fields)
    # Códigos que el modelo estructuró por su cuenta: validar el anclaje (I3). Corre después
    # de la captura por texto (esa ya resuelve anclada) y antes de las ofertas/cierres.
    ai_response = _enforce_selected_tests_grounding(session, ai_response, prev_captured, user_message, history)
    fields = ai_response.get("captured_fields", fields)
    ai_response = _enforce_catalog_profile_code_selection(session, ai_response, user_message)
    fields = ai_response.get("captured_fields", fields)
    ai_response = _enforce_diagnostic_label_help(session, ai_response, user_message, prev_captured, history)
    fields = ai_response.get("captured_fields", fields)
    ai_response = _enforce_catalog_profile_help(session, ai_response, user_message, history)
    fields = ai_response.get("captured_fields", fields)
    ai_response = _enforce_generic_blood_analysis_help(session, ai_response)
    fields = ai_response.get("captured_fields", fields)
    ai_response = _enforce_test_category_help(session, ai_response, prev_captured, user_message, history)
    fields = ai_response.get("captured_fields", fields)
    ai_response = _enforce_analysis_help_fallback(session, ai_response, prev_captured, user_message, history)
    fields = ai_response.get("captured_fields", fields)
    ai_response = _enforce_profile_detail_step(session, ai_response, fields, user_message)
    fields = ai_response.get("captured_fields", fields)
    ai_response = _enforce_custom_profile_close(session, ai_response, prev_captured, user_message)
    fields = ai_response.get("captured_fields", fields)
    ai_response = _enforce_extra_analysis_offer(session, ai_response, prev_captured)
    fields = ai_response.get("captured_fields", fields)
    # Va ANTES del paso de pago: con un pedido abierto, la forma de pago cierra el PEDIDO
    # entero, no la orden suelta (decisión 011).
    ai_response = _enforce_open_pedido_close(session, ai_response, prev_captured, user_message)
    fields = ai_response.get("captured_fields", fields)
    ai_response = _enforce_payment_step(session, ai_response, fields, user_message)
    ai_response = _enforce_profile_customization_changes(ai_response, prev_captured, user_message)
    fields = ai_response.get("captured_fields", fields)
    ai_response = _enforce_profile_exam_type_integrity(ai_response)
    fields = ai_response.get("captured_fields", fields)
    ai_response = _enforce_loose_exam_catalog_resolution(ai_response, prev_captured)
    fields = ai_response.get("captured_fields", fields)
    ai_response = _enforce_age_unit_grounding(ai_response, prev_captured, user_message, history)
    fields = ai_response.get("captured_fields", fields)
    _reject_reference_phrases_as_names(fields, prev_captured)
    _normalize_name_fields(fields)
    ai_response["captured_fields"] = fields
    ai_response = _recover_enumerated_answer(ai_response, prev_captured, user_message, history)
    fields = ai_response.get("captured_fields", fields)
    ai_response = _recover_implied_animal_fields(ai_response, prev_captured, user_message, history)
    fields = ai_response.get("captured_fields", fields)
    ai_response = _clarify_ambiguous_species(ai_response, prev_captured, user_message, history)
    fields = ai_response.get("captured_fields", fields)
    ai_response = _recover_patient_name_answer(ai_response, prev_captured, user_message, history)
    fields = ai_response.get("captured_fields", fields)
    ai_response = _recover_breed_and_species(ai_response, prev_captured)
    fields = ai_response.get("captured_fields", fields)
    ai_response = _recover_unknown_breed(ai_response, user_message, history)
    fields = ai_response.get("captured_fields", fields)
    ai_response = _recover_doctor_from_text(ai_response, prev_captured, user_message, history)
    fields = ai_response.get("captured_fields", fields)
    ai_response = _apply_handoff_guardrails(ai_response)
    ai_response = _avoid_redundant_client_identity_question(session, ai_response)
    ai_response = _avoid_forbidden_route_question(session, ai_response)
    ai_response = _avoid_redundant_route_field_question(session, ai_response)
    ai_response = _avoid_repeated_question(session, ai_response, history, prev_captured)
    ai_response = _apply_route_closure_summary(ai_response)
    ai_response = _clarify_captured_field(ai_response, prev_captured)
    ai_response = _enforce_field_coherence(session, ai_response, prev_captured, user_message, history)
    ai_response = _enforce_comprehension_recheck(session, ai_response, prev_captured, user_message, history)
    ai_response = _enforce_first_missing_after_progress(session, ai_response, prev_captured)
    ai_response = _resume_route_after_lateral_turn(session, ai_response)
    fields = ai_response.get("captured_fields", fields)

    # ERR-046: la confirmación de dirección quedó pendiente y este turno no la resolvió.
    # Se respeta lo que el pipeline respondió al mensaje (menú, dato capturado, etc.),
    # pero la pregunta final del turno vuelve a ser la dirección: lo pendiente se
    # re-pregunta, no se asume.
    if (address_reask_needed and fields.get("_address_confirmation_pending")
            and ai_response.get("intent") == "route_scheduling"
            and not ai_response.get("requires_handoff")):
        reply = ai_response.get("reply") or ""
        if not ({"direccion", "dirección", "domicilio"} & set(_tokenize(reply))):
            last_question = reply.rfind("¿")
            if last_question != -1:
                reply = reply[:last_question].strip()
            ai_response["reply"] = (
                f"{reply} Antes de seguir, ¿me confirmas la dirección de retiro: "
                f"{address_reask_needed}? Si no es esa, dime la correcta."
            ).strip()

    previous_phase = session.get("phase_current", "")
    ai_response = _enforce_confirmation_step(session, ai_response, fields, previous_phase, user_message)
    # Red final antes de registrar: ninguna orden de ruta incompleta debe cerrarse/escalar.
    # Corre tras TODOS los guardrails de cierre (incluido el handoff por pago en línea
    # heredado en una orden de seguimiento), para no registrar órdenes vacías.
    fields = ai_response.get("captured_fields", fields)
    ai_response = _prevent_incomplete_route_closure(session, ai_response, fields)
    ai_response = _enforce_selected_tests_are_catalog_codes(ai_response)
    ai_response = _finalize_request(chat_id, session, ai_response, started_from_escalation, previous_phase)

    return _persist_turn(chat_id, user_message, ai_response)
