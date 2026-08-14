"""Enforcers del ARMADO de la orden (ofertas de agregado, captura múltiple,
resolución de texto suelto, personalización e integridad del perfil)."""
import re

from app import catalog, state
from app.config import PEDIDOS_ENABLED
from app.text import as_text_items as _as_text_items, catalog_item_key as _catalog_item_key, money as _money, strip_price_text as _strip_price_text, tokenize as _tokenize
from app.flow import (
    base_route_response as _base_route_response,
    estimated_total_text as _estimated_total_text,
    format_test_items as _format_test_items,
    missing_route_field as _missing_route_field,
    missing_route_field_question as _missing_route_field_question,
    order_data_complete as _order_data_complete,
)
from app.detectors import (
    _AFFIRMATIVE_TOKENS,
    _REMOVE_TOKENS,
    _STABLE_ORDER_FIELDS,
    _detect_correction_field,
    _detect_which_field_is_being_asked,
    _wants_to_change_client,
    _doesnt_know_what_to_ask,
    _is_affirmative_text,
    _is_ambiguous_profile_change,
    _is_profile_customization_request,
    _is_profile_detail_question,
    _looks_like_catalog_profile,
    _looks_like_specific_profile_query,
    _named_analysis_terms,
    _payment_method_from_text,
    _profile_codes_from_text,
    _split_multiple_exam_items,
    _wants_partial_analysis_change,
    _wants_profile_recommendation,
    _wants_to_proceed_to_payment,
)
from app.menus import (
    _analysis_help_candidate,
    _diagnostic_label_suggestion_reply,
    _format_profile_recommendation,
    _profile_lists_unchanged,
    _store_profile_menu_options,
    _store_selected_profile_fields,
    _store_test_menu_options,
    _test_area_suggestion_reply,
    _test_options_response,
    _unknown_catalog_items,
)
from app.orders import (
    _scan_ambiguous_terms, _menu_for_ambiguous_term,
    _add_tests_to_order,
    _analysis_settled_response,
    _order_confirmation_response,
    _area_options_for_profile_addition,
    _capture_profile_menu_selection,
    _category_profiles_menu_response,
    _resolve_profile_base_if_missing,
    _selected_profile_addition_response,
)
from app.messages import (
    EXTRA_ANALYSIS_AMBIGUOUS_QUESTION, EXTRA_ANALYSIS_OFFER, PAYMENT_METHOD_QUESTION,
)
from app.rules import calculate_custom_profile_total
from app.services import db


_ADD_ANALYSIS_TOKENS = frozenset({"poner", "pon", "ponme", "ponle", "poné", "agrega", "agregá",
                                  "agregar", "agregale", "agrégale", "sumar", "suma", "sumale",
                                  "cambia", "cambiá", "cambiar", "reemplaza", "reemplazar"})



def _format_profile_items(profiles: list[dict]) -> str:
    return ", ".join(f"{p.get('code')} {p.get('name')} {_money(p.get('price'))}" for p in profiles)


def _attach_profiles_by_code(fields: dict, user_message: str) -> tuple[list[dict], list[dict]]:
    """Engancha a la orden los PERFILES que el cliente nombró por su CÓDIGO.

    Los perfiles viven en `catalog_profiles`, no en `catalog_tests`, así que el resolvedor de
    análisis nunca los ve. Se consultan TODOS los códigos del mensaje —no solo el primero—
    porque el pedido mixto real trae análisis y perfil juntos ('el 1101 y el perfil 701') y
    quedarse con el primero perdía el perfil. Con perfil base ya elegido, el nuevo se suma
    como perfil adicional (mecanismo de ERR-077, que el resumen ya muestra y suma).

    Devuelve (enganchados, ya_estaban): el segundo grupo permite acusar "ese ya lo tenés"
    en vez de tratar la repetición como un pedido nuevo y caer a la lista de recomendaciones.
    """
    codes = _profile_codes_from_text(user_message)
    if not codes:
        return [], []
    try:
        profiles = db.get_catalog_profiles_by_codes(codes, fields.get("species"))
    except Exception:
        return [], []
    attached, already = [], []
    for profile in profiles:
        code = str(profile.get("code"))
        if fields.get("_selected_profile_code"):
            extras = list(fields.get("_extra_profiles") or [])
            if code == str(fields.get("_selected_profile_code")) or any(
                    str(p.get("code")) == code for p in extras):
                already.append(profile)
                continue
            extras.append({"code": profile.get("code"), "name": profile.get("name"),
                           "price": int(profile.get("price") or 0)})
            fields["_extra_profiles"] = extras
        else:
            _store_selected_profile_fields(fields, profile)
        attached.append(profile)
    return attached, already


def _handle_extra_analysis_answer(session: dict, fields: dict, user_message: str) -> dict | None:
    """Interpreta la respuesta del cliente a la oferta '¿agregar otro análisis o seguimos con
    el pago?'. Devuelve la respuesta del bot, o None si dio el método de pago (que el pipeline
    normal capture). Se repite tras cada agregado hasta que el cliente decida seguir."""
    # 0) CORRECCIÓN de un dato estable de la orden ('quiero cambiar la raza es un tobiano'):
    # no es un asunto de este carril — ceder el turno COMPLETO al modelo, que captura el
    # cambio; el acuse determinístico lo arma _enforce_first_missing_after_progress
    # (ERR-069: el carril devoraba la corrección y respondía '¿qué análisis agregas?' en
    # bucle — chat real 2026-07-17, 3 intentos del cliente sin acuse).
    correction_field = _detect_correction_field(user_message)
    if correction_field in _STABLE_ORDER_FIELDS:
        return None
    # ERR-099: un cambio de CLIENTE en medio de la oferta tampoco es de este carril. El guard
    # de abajo (_wants_to_change_client) no reconoce fraseos como "el cliente, soy Animal
    # Pets"; el detector de campo sí, y ceder acá deja que la identificación se re-verifique.
    if correction_field == "clinic_name":
        return None
    # Cambio de cliente/sede ('necesito cambiar de veterinaria') tampoco es de este carril:
    # con el reorden C2 el atajo pre-LLM ya no intercepta antes — sin esta cesión, el paso
    # genérico se lo tragaba con '¿qué análisis agregas?' (mensaje corto, <8 tokens).
    if _wants_to_change_client(user_message):
        return None
    # 1) Sigue al pago: dio el método o dijo que ya está. Un atajo solo traga el mensaje si
    # NO trae más que eso (L49): un 'no' incidental dentro de otra intención ('...esta orden
    # va a nombre de otra clínica, no de animal pets') no debe cerrar la oferta y saltar al
    # pago — verificado en vivo con modelo real (3.3).
    if _wants_to_proceed_to_payment(user_message) and (
        _payment_method_from_text(user_message) or len(_tokenize(user_message)) <= 6
    ):
        fields.pop("_offering_extra_analysis", None)
        if _payment_method_from_text(user_message):
            return None  # el pipeline normal captura el método de pago
        # Con pedidos NO hay pago que preguntar acá: la forma de pago es del PEDIDO y se
        # pregunta una sola vez al cerrarlo (decisión 011). Declinar la oferta lleva la orden
        # a su confirmación. Este carril devolvía PAYMENT_METHOD_QUESTION sin mirar el flag,
        # así que pedía la forma de pago orden por orden incluso con pedidos encendidos
        # — reportado en el testeo en vivo del 2026-08-14.
        if PEDIDOS_ENABLED:
            confirmacion = _order_confirmation_response(fields)
            if confirmacion:
                return confirmacion
            # Orden todavía incompleta (no debería pasar: la oferta solo sale cuando ya no
            # falta nada). Se pide el dato pendiente antes que preguntar un pago que en este
            # flujo no corresponde.
            missing = _missing_route_field(session, fields)
            return _base_route_response(_missing_route_field_question(missing), fields) if missing else None
        return _base_route_response(PAYMENT_METHOD_QUESTION, fields)

    tokens = set(_tokenize(user_message))

    # 1b) ERR-093: nombró el pago, pero el mensaje trae más texto del que acepta el atajo de
    # arriba ("No seguimos con el pago, te estoy diciendo" son 8 tokens y el guard corta en 6).
    # La frase es genuinamente ambigua: "no, sigamos con el pago" vs "no sigamos con el pago".
    # Antes seguía cayendo por la cascada hasta el paso 3 y RE-MOSTRABA el menú de perfiles
    # desde cero, tirando todo el avance de la orden (QA en vivo 2026-07-27, chat 1).
    # Ante la duda se PREGUNTA, no se adivina. Se excluye el caso con intención explícita de
    # tocar el pedido ("agregale una glucosa antes del pago"): ahí el verbo desambigua solo.
    # No se usa `_named_analysis_terms` para esto porque devuelve palabras sueltas de la frase
    # ("seguimos", "pago"), no análisis del catálogo — no distingue nada acá.
    if (_wants_to_proceed_to_payment(user_message)
            and not (tokens & _ADD_ANALYSIS_TOKENS)
            and not (tokens & _REMOVE_TOKENS)):
        return _base_route_response(EXTRA_ANALYSIS_AMBIGUOUS_QUESTION, fields)

    # 2) Pregunta por opciones de un área ('qué análisis de orina tienen') -> menú que SUMA.
    area_resp = _area_options_for_profile_addition(fields, user_message)
    if area_resp:
        return area_resp

    # 2b) Quiere AGREGAR sobre el análisis ya elegido ('agregale un análisis más a este
    #     perfil'): abrir el ajuste del perfil base — NUNCA ofrecer perfiles nuevos (esto
    #     mostraba Perfiles Cachorros ante "agregarle un análisis más"; chat 4). Si nombra
    #     otro código de perfil en el mismo mensaje ('el 152 y agregarle...'), se respeta.
    if ((fields.get("_selected_profile_code") or _as_text_items(fields.get("selected_tests")))
            and _wants_partial_analysis_change(user_message)
            and not (tokens & _REMOVE_TOKENS)):
        codes = [c for c in _profile_codes_from_text(user_message)
                 if c != str(fields.get("_selected_profile_code") or "")]
        if codes:
            try:
                profiles = db.get_catalog_profiles_by_codes(codes[:1], fields.get("species"))
            except Exception:
                profiles = []
            if len(profiles) == 1:
                _store_selected_profile_fields(fields, profiles[0])
        name = fields.get("_selected_profile_name")
        intro = (f"Claro, seguimos con {name} ({_money(fields.get('_selected_profile_price'))})."
                 if name else "Claro, seguimos con tu perfil.")
        return _selected_profile_addition_response(session, fields, user_message, intro)

    # 2c) Nombró un PERFIL por su CÓDIGO ('perfil 903', '903', 'otro más: el 903'). Va ANTES
    #     de la recomendación y del resolvedor de análisis por dos razones: `resolve_tests`
    #     solo mira `catalog_tests` (un código de perfil no resuelve nada y el turno caía a
    #     "¿qué análisis querés agregar?"), y la heurística de 'otro/más' del paso 3 tapaba el
    #     código explícito con una lista genérica. Un código concreto es la señal más fuerte
    #     que puede dar el cliente: gana. ERR-080 ya cubrió esto para la confirmación; acá se
    #     cierra el carril de la oferta, donde el cliente pidió el 903 dos veces y la orden
    #     cerró sin él (simulación con cliente humano sobre datos reales, 2026-08-12).
    if not (tokens & _REMOVE_TOKENS):
        added_profiles, repeated_profiles = _attach_profiles_by_code(fields, user_message)
        if added_profiles:
            fields.pop("_awaiting_additional_test", None)
            return _analysis_settled_response(
                session, fields, f"Listo, agrego {_format_profile_items(added_profiles)}.")
        if repeated_profiles:
            fields.pop("_awaiting_additional_test", None)
            return _analysis_settled_response(
                session, fields,
                f"Ese ya está en la orden: {_format_profile_items(repeated_profiles)}.")

    # 3) Pide recomendación / no sabe / 'otro perfil' -> lista de perfiles por especie.
    species = fields.get("species")
    if species and (_wants_profile_recommendation(user_message) or _doesnt_know_what_to_ask(user_message)
                    or ("perfil" in tokens and tokens & {"otro", "otra", "mas", "más"})):
        profiles = db.list_catalog_profiles_for_species(species, limit=6)
        if profiles:
            _store_profile_menu_options(fields, profiles)
            return _base_route_response(_format_profile_recommendation(
                species, profiles, fields.get("_client_favorite_profiles")), fields)

    # 3b) Nombró una CATEGORÍA de perfiles armados ('un prequirúrgico', 'un renal') mientras
    #     agrega: ofrecer esos perfiles para elegir, en vez de tratarlo como análisis suelto
    #     (historial real: 'un prequirúrgico' repetido caía en bucle '¿qué análisis?').
    if not (tokens & _REMOVE_TOKENS):
        category_resp = _category_profiles_menu_response(fields, user_message)
        if category_resp:
            return category_resp

    # 4) Nombró análisis concreto(s). QUITAR opera sobre lo ya elegido (resolución directa).
    #    AGREGAR pasa por el resolvedor unívoco: solo agrega con match inequívoco; ante un
    #    término genérico o de área ('sanguíneos', 'orina') ofrece opciones en vez de adivinar
    #    un test suelto y sumarlo callado (raíz de ERR-053). Ante la duda, ofrecer.
    named_terms = _named_analysis_terms(user_message)
    # Términos que nombran un análisis de verdad (excluye muletillas afirmativas como 'dale':
    # un 'sí, dale' suelto NO debe cargar el catálogo, va al paso 5 a preguntar cuál).
    analysis_terms = [t for t in named_terms if t not in _AFFIRMATIVE_TOKENS]
    if tokens & _REMOVE_TOKENS:
        # Reemplazo ('sacá eso y ponme una glucosa', 'cambiá X por Y'): hay remove Y add, y se
        # nombra un análisis concreto para poner → se quita lo suelto actual y se agrega el
        # nuevo (QA extremo: 'sacá eso y ponme glucosa' se ignoraba y seguía con el previo).
        if (tokens & _ADD_ANALYSIS_TOKENS) and analysis_terms:
            new_res = catalog.resolve_tests(user_message, db.list_catalog_tests(limit=5000), fields.get("species"))
            if new_res.status == catalog.EXACT and new_res.tests:
                fields["selected_tests"] = []
                _add_tests_to_order(fields, new_res.tests, "add")
                fields.pop("_awaiting_additional_test", None)
                return _analysis_settled_response(session, fields, f"Listo, lo cambio por {_format_test_items(new_res.tests)}.")
        rows = (db.get_tests_by_codes_or_names([user_message])
                or db.get_tests_by_codes_or_names(named_terms))
        if rows:
            _add_tests_to_order(fields, rows, "remove")
            fields.pop("_awaiting_additional_test", None)
            return _analysis_settled_response(session, fields, f"Listo, quito {_format_test_items(rows)}.")
    elif analysis_terms:
        result = catalog.resolve_tests(user_message, db.list_catalog_tests(limit=5000), fields.get("species"))
        if result.status == catalog.EXACT:
            _add_tests_to_order(fields, result.tests, "add")
            fields.pop("_awaiting_additional_test", None)
            intro = f"Listo, agrego {_format_test_items(result.tests)}."
            # Pedido MIXTO análisis + PERFIL en la misma frase ('el 1101 y el perfil 701'):
            # el análisis resolvía y el turno retornaba acá, así que el perfil se perdía en
            # silencio (sim con datos reales: el 701 nunca llegó al resumen).
            mixed_profiles, _ = _attach_profiles_by_code(fields, user_message)
            if mixed_profiles:
                intro += f" Y sumo {_format_profile_items(mixed_profiles)}."
            # Pedido MIXTO (ERR-067): los términos con OPCIONES de la misma frase se
            # ofrecen en ORDEN de pedido — el primero ya, el resto en cola paso a paso.
            ambiguous = _scan_ambiguous_terms(fields, user_message)
            if ambiguous:
                menu = _menu_for_ambiguous_term(fields, ambiguous[0])
                if menu:
                    if ambiguous[1:]:
                        fields["_pending_ambiguous_items"] = ambiguous[1:]
                    return _base_route_response(f"{intro}\n{menu}", fields)
            return _analysis_settled_response(session, fields, intro)
        if result.status == catalog.AMBIGUOUS:
            _store_test_menu_options(fields, result.tests)
            fields["_test_menu_adds_to_profile"] = True
            fields.pop("_awaiting_additional_test", None)
            return _base_route_response(
                _test_area_suggestion_reply(result.area or "lo que buscas", result.tests), fields
            )
        # Sin match por nombre pero menciona un ÁREA ('necesito una prueba de orina'):
        # ofrecer las opciones reales de esa área marcadas para AGREGAR, en vez de la
        # pregunta seca '¿cuál?' (prueba real chat 4).
        area_resp = _area_options_for_profile_addition(fields, user_message, require_question=False)
        if area_resp:
            fields.pop("_awaiting_additional_test", None)
            return area_resp

    # 5) Quiere agregar pero no dijo cuál (un 'sí' suelto o 'personalizar').
    if _is_affirmative_text(user_message) or _is_profile_customization_request(user_message):
        fields["_awaiting_additional_test"] = "add"
        return _base_route_response("Claro. ¿Qué análisis quieres agregar? Decime el nombre o el código.", fields)

    # 6a) Mensaje largo que no encaja en NADA de la oferta: trae otra intención (cambiar el
    # cliente, corregir un dato…) — que lo lea el MODELO y actúen las señales (3.3), en vez
    # de tragarlo con la re-pregunta de la oferta.
    if len(_tokenize(user_message)) > 8:
        return None

    # 6) No se entendió: aclarar sin perder el estado ni cerrar a ciegas.
    return _base_route_response(
        "¿Quieres agregar algún análisis más (decime cuál) o seguimos con el pago?", fields
    )



def _enforce_extra_analysis_offer(session: dict, ai_response: dict, prev_fields: dict) -> dict:
    """Vía del modelo: cuando el AI captura el análisis directamente (texto libre) y solo
    falta el pago, ofrecer una vez agregar otro/personalizar antes de seguir, igual que las
    vías de selección por menú. La respuesta a la oferta la maneja `_handle_extra_analysis_answer`."""
    if ai_response.get("intent") != "route_scheduling":
        return ai_response
    fields = ai_response.get("captured_fields", {})
    if not (session.get("client_id") or fields.get("_client_found")):
        return ai_response
    if fields.get("_offering_extra_analysis") or fields.get("payment_method"):
        return ai_response
    has_analysis = bool(fields.get("exam_type") or fields.get("selected_tests") or fields.get("_selected_profile_code"))
    # Menú PEGADO que ya no aplica (ERR-060): si la orden YA tiene análisis, un menú arrastrado
    # de un turno anterior (idéntico al de prev = vino por carry_over) es basura de estado y se
    # descarta para que no inhiba la oferta. Un menú puesto EN ESTE turno (difiere de prev) es
    # una pregunta legítima al cliente —p. ej. el menú de área del grounding— y se respeta.
    if has_analysis:
        for k in ("_profile_menu_options", "_test_menu_options"):
            if fields.get(k) and fields.get(k) == prev_fields.get(k):
                fields.pop(k, None)
        if not fields.get("_test_menu_options"):
            fields.pop("_test_menu_adds_to_profile", None)
    # No interferir si hay un menú/selección de análisis a medio resolver.
    if (fields.get("_test_menu_options") or fields.get("_profile_menu_options")
            or fields.get("_test_menu_adds_to_profile") or fields.get("_diagnostic_label")):
        return ai_response
    if not has_analysis:
        return ai_response
    analysis_new = (
        (fields.get("exam_type") or None) != (prev_fields.get("exam_type") or None)
        or _as_text_items(fields.get("selected_tests")) != _as_text_items(prev_fields.get("selected_tests"))
        or fields.get("_selected_profile_code") != prev_fields.get("_selected_profile_code")
    )
    # Con el análisis recién fijado, este enforcer toma el turno SIEMPRE, falte lo que falte.
    # Antes solo entraba si ya no faltaba nada, y entre "se fijó el análisis" y "la orden está
    # completa" queda un hueco —la observación, que desde el 28/07 va después del análisis— en
    # el que mandaba el modelo. Ahí improvisaba "¿quieres agregar otro análisis?" y el flujo
    # daba vueltas sin llegar nunca al resumen. `_analysis_settled_response` decide qué
    # corresponde en cada caso: ofrecer, pedir el dato que falta, o resumir.
    if not analysis_new:
        return ai_response
    exam = fields.get("_selected_profile_name") or fields.get("exam_type")
    intro = f"Listo, queda {exam}." if exam else "Listo, lo anoto."
    # Códigos nuevos capturados este turno sin perfil base: mostrar QUÉ quedó registrado y
    # a qué precio (reporte 2026-07-16: 'Potasio y Sodio' se anotaban sin decir el valor).
    new_codes = [c for c in _as_text_items(fields.get("selected_tests"))
                 if c not in set(_as_text_items(prev_fields.get("selected_tests")))]
    if new_codes and not fields.get("_selected_profile_code"):
        try:
            rows = db.get_tests_by_codes(_as_text_items(fields.get("selected_tests")))
            new_rows = [r for r in rows if str(r.get("code")) in set(new_codes)]
            if new_rows:
                totals = calculate_custom_profile_total(rows)
                intro = (f"Listo, registro {_format_test_items(new_rows)}. "
                         f"{_estimated_total_text(totals)}")
        except Exception:  # informativo: si el catálogo no responde, queda el intro simple
            pass
    return _analysis_settled_response(session, fields, intro)



def _enforce_multiple_tests_capture(session: dict, ai_response: dict, prev_fields: dict,
                                    user_message: str = "") -> dict:
    """Si el cliente pidió varios análisis en un mismo mensaje y cada uno mapea
    1:1 a un test del catálogo, los registra de una vez como perfil personalizado
    en lugar de repreguntar el tipo de análisis (evita el bucle reportado). Si
    algún ítem es ambiguo o no existe, no toca nada: deja el flujo normal.

    `user_message` es el texto CRUDO del cliente y se usa para rescatar lo que el modelo dejó
    fuera de `exam_type` (ERR-076). Tiene default para no romper llamadas posicionales viejas."""
    if ai_response.get("intent") != "route_scheduling":
        return ai_response
    fields = ai_response.get("captured_fields", {})
    if not (session.get("client_id") or fields.get("_client_found")):
        return ai_response
    if (
        fields.get("selected_tests") is not None
        or fields.get("_diagnostic_label")
        or fields.get("_selected_profile_code")
    ):
        return ai_response

    candidate = fields.get("exam_type")
    if not candidate or candidate == prev_fields.get("exam_type"):
        return ai_response

    catalog_tests = db.list_catalog_tests(limit=5000)
    # Resolvedor unívoco: cada ítem debe resolver 1:1 a un test del catálogo (EXACT). Si
    # alguno es ambiguo/inexistente, resolve_tests no devuelve EXACT y se deja el flujo normal.
    result = None
    if len(_split_multiple_exam_items(candidate)) >= 2:
        exact = catalog.resolve_tests(candidate, catalog_tests, fields.get("species"))
        if exact.status == catalog.EXACT and len(exact.tests) >= 2:
            result = exact
    if result is None:
        # ERR-087 (chat real 'análisis de sangre u orina, sodio y potasio'): el modelo
        # resumió el pedido MIXTO a UN término vago en exam_type y la compuerta de arriba
        # ni miraba el mensaje real — sodio/potasio se perdían y el cliente tenía que
        # repetir todo. Si el exam_type no da 2+ ítems, se resuelve el MENSAJE CRUDO:
        # 2+ exactos (o 1+ exacto con términos de área pendientes) siguen el mismo camino
        # de ERR-076 (registrar los unívocos + encolar los ambiguos). Un análisis suelto
        # sin pendientes ('quiero un hemograma') queda en el flujo normal.
        raw = (user_message or "").strip()
        if not raw:
            return ai_response
        raw_result = catalog.resolve_tests(raw, catalog_tests, fields.get("species"),
                                           collect_partial=True)
        if not raw_result.tests or (len(raw_result.tests) < 2 and not raw_result.unresolved):
            return ai_response
        result = raw_result
    rows = result.tests

    totals = calculate_custom_profile_total(rows)
    fields["selected_tests"] = [r["code"] for r in rows]
    fields["removed_tests"] = []
    fields["exam_type"] = f"Perfil personalizado ({len(rows)} análisis)"

    intro = (
        f"Listo, registro {_format_test_items(rows)}. {_estimated_total_text(totals)}"
        if len(rows) == 1 else
        f"Listo, registro estos {len(rows)} análisis: {_format_test_items(rows)}. "
        f"{_estimated_total_text(totals)}"
    )
    # Pedido MIXTO en la PRIMERA captura (ERR-067d, chat real 'sodio potasio y orina'): los
    # de opción única (sodio, potasio) se absorben acá; los términos con OPCIONES de la misma
    # frase (orina, un prequirúrgico…) NO se pierden — se encolan en orden de pedido y
    # `_analysis_settled_response` los ofrece uno por uno vía `_offer_next_pending`.
    # ERR-076: acá se pasaba `candidate` (= exam_type, el texto NORMALIZADO por el modelo) a un
    # parámetro que se llama `user_message`. Si el modelo resumía exam_type a "Sodio, Potasio",
    # el prequirúrgico que el cliente había pedido en la misma frase no estaba en ese texto y se
    # perdía en silencio — con plata de por medio. Ahora manda el mensaje real del cliente.
    # `result.unresolved` (señal dura del resolvedor) tiene prioridad; el escaneo queda de red,
    # mismo molde señal-primero/tokens-de-red de C1/C2/C3.
    ambiguous = _scan_ambiguous_terms(fields, user_message or candidate)
    for item in result.unresolved:
        if item not in ambiguous:
            ambiguous.append(item)
    if ambiguous:
        fields["_pending_ambiguous_items"] = ambiguous
    return _analysis_settled_response(session, fields, intro)



def _enforce_loose_exam_catalog_resolution(ai_response: dict, prev_fields: dict) -> dict:
    """QA-1/QA-7 (2026-07-05): un análisis suelto capturado como TEXTO ('Coprológico $23k')
    se resuelve SIEMPRE contra el catálogo — selected_tests estructurado con código y
    precio reales, exam_type = 'código nombre'. Así el resumen, el valor estimado y el
    payload de la orden salen del catálogo y el modelo no puede inventar precios (la
    orden real quedó con $23k para un análisis de $12.000 y payload con precio 0).
    Solo actúa sobre exam_type NUEVO en el turno, sin perfil base ni estructura previa."""
    if ai_response.get("intent") != "route_scheduling":
        return ai_response
    fields = ai_response.get("captured_fields", {})
    exam = fields.get("exam_type")
    if (not exam or fields.get("_selected_profile_code")
            or _as_text_items(fields.get("selected_tests"))
            or fields.get("_diagnostic_label")
            or exam == (prev_fields or {}).get("exam_type")):
        return ai_response
    clean = _strip_price_text(str(exam))
    if not clean or "personalizado" in clean.lower():
        if clean and clean != exam:
            fields["exam_type"] = clean
        return ai_response
    # Un perfil ESPECÍFICO ('Prequirúrgico I', '152') se resuelve por su propio camino
    # (_resolve_profile_base_if_missing). Pero una CATEGORÍA genérica ('un perfil
    # prequirúrgico', 6 variantes) NO ancla a un perfil único: si se dejaba pasar, el texto
    # quedaba suelto sin código ni precio y se perdía del resumen (chat real 2026-07-17,
    # ERR-067e). Se ofrecen las variantes reales para que el cliente elija.
    if _looks_like_catalog_profile(clean):
        if not _looks_like_specific_profile_query(clean):
            try:
                menu_response = _category_profiles_menu_response(fields, clean)
            except Exception:
                menu_response = None
            if menu_response:
                return menu_response
        if clean != exam:
            fields["exam_type"] = clean
        return ai_response
    # Resolvedor unívoco: uno o varios análisis nombrados en el texto se estructuran con
    # su código y precio del catálogo. Solo se acepta match inequívoco (EXACT); un término
    # genérico/de área no se estructura a ciegas (cae al menú de categoría o al texto limpio).
    try:
        result = catalog.resolve_tests(clean, db.list_catalog_tests(limit=5000), fields.get("species"))
    except Exception:
        result = catalog.ResolveResult(catalog.NONE)
    if result.status == catalog.EXACT and result.tests:
        codes = [str(r.get("code")) for r in result.tests]
        fields["selected_tests"] = codes
        fields["removed_tests"] = []
        fields["exam_type"] = (f"{result.tests[0].get('code')} {result.tests[0].get('name')}"
                               if len(codes) == 1
                               else f"Perfil personalizado ({len(codes)} análisis)")
        return ai_response
    # Análisis genérico con varias variantes reales ('glucosa' → Ayunas / Pre y Pos /
    # Insulina-Glucosa): ofrecer las opciones para que el cliente elija, en vez de dejar el
    # texto suelto con precio $0 (QA modelo real: "una glucosa" cerraba mostrando $0).
    if result.status == catalog.AMBIGUOUS and result.tests:
        return _test_options_response(fields, result.tests, _test_area_suggestion_reply(clean, result.tests))
    # Una CATEGORÍA de perfiles armados ('PREQUIRURGICO') nunca pasa al resumen como
    # análisis sin precio: se ofrecen los perfiles reales de esa categoría para elegir
    # (QA re-test: la orden cerró con 'PREQUIRURGICO' pelado y payload en $0).
    try:
        menu_response = _category_profiles_menu_response(fields, clean)
    except Exception:
        menu_response = None
    if menu_response:
        return menu_response
    if clean != exam:
        fields["exam_type"] = clean  # sin match único: al menos sin precio inventado
    return ai_response



def _enforce_profile_customization_changes(ai_response: dict, prev_fields: dict, user_message: str) -> dict:
    fields = ai_response.get("captured_fields", {})
    if ai_response.get("intent") != "route_scheduling" or not fields.get("_profile_customizing"):
        return ai_response

    # Pregunta abierta por ÁREA mientras se ajusta el perfil ('qué análisis de orina
    # tienen'): listar las opciones de esa área para AGREGAR al perfil base, en vez de
    # ignorar la pregunta y repetir el resumen (bucle reportado en chat 4).
    if _profile_lists_unchanged(prev_fields, fields):
        area_response = _area_options_for_profile_addition(fields, user_message)
        if area_response:
            return area_response

    if _is_ambiguous_profile_change(user_message) and _profile_lists_unchanged(prev_fields, fields):
        return _base_route_response(
            "Para ajustarlo necesito el nombre o código exacto del análisis. ¿Cuál quieres agregar o quitar?",
            fields,
        )

    selected = _as_text_items(fields.get("selected_tests"))
    removed = _as_text_items(fields.get("removed_tests"))
    selected_changed = selected != _as_text_items(prev_fields.get("selected_tests"))
    removed_changed = removed != _as_text_items(prev_fields.get("removed_tests"))
    if not selected_changed and not removed_changed:
        return ai_response

    unknown = []
    if selected_changed and selected:
        selected_rows = db.get_tests_by_codes_or_names(selected)
        missing = _unknown_catalog_items(selected, selected_rows)
        if missing:
            unknown.extend(missing)
            fields["selected_tests"] = [item for item in selected if item not in missing]
    if removed_changed and removed:
        removed_rows = db.get_tests_by_codes_or_names(removed)
        missing = _unknown_catalog_items(removed, removed_rows)
        if missing:
            unknown.extend(missing)
            fields["removed_tests"] = [item for item in removed if item not in missing]

    if not unknown:
        return ai_response

    names = ", ".join(unknown)
    return _base_route_response(
        f"No encuentro {names} en el catálogo de análisis sueltos. ¿Me confirmás el nombre o código exacto?",
        fields,
    )



def _enforce_profile_exam_type_integrity(ai_response: dict) -> dict:
    """Invariante estructural (chat 4): con un perfil base elegido, exam_type es EXACTAMENTE
    el nombre del perfil y todo análisis agregado vive en selected_tests (código y precio
    reales del catálogo). Si el modelo anota un agregado como texto libre en exam_type
    ('Perfil Prequirúrgico I + Parcial de Orina $16k'), se resuelve contra el catálogo y
    se suma a la estructura; lo que no se resuelve se descarta del texto. Si exam_type
    quedó vacío por un menú lateral, se restaura desde el perfil. Así el resumen y el
    valor estimado salen SIEMPRE de la estructura y no pueden perder un agregado."""
    if ai_response.get("intent") != "route_scheduling":
        return ai_response
    fields = ai_response.get("captured_fields", {})
    code = fields.get("_selected_profile_code")
    name = fields.get("_selected_profile_name")
    if not code or not name:
        return ai_response
    exam = fields.get("exam_type")
    if not exam:
        if not fields.get("_correction_pending"):
            fields["exam_type"] = name
        return ai_response
    if exam == name:
        return ai_response
    extra = exam.replace(name, " ").replace(str(code), " ")
    extra = re.sub(r"\$\s*[\d.,]+\s*k?\b", " ", extra, flags=re.IGNORECASE)
    # Los análisis que el perfil YA INCLUYE (su descripción) no son agregados: si el
    # modelo escribe el nombre con descripción ("Perfil Parasitológico II: Coprológico
    # y Coproscópico"), esos ítems se descartan — sumarlos duplicaba lo incluido y el
    # total saltaba de $23.000 a $50.000 entre la confirmación y el cierre (QA re-test).
    desc_key = _catalog_item_key(fields.get("_selected_profile_description") or "")
    items = [
        item for item in _split_multiple_exam_items(extra)
        if len(_catalog_item_key(item)) >= 4
        and not (desc_key and _catalog_item_key(item) in desc_key)
    ]
    if items:
        try:
            rows = db.get_tests_by_codes_or_names(items)
        except Exception:
            rows = []
        already = set(_as_text_items(fields.get("selected_tests")))
        new_rows = [
            r for r in rows
            if str(r.get("code")) not in already
            and not (desc_key and _catalog_item_key(r.get("name")) in desc_key)
        ]
        if new_rows:
            _add_tests_to_order(fields, new_rows, "add")
    fields["exam_type"] = name
    return ai_response



def _enforce_profile_recommendation_help(session: dict, ai_response: dict, user_message: str, history: list[dict]) -> dict:
    """Si el cliente no sabe qué análisis pedir o pide una recomendación, y ya tenemos la
    especie, mostrar perfiles del catálogo de esa especie en una lista clara y
    seleccionable (con código y precio). Determinístico: el LLM improvisaba el formato
    (todo junto) y la selección quedaba sin código ni precio. También cubre el cambio de
    análisis en multiorden: limpia el análisis viejo antes de recomendar el nuevo."""
    if ai_response.get("intent") != "route_scheduling":
        return ai_response
    fields = ai_response.get("captured_fields", {})
    if not (session.get("client_id") or fields.get("_client_found")):
        return ai_response
    species = fields.get("species")
    if not species:
        return ai_response
    # Ya se está armando un perfil por otra vía (etiqueta diagnóstica, perfil a medida o un
    # menú de análisis individuales ya ofrecido): no interferir.
    if (fields.get("_diagnostic_label") or fields.get("selected_tests")
            or fields.get("_test_menu_options") or fields.get("_profile_menu_options")):
        return ai_response
    # Ajuste parcial ('el mismo pero sin X', 'agregale Y'): NO recomendar desde cero; eso lo
    # maneja la personalización del perfil base. Solo recomendamos ante un cambio total o
    # cuando el cliente no sabe qué pedir.
    if _wants_partial_analysis_change(user_message):
        return ai_response

    wants_reco = _wants_profile_recommendation(user_message)
    asked_exam = _detect_which_field_is_being_asked(history) == "exam_type"
    no_exam = not fields.get("exam_type") and not fields.get("_selected_profile_code")
    if not (wants_reco or (no_exam and asked_exam and _doesnt_know_what_to_ask(user_message))):
        return ai_response

    # Categoría nombrada (ej. 'prequirúrgico') -> perfiles armados de esa categoría (ERR-045).
    category_response = _category_profiles_menu_response(fields, user_message)
    if category_response:
        return category_response

    profiles = db.list_catalog_profiles_for_species(species, limit=6)
    if not profiles:
        return ai_response

    # Limpiar cualquier análisis previo: clave para el cambio de análisis en multiorden,
    # donde el perfil de la orden anterior (p. ej. felino) seguía pegado a un paciente
    # nuevo (p. ej. canino) y se colaba al resumen.
    fields["exam_type"] = None
    fields["selected_tests"] = None
    fields["removed_tests"] = None
    for key in ("_selected_profile_code", "_selected_profile_name", "_selected_profile_price",
                "_selected_profile_description", "_profile_detail_offered", "_correction_pending"):
        fields.pop(key, None)
    _store_profile_menu_options(fields, profiles)
    return _base_route_response(_format_profile_recommendation(
                species, profiles, fields.get("_client_favorite_profiles")), fields)



def _enforce_diagnostic_label_help(session: dict, ai_response: dict, user_message: str,
                                   prev_fields: dict, history: list[dict]) -> dict:
    """Si el cliente pide un perfil por necesidad diagnóstica (etiqueta: CARDIACO,
    SENIOR CANINO, HEPÁTICO, etc.) sugiere las pruebas que lo conforman y arranca
    un perfil personalizado para que el cliente escoja y agregue otras."""
    if ai_response.get("intent") != "route_scheduling":
        return ai_response
    fields = ai_response.get("captured_fields", {})
    if not (session.get("client_id") or fields.get("_client_found")):
        return ai_response
    # Ya se está armando un perfil o ya se sugirió una etiqueta en este flujo.
    if fields.get("selected_tests") is not None or fields.get("_diagnostic_label"):
        return ai_response
    # Y si el turno YA resolvió un perfil concreto del catálogo, la ayuda por etiqueta
    # diagnóstica no tiene nada que hacer: el cliente dijo exactamente qué quería. Sin este
    # guard, "perfil 956" resolvía el perfil y acto seguido esto lo borraba para ofrecer la
    # lista de la etiqueta FELINOS (el nombre del perfil contiene "felinos", y las etiquetas
    # se recorren alfabéticamente).
    if fields.get("_selected_profile_code"):
        return ai_response

    # Lo que el AI capturó en exam_type o, si lo dejó vacío y el bot acaba de pedir el
    # análisis, el propio mensaje del usuario (la lista no debe depender del modelo).
    candidate = _analysis_help_candidate(fields, prev_fields, user_message, history)
    if not candidate:
        return ai_response
    # Si pide un perfil de catálogo específico (con versión "I/II" o código),
    # respetar ese flujo; las etiquetas son para necesidades clínicas genéricas.
    if _looks_like_specific_profile_query(candidate):
        return ai_response
    label = db.find_diagnostic_label(candidate, species=fields.get("species"))
    # Si el catálogo tiene perfiles ARMADOS de esa categoría (ej. Prequirúrgico),
    # ofrecerlos primero; el armado a medida con pruebas sueltas queda como
    # alternativa que el propio menú menciona (ERR-045). Se intenta con la etiqueta
    # y también con el texto crudo: la etiqueta no matchea variantes con espacios
    # ('pre quirúrgico'), el matcher de categoría sí (ERR-048).
    menu_response = _category_profiles_menu_response(fields, label or candidate)
    if menu_response:
        return menu_response
    if not label:
        return ai_response
    tests = db.get_tests_for_label(label)
    if not tests:
        return ai_response

    fields["exam_type"] = None
    fields["selected_tests"] = []
    fields["removed_tests"] = []
    fields["_diagnostic_label"] = label
    reply = _diagnostic_label_suggestion_reply(label, tests)
    # Si en el MISMO mensaje también pidió análisis por área (otra categoría, ej. "perfil
    # renal y análisis de orina"), no lo perdemos: lo reconocemos para que el cliente lo
    # retome al cerrar este perfil. (El primer guardrail de categoría que captura inhibe
    # a los demás; sin esto, el segundo pedido se silenciaba — ver flujo R.)
    area, area_tests = db.find_tests_by_area(user_message, fields.get("species"))
    if area and area_tests:
        reply += f"\n\nTambién mencionaste {area.lower()}; apenas cerremos este perfil, recuérdamelo y lo vemos."
    return _base_route_response(reply, fields)



def _capture_mixed_codes(session: dict, fields: dict, ai_response: dict,
                         user_message: str, codigos_sueltos: list[str]) -> dict:
    """Registra en un solo turno los PERFILES y los ANÁLISIS que el cliente nombró por código.

    Reusa `_attach_profiles_by_code` (ERR-103), que ya sabe enganchar varios perfiles
    distinguiendo el base de los adicionales y —clave acá— **sin tocar los análisis ya
    registrados**. Los códigos que no son perfil se resuelven contra `catalog_tests` y se
    suman con el mismo mecanismo del pedido mixto de la ventana de oferta.
    """
    perfiles, repetidos = _attach_profiles_by_code(fields, user_message)
    if not perfiles and not repetidos:
        return ai_response

    partes = []
    if perfiles:
        partes.append(_format_profile_items(perfiles))

    tests = []
    if codigos_sueltos:
        try:
            tests = db.get_tests_by_codes(codigos_sueltos) or []
        except Exception:
            tests = []
        if tests:
            _add_tests_to_order(fields, tests, "add")
            partes.append(_format_test_items(tests))

    if not partes:
        return ai_response

    # La etiqueta diagnóstica ya no aplica: el cliente dijo exactamente qué quería.
    fields.pop("_diagnostic_label", None)
    fields.pop("_profile_menu_options", None)
    fields.pop("_test_menu_options", None)
    fields.pop("_awaiting_additional_test", None)
    return _analysis_settled_response(session, fields, f"Listo, registro {' y '.join(partes)}.")


def _enforce_catalog_profile_code_selection(session: dict, ai_response: dict, user_message: str) -> dict:
    if ai_response.get("intent") != "route_scheduling" or _is_profile_detail_question(user_message):
        return ai_response
    fields = ai_response.get("captured_fields", {})
    if not (session.get("client_id") or fields.get("_client_found")):
        return ai_response
    codes = _profile_codes_from_text(user_message)
    if not codes:
        return ai_response
    try:
        profiles = db.get_catalog_profiles_by_codes(codes, fields.get("species"))
    except Exception:
        return ai_response
    if not profiles:
        return ai_response

    # PEDIDO MIXTO en la primera captura: "perfil 956, 2016 y 1901" — un perfil y dos
    # análisis en la misma frase. Antes esto se perdía ENTERO: la rama de abajo resolvía el
    # perfil y hacía `selected_tests = None`, borrando los análisis del turno; después el
    # guard de la etiqueta diagnóstica borraba también el perfil. El cliente terminaba viendo
    # una lista de sugerencias y sin nada registrado (error de dinero, familia ERR-077/103).
    codigos_de_perfil = {str(p.get("code")) for p in profiles}
    codigos_sueltos = [c for c in codes if c not in codigos_de_perfil]
    if len(profiles) > 1 or codigos_sueltos:
        return _capture_mixed_codes(session, fields, ai_response, user_message, codigos_sueltos)

    fields["selected_tests"] = None
    fields["removed_tests"] = None
    fields.pop("_diagnostic_label", None)

    # Intención compuesta: 'el perfil 152 al que le quiero agregar un análisis extra'.
    # Fijar el perfil base y, en vez de saltar al pago, abrir el ajuste preguntando qué
    # agregar (o listar el área si ya la nombró). Solo cuando pide agregar/quitar y no
    # nombró el análisis concreto en el mismo mensaje.
    if _wants_partial_analysis_change(user_message):
        _store_selected_profile_fields(fields, profiles[0])
        fields.pop("_profile_menu_options", None)
        fields.pop("_test_menu_options", None)
        fields.pop("_correction_pending", None)
        name = fields.get("_selected_profile_name") or "el perfil"
        intro = f"Listo, parto del {name} ({_money(fields.get('_selected_profile_price'))})."
        return _selected_profile_addition_response(session, fields, user_message, intro)

    return _capture_profile_menu_selection(session, fields, profiles[0])

