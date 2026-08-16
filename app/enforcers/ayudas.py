"""Enforcers de AYUDAS de catálogo (recomendación, detalle de perfil, fallback)."""
import re

from app import catalog, state
from app.text import as_text_items as _as_text_items, tokenize as _tokenize
from app.flow import (
    base_route_response as _base_route_response,
    format_test_items as _format_test_items,
)
from app.detectors import _detect_which_field_is_being_asked, _is_profile_confirmation, _is_profile_customization_request, _is_profile_detail_question, _last_bot_message, _looks_like_catalog_profile, _looks_like_specific_profile_query, _named_analysis_terms, _profile_codes_from_text, _wants_partial_analysis_change
from app.menus import _format_profile_options_with_details, _format_profile_recommendation, _profile_customization_reply, _profile_detail_reply, _store_profile_menu_options, _store_selected_profile_fields
from app.messages import PAYMENT_METHOD_QUESTION, EXTRA_ANALYSIS_OFFER
from app.services import ai, db
from app.rules import TERMINAL_PHASES, calculate_custom_profile_total



def _enforce_analysis_help_fallback(session: dict, ai_response: dict, prev_fields: dict,
                                    user_message: str, history: list[dict]) -> dict:
    """Red de seguridad final del paso de análisis: si el bot pidió el análisis y el cliente
    respondió algo VAGO (un síntoma/necesidad que no mapeó a área ni etiqueta, o no supo qué
    pedir) y el AI dejó exam_type vacío, mostrar perfiles de la especie en una lista
    seleccionable con precios REALES, en vez de dejar que el modelo improvise una lista sin
    menú detrás (no seleccionable y con riesgo de inventar precios). Ver RESUELTO-016."""
    if ai_response.get("intent") != "route_scheduling":
        return ai_response
    # SEÑAL-PRIMERO (Ronda 3, confirmo_y_sigo): "Ya está, son todas las órdenes" con el
    # análisis pendiente NO es "no sé qué pedir" — es cerrar/avanzar. Si el modelo leyó otra
    # intención, esta red cede y la atiende su handler (cierre del pedido, frontera, etc.).
    if ai_response.get("user_intent_signal") in {"farewell", "negate", "cancel", "another_order"}:
        return ai_response
    fields = ai_response.get("captured_fields", {})
    if not (session.get("client_id") or fields.get("_client_found")):
        return ai_response
    species = fields.get("species")
    if not species:
        return ai_response
    # Si ya hay análisis capturado o un menú/perfil/etiqueta en curso, no interferir.
    if (fields.get("exam_type") or fields.get("_selected_profile_code")
            or fields.get("selected_tests") is not None or fields.get("_diagnostic_label")
            or fields.get("_test_menu_options") or fields.get("_profile_menu_options")):
        return ai_response
    if _detect_which_field_is_being_asked(history) != "exam_type":
        return ai_response
    if _wants_partial_analysis_change(user_message) or _profile_codes_from_text(user_message):
        return ai_response
    # ¿El mensaje nombra un análisis concreto del catálogo? Entonces NO es vago: dejar que
    # el flujo normal lo registre, no mostrar una lista.
    if db.get_tests_by_codes_or_names(_named_analysis_terms(user_message)):
        return ai_response

    profiles = db.list_catalog_profiles_for_species(species, limit=6)
    if not profiles:
        return ai_response
    fields["exam_type"] = None
    fields["selected_tests"] = None
    fields["removed_tests"] = None
    _store_profile_menu_options(fields, profiles)
    return _base_route_response(_format_profile_recommendation(
        species, profiles, fields.get("_client_favorite_profiles")), fields)



def _enforce_catalog_profile_help(session: dict, ai_response: dict, user_message: str, history: list[dict]) -> dict:
    if ai_response.get("intent") != "route_scheduling":
        return ai_response

    fields = ai_response.get("captured_fields", {})
    if not (session.get("client_id") or fields.get("_client_found")):
        return ai_response

    detail_question = _is_profile_detail_question(user_message)
    species = fields.get("species")

    if fields.get("_profile_detail_offered"):
        if detail_question and fields.get("_selected_profile_code"):
            profiles = db.get_catalog_profiles_by_codes([fields["_selected_profile_code"]], species)
            if profiles:
                return _base_route_response(_profile_detail_reply(profiles[0]), fields)
        return ai_response

    if detail_question:
        codes = _profile_codes_from_text(user_message) or _profile_codes_from_text(_last_bot_message(history))
        if codes:
            profiles = db.get_catalog_profiles_by_codes(codes, species)
            if len(profiles) == 1:
                _store_selected_profile_fields(fields, profiles[0])
                return _base_route_response(_profile_detail_reply(profiles[0]), fields)
            if len(profiles) > 1:
                fields["exam_type"] = None
                fields["_profile_options_offered"] = True
                return _base_route_response(_format_profile_options_with_details(None, profiles), fields)

    query = fields.get("exam_type") if _looks_like_catalog_profile(fields.get("exam_type")) else None
    if detail_question and not query:
        query = user_message
    if not query:
        return ai_response
    if not detail_question and _looks_like_specific_profile_query(query):
        return ai_response

    profiles = db.find_catalog_profiles(query, species)
    if len(profiles) > 1:
        fields["exam_type"] = None
        fields["_profile_options_offered"] = True
        return _base_route_response(_format_profile_options_with_details(query, profiles), fields)
    if detail_question and len(profiles) == 1:
        _store_selected_profile_fields(fields, profiles[0])
        return _base_route_response(_profile_detail_reply(profiles[0]), fields)
    return ai_response



def _enforce_profile_detail_step(session: dict, ai_response: dict, fields: dict, user_message: str) -> dict:
    if ai_response.get("intent") != "route_scheduling":
        return ai_response
    if fields.get("_profile_detail_confirmed") or fields.get("_profile_customizing"):
        return ai_response
    if fields.get("selected_tests") is not None and not fields.get("_selected_profile_code"):
        return ai_response

    if fields.get("_profile_detail_offered"):
        signal = ai_response.get("user_intent_signal")
        # Ajuste PARCIAL del perfil base: 'personalizar/agregar/quitar' (tokens explícitos) o
        # 'el mismo pero sin X / igual más Y'. Mantiene el perfil base y entra al modo
        # personalización; el detalle (qué agregar/quitar) lo captura el LLM con el contexto
        # de "PERFIL BASE EN PERSONALIZACIÓN" inyectado.
        wants_customization = _is_profile_customization_request(user_message) or _wants_partial_analysis_change(user_message)
        rows = db.get_tests_by_codes_or_names([user_message] + _named_analysis_terms(user_message)) if wants_customization else []
        if wants_customization and (rows or signal != "negate"):
            fields["_profile_customizing"] = True
            if not isinstance(fields.get("selected_tests"), list):
                fields["selected_tests"] = []
            if not isinstance(fields.get("removed_tests"), list):
                fields["removed_tests"] = []
            if rows:
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
            return _base_route_response(_profile_customization_reply(fields), fields)
        if signal in {"affirm", "negate"} or _is_profile_confirmation(user_message):
            fields["_profile_detail_confirmed"] = True
        return ai_response

    exam_type = fields.get("exam_type")
    if not _looks_like_catalog_profile(exam_type):
        return ai_response

    profile = db.find_catalog_profile(exam_type, fields.get("species"))
    if not profile:
        return ai_response

    fields["exam_type"] = profile.get("name") or exam_type
    fields["_selected_profile_code"] = profile.get("code")
    fields["_selected_profile_name"] = profile.get("name") or exam_type
    fields["_selected_profile_price"] = int(profile.get("price") or 0)
    fields["_selected_profile_description"] = profile.get("description") or ""
    fields["_profile_detail_offered"] = True
    return _base_route_response(_profile_detail_reply(profile), fields)

