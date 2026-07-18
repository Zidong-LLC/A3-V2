"""Enforcers de CATÁLOGO/identificación: ayudas de área, anclaje de códigos, cierre
de perfil a medida y la puerta de identificación."""
import re

from app import catalog, state
from app.text import tokenize as _tokenize, as_text_items as _as_text_items,     catalog_item_key as _catalog_item_key
from app.flow import (
    base_route_response as _base_route_response, missing_route_field as _missing_route_field,
    missing_route_field_question as _missing_route_field_question,
    format_test_items as _format_test_items,
)
from app.detectors import (
    _is_generic_blood_analysis, _is_same_as_previous, _wants_to_close_custom_profile,
    _is_profile_customization_request, _looks_like_specific_profile_query,
    _asks_for_client_identity, _detect_which_field_is_being_asked, _last_bot_message,
)
from app.menus import (
    _test_area_suggestion_reply, _store_test_menu_options, _test_options_response,
    _analysis_help_candidate, _client_identity_prompt_count, _profile_lists_unchanged,
)
from app.messages import CLIENT_IDENTIFICATION_REQUIRED_MESSAGE
from app.services import db




def _enforce_client_identification_gate(session: dict, ai_response: dict, history: list[dict]) -> dict:
    if ai_response.get("intent") != "route_scheduling" or ai_response.get("requires_handoff"):
        return ai_response
    if ai_response.get("message_mode") == "cancellation":
        return ai_response

    fields = ai_response.get("captured_fields", {})
    if session.get("client_id") or fields.get("_client_found"):
        return ai_response
    if fields.get("clinic_name") or fields.get("tax_id") or fields.get("_client_match_options"):
        return ai_response

    # Preguntas de preventa/metodología no son una orden todavía. Dejar que el LLM
    # responda como persona; pedir NIT solo cuando el usuario quiera programar.
    if ai_response.get("message_mode") == "side_question":
        return ai_response

    if _client_identity_prompt_count(history) >= 2:
        ai_response["reply"] = CLIENT_IDENTIFICATION_REQUIRED_MESSAGE
    elif not _asks_for_client_identity(ai_response.get("reply", "")):
        ai_response["reply"] = _missing_route_field_question("client")
    ai_response["phase"] = "fase_2_recogida_datos"
    ai_response["service_area"] = "route_scheduling"
    ai_response["requires_handoff"] = False
    ai_response["handoff_area"] = None
    ai_response["message_mode"] = "flow_progress"
    return ai_response



def _enforce_custom_profile_close(session: dict, ai_response: dict, prev_fields: dict, user_message: str) -> dict:
    """Backstop determinístico: si el cliente armó un perfil personalizado desde
    cero (selected_tests con análisis, sin perfil base) y pide cerrarlo, fija el
    exam_type para que la orden avance, sin depender de que el modelo lo haga.
    Evita el bucle '¿agregás otro análisis o lo cerramos así?'."""
    if ai_response.get("intent") != "route_scheduling":
        return ai_response
    fields = ai_response.get("captured_fields", {})
    if fields.get("_selected_profile_code") and fields.get("_profile_customizing"):
        if not _wants_to_close_custom_profile(user_message):
            return ai_response
        fields["_profile_customizing"] = False
        fields["_profile_detail_confirmed"] = True
        missing = _missing_route_field(session, fields)
        reply = "Perfecto, dejamos ese perfil así."
        if missing and missing != "exam_type":
            reply += f" {_missing_route_field_question(missing)}"
        return _base_route_response(reply, fields)
    selected = _as_text_items(fields.get("selected_tests"))
    if not selected or fields.get("_selected_profile_code") or fields.get("exam_type"):
        return ai_response
    # Solo cerrar si en este turno no agregó/quitó análisis y pidió cerrar.
    if not _profile_lists_unchanged(prev_fields, fields):
        return ai_response
    if not _wants_to_close_custom_profile(user_message):
        return ai_response

    fields["exam_type"] = f"Perfil personalizado ({len(selected)} análisis)"
    fields["_profile_customizing"] = False
    missing = _missing_route_field(session, fields)
    if missing and missing != "exam_type":
        return _base_route_response(_missing_route_field_question(missing), fields)
    ai_response["captured_fields"] = fields
    return ai_response



def _enforce_generic_blood_analysis_help(session: dict, ai_response: dict) -> dict:
    if ai_response.get("intent") != "route_scheduling":
        return ai_response
    fields = ai_response.get("captured_fields", {})
    if not (session.get("client_id") or fields.get("_client_found")):
        return ai_response
    if fields.get("selected_tests") is not None or fields.get("_diagnostic_label"):
        return ai_response
    if not _is_generic_blood_analysis(fields.get("exam_type")):
        return ai_response
    area, tests = db.find_tests_by_area("Hematología", fields.get("species"), limit=8)
    if not tests:
        return ai_response
    reply = (
        "'Análisis de sangre' es muy general; no hay una prueba única con ese nombre. "
        "Para sangre/hematología tenemos estas opciones:\n"
        + _test_area_suggestion_reply(area or "hematología", tests).split("\n", 1)[1]
    )
    return _test_options_response(fields, tests, reply)



def _enforce_selected_tests_grounding(session: dict, ai_response: dict, prev_fields: dict,
                                      user_message: str, history: list[dict]) -> dict:
    """I3 por la puerta lateral (prueba real 2026-07-16): cuando el MODELO estructura
    `selected_tests` por su cuenta, el resolvedor de texto nunca corre y nada validaba que
    cada código correspondiera a un análisis que el cliente NOMBRÓ. 'potasio sodio y orina'
    → el modelo eligió solo 'Parcial de Orina' entre 5 opciones de orina y se aceptó en
    silencio. Regla: cada código NUEVO debe estar anclado al texto del cliente (mensaje
    actual, turnos recientes o la oferta previa del bot); lo no-anclado se quita y se vuelve
    MENÚ de su área — la adivinanza del modelo se convierte en opciones, nunca en agregado."""
    if ai_response.get("intent") != "route_scheduling" or ai_response.get("requires_handoff"):
        return ai_response
    fields = ai_response.get("captured_fields", {})
    if not (session.get("client_id") or fields.get("_client_found")):
        return ai_response
    prev = prev_fields or {}
    prev_codes = set(_as_text_items(prev.get("selected_tests")))
    new_codes = [c for c in _as_text_items(fields.get("selected_tests")) if c not in prev_codes]
    if not new_codes:
        return ai_response
    # Vías ya validadas por otro camino: la repetición del pedido previo, o una selección
    # sobre el menú mostrado ('el 1' no nombra el análisis) — pero SOLO si los códigos nuevos
    # salen de ese menú. Un menú PEGADO de otro paso (ej. perfiles prequirúrgicos arrastrados
    # hasta el armado a medida) no desactiva el anclaje: por ese hueco 'orina' se registró
    # igual sin menú en el replay verificado.
    if _is_same_as_previous(user_message):
        return ai_response
    menu_codes = {str(o.get("code")) for o in (prev.get("_test_menu_options") or []) if o.get("code")}
    if menu_codes and set(new_codes) <= menu_codes:
        return ai_response
    snapshot = prev.get("_prev_order_snapshot") or {}
    if set(new_codes) <= set(_as_text_items(snapshot.get("selected_tests"))):
        return ai_response
    try:
        all_rows = db.list_catalog_tests(limit=5000)
    except Exception:
        return ai_response
    rows_by_code = {str(r.get("code")): r for r in all_rows if str(r.get("code")) in set(new_codes)}
    if not rows_by_code:
        return ai_response
    # Anclaje con el MISMO resolvedor unívoco de la vía de texto: lo que el mensaje resuelve
    # EXACT está anclado; si resuelve AMBIGUOUS y el código está entre los candidatos, el
    # modelo eligió por el cliente en un empate real ('glucosa' → las tres glucosas) y esas
    # MISMAS opciones son el menú. Para el resto (p. ej. 'sí, agrégalo' tras una oferta),
    # ancla el texto reciente del cliente o la última respuesta del bot que lo nombró.
    resolved = catalog.resolve_tests(user_message, all_rows, fields.get("species"))
    exact_codes = ({str(r.get("code")) for r in resolved.tests}
                   if resolved.status == catalog.EXACT else set())
    tie_codes = ({str(r.get("code")) for r in resolved.tests}
                 if resolved.status == catalog.AMBIGUOUS else set())
    user_texts = [m.get("content", "") for m in history if m.get("role") == "user"][-2:]
    bot_texts = [m.get("content", "") for m in history if m.get("role") != "user"][-1:]
    corpus = " ".join([user_message] + user_texts + bot_texts)
    guessed, tied = [], []
    for code, row in rows_by_code.items():
        if code in exact_codes:
            continue
        if code in tie_codes:
            tied.append(row)
        elif not catalog.names_test(corpus, row):
            guessed.append(row)
    if not guessed and not tied:
        return ai_response
    guessed = tied + guessed

    guessed_codes = {str(r.get("code")) for r in guessed}
    kept = [c for c in _as_text_items(fields.get("selected_tests")) if c not in guessed_codes]
    fields["selected_tests"] = kept
    exam = str(fields.get("exam_type") or "")
    if "personalizado" in exam.lower():
        fields["exam_type"] = f"Perfil personalizado ({len(kept)} análisis)" if kept else None
    grounded_new = [rows_by_code[c] for c in new_codes
                    if c in rows_by_code and c not in guessed_codes]
    intro = f"Listo, registro {_format_test_items(grounded_new)}. " if grounded_new else ""

    # La adivinanza se ofrece como MENÚ para que ELIJA el cliente. Empate de nombres
    # ('glucosa' → las tres glucosas): las opciones son los propios candidatos del
    # resolvedor. Palabra de área ('orina'): el menú del área del test adivinado.
    if tied:
        options = resolved.tests[:10]
        label = resolved.area or "ese análisis"
        _store_test_menu_options(fields, options)
        if kept or fields.get("_selected_profile_code"):
            fields["_test_menu_adds_to_profile"] = True
        return _base_route_response(intro + _test_area_suggestion_reply(label, options), fields)
    area, area_tests = db.find_tests_by_area(
        guessed[0].get("category") or guessed[0].get("name"), fields.get("species"), limit=10,
    )
    if area and area_tests:
        _store_test_menu_options(fields, area_tests)
        if kept or fields.get("_selected_profile_code"):
            fields["_test_menu_adds_to_profile"] = True
        return _base_route_response(intro + _test_area_suggestion_reply(area, area_tests), fields)
    return _base_route_response(
        f"{intro}Del resto no estoy seguro de cuál análisis necesitas: "
        "¿me confirmas el nombre o código exacto?", fields,
    )



def _enforce_test_category_help(session: dict, ai_response: dict, prev_fields: dict,
                                user_message: str, history: list[dict]) -> dict:
    """Si el cliente pide análisis por área o tipo de muestra (ej. "orina",
    "materia fecal") y no es un perfil ni una etiqueta diagnóstica, despliega los
    análisis individuales de esa área y arranca la selección (perfil personalizado)."""
    if ai_response.get("intent") != "route_scheduling":
        return ai_response
    fields = ai_response.get("captured_fields", {})
    if not (session.get("client_id") or fields.get("_client_found")):
        return ai_response
    # Ya se está armando un perfil o ya se sugirió una etiqueta/área en este flujo.
    if fields.get("selected_tests") is not None or fields.get("_diagnostic_label"):
        return ai_response

    candidate = _analysis_help_candidate(fields, prev_fields, user_message, history)
    if not candidate:
        return ai_response
    if _looks_like_specific_profile_query(candidate):
        return ai_response

    area, tests = db.find_tests_by_area(candidate, fields.get("species"), limit=10)
    if not tests:
        return ai_response

    # Pedido MIXTO (clase ERR-067, 4ª ruta — QA real 2026-07-18): 'sodio potasio y orina'
    # de primer pedido llegaba ACÁ (el modelo no capturó nada y este helper matcheó el
    # área) y el menú MACHACABA los exactos (selected_tests=[]) en silencio. Lo
    # inequívoco se registra ya; el menú del área se ofrece como AGREGADO (la selección
    # posterior SUMA, no reemplaza).
    try:
        partial = catalog.resolve_tests(user_message, db.list_catalog_tests(limit=5000),
                                        fields.get("species"), collect_partial=True)
    except Exception:
        partial = None
    if partial is not None and partial.status == catalog.EXACT and partial.tests:
        codes = [str(r.get("code")) for r in partial.tests]
        fields["selected_tests"] = codes
        fields["removed_tests"] = []
        fields["exam_type"] = (f"{partial.tests[0].get('code')} {partial.tests[0].get('name')}"
                               if len(codes) == 1
                               else f"Perfil personalizado ({len(codes)} análisis)")
        _store_test_menu_options(fields, tests)
        fields["_test_menu_adds_to_profile"] = True
        intro = (f"Listo, registro {_format_test_items(partial.tests)}. "
                 "Ahora vamos con lo siguiente que pediste:\n")
        return _base_route_response(intro + _test_area_suggestion_reply(area or candidate, tests), fields)

    fields["exam_type"] = None
    fields["selected_tests"] = []
    fields["removed_tests"] = []
    _store_test_menu_options(fields, tests)
    return _base_route_response(_test_area_suggestion_reply(area or candidate, tests), fields)
