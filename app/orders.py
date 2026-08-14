"""Armado y resumen de la ORDEN (Paso 3.4): agregar/quitar análisis, resúmenes de
confirmación y cierre, menús de categoría y capturas de selección de perfil."""
import re

from app import catalog, state
from app.config import DISCOUNT_TIERS, PEDIDOS_ENABLED
from app.text import (
    tokenize as _tokenize, money as _money, as_text_items as _as_text_items,
    catalog_item_key as _catalog_item_key, strip_price_text as _strip_price_text,
)
from app.flow import (
    base_route_response as _base_route_response, missing_route_field as _missing_route_field,
    missing_route_field_question as _missing_route_field_question,
    format_test_items as _format_test_items, estimated_total_text as _estimated_total_text,
    age_has_unit as _age_has_unit, route_ready_for_payment as _route_ready_for_payment,
    order_data_complete as _order_data_complete,
    extra_analysis_offer as _extra_analysis_offer,
    ROUTE_REQUIRED_FIELDS as _ROUTE_REQUIRED_FIELDS,
    order_required_fields as _order_required_fields,
    ROUTE_ORDER_FIELDS_BEFORE_PAYMENT as _ROUTE_ORDER_FIELDS_BEFORE_PAYMENT,
)
from app.detectors import (
    _PRICE_QUESTION_TOKENS,
    _TOTAL_QUESTION_TOKENS,
    _asks_for_area_options,
    _looks_like_catalog_profile,
    _named_analysis_terms,
    _profile_codes_from_text,
    _wants_partial_analysis_change,
)
from app.menus import (
    _store_test_menu_options, _store_profile_menu_options, _store_selected_profile_fields,
    _test_area_suggestion_reply, _profile_menu_option_lines, _profile_description_items,
    _format_profile_recommendation, _select_tests_from_menu,
)
from app.messages import EXTRA_ANALYSIS_OFFER, PAYMENT_METHOD_QUESTION
from app.rules import calculate_custom_profile_total, calculate_profile_adjusted_total
from app.services import db

CONFIRMATION_PHASE = state.Phase.CONFIRMACION.value




def _resolve_profile_base_if_missing(fields: dict) -> None:
    """Si el exam_type es un perfil del catálogo pero no quedó registrado el código/precio
    del perfil base (p. ej. el cliente lo eligió por texto vía el LLM y luego AGREGÓ análisis
    por el menú genérico, que perdía la base), resolver el perfil y fijar su base. Así el
    total cuenta el precio del PERFIL + los agregados, no solo los análisis agregados."""
    if fields.get("_selected_profile_code"):
        return
    exam = fields.get("exam_type") or ""
    if not _looks_like_catalog_profile(exam):
        return
    # Un perfil armado desde cero ("Perfil personalizado (N análisis)") no es del catálogo:
    # su total se calcula con sus análisis sueltos, no hay base que resolver.
    if "personalizado" in exam.lower():
        return
    # Resolver por CÓDIGO primero: el exam_type suele venir como "152-Perfil Prequirúrgico I"
    # (código + nombre). find_catalog_profile no matchea esa cadena combinada y el match por
    # nombre es ambiguo ("Perfil Prequirúrgico I" devolvía el X de $90k en vez del I de $24k).
    # El código del catálogo es la fuente determinística del precio correcto.
    profile = None
    codes = _profile_codes_from_text(exam)
    if codes:
        try:
            matches = db.get_catalog_profiles_by_codes(codes[:1], fields.get("species"))
        except Exception:
            matches = []
        profile = matches[0] if matches else None
    if not profile:
        try:
            profile = db.find_catalog_profile(exam, fields.get("species"))
        except Exception:
            profile = None
    if profile:
        fields["_selected_profile_code"] = profile.get("code")
        fields["_selected_profile_name"] = profile.get("name") or fields.get("exam_type")
        fields["_selected_profile_price"] = int(profile.get("price") or 0)
        fields["_selected_profile_description"] = profile.get("description") or ""



def _order_summary_lines(fields: dict, header: str) -> list[str] | None:
    if not all(fields.get(key) for key in _order_required_fields()):
        return None

    # Backstop de precio: asegurar que un perfil base elegido por texto tenga su código/precio
    # antes de calcular el total (si se agregaron análisis, no perder el valor del perfil).
    _resolve_profile_base_if_missing(fields)

    clinic_name = fields.get("clinic_name") or fields.get("_client_display_name") or "cliente registrado"
    analysis = fields.get("exam_type")
    if fields.get("_selected_profile_code"):
        # Con el CÓDIGO adelante, igual que la línea de "Perfiles adicionales" y que la orden
        # impresa. Sin él, el cliente que pidió "el perfil 986" no podía verificar en el
        # resumen que quedó ese y no otro — y es la línea más cara de la orden.
        analysis = (f"{fields['_selected_profile_code']} "
                    f"{fields.get('_selected_profile_name') or analysis} — "
                    f"{_money(fields.get('_selected_profile_price'))}")
    lines = [
        header,
        f"- Veterinaria: {clinic_name}",
        f"- Dirección de retiro: {fields.get('pickup_address')}",
        f"- Médico solicitante: {fields.get('requesting_doctor')}",
        (
            f"- Paciente: {fields.get('patient_name')} "
            f"({fields.get('species')}, {fields.get('breed')}, {fields.get('sex')}, {fields.get('patient_age')})"
        ),
        f"- Propietario: {fields.get('owner_name')}",
        f"- Análisis: {analysis}",
        f"- Observaciones: {fields.get('observations')}",
    ]
    # Con pedidos, la forma de pago es del PEDIDO y se muestra en su resumen, no en el de
    # cada orden: A3 pidió que el resumen de la orden no la incluya (decisión 011).
    if not PEDIDOS_ENABLED:
        lines.append(f"- Forma de pago: {fields.get('payment_method')}")

    if fields.get("_selected_profile_code"):
        added_rows = db.get_tests_by_codes_or_names(_as_text_items(fields.get("selected_tests")))
        removed_rows = db.get_tests_by_codes_or_names(_as_text_items(fields.get("removed_tests")))
        base_price = int(fields.get("_selected_profile_price") or 0)
        # ERR-077: el cliente eligió VARIOS perfiles del menú ("1, 3 y 6"). El primero es el
        # base; los demás viajan en _extra_profiles con su precio de catálogo. No pueden ir
        # en selected_tests: un código de perfil (103) NO resuelve como análisis, así que el
        # resumen los perdería y el total volvería a quedar corto.
        extra_profiles = fields.get("_extra_profiles") or []
        totals = calculate_profile_adjusted_total(
            base_price,
            [row["price"] for row in added_rows] + [int(p.get("price") or 0) for p in extra_profiles],
            [row["price"] for row in removed_rows],
        )
        if extra_profiles:
            lines.append(f"- Perfiles adicionales: {_format_test_items(extra_profiles)}")
        if added_rows:
            lines.append(f"- Agregados: {_format_test_items(added_rows)}")
        if removed_rows:
            lines.append(f"- Quitados: {_format_test_items(removed_rows)}")
        lines.append(f"- Valor estimado: {_money(totals['total'])}")
    elif fields.get("selected_tests"):
        rows = db.get_tests_by_codes(_as_text_items(fields.get("selected_tests")))
        totals = calculate_custom_profile_total(rows)
        if rows:
            lines.append(f"- Análisis incluidos: {_format_test_items(rows)}")
        # Con descuento por volumen, el desglose SIEMPRE visible: sin él, el total
        # parece un error de cálculo (reporte del usuario, 2026-07-06).
        if totals["discount"]:
            lines.append(f"- Subtotal: {_money(totals['subtotal'])}")
            lines.append(f"- Descuento por volumen: -{_money(totals['discount'])}")
        lines.append(f"- Valor estimado: {_money(totals['total'])}")

    return lines



def _route_confirmation_summary(fields: dict) -> str | None:
    lines = _order_summary_lines(fields, "Antes de registrar, te resumo la orden:")
    if lines is None:
        return None
    # La oferta de editar/agregar va ACÁ y no en un paso aparte. El paso que la hacía
    # ("¿quieres agregar otro análisis?") quedó huérfano el 28/07, cuando A3 pidió mover el
    # análisis ANTES de las observaciones: desde entonces, al fijar el análisis siempre falta
    # `observations`, así que `order_data_complete` es False y la oferta no se dispara nunca.
    # Este es el único momento donde el cliente ve la orden entera antes de que se registre,
    # y decirlo explícito es lo que pidió el usuario (2026-08-14: "nunca le preguntaron si
    # quería editar alguno de los datos o agregar otro análisis").
    # La subcadena "¿Confirmas estos datos?" se conserva a propósito: cuatro tests la
    # verifican y el prompt la nombra. El "(Sí / Corregir)" se va: era la parte que sonaba a
    # formulario y no mencionaba los análisis.
    # La oferta va PRIMERO y la pregunta ÚLTIMA. Al revés ("¿Confirmas estos datos? Si
    # quieres, puedes... agregar otro análisis.") un "Sí" queda genuinamente ambiguo —¿confirma
    # o quiere agregar?— y ni una persona sabría cuál: en la prueba en vivo del 2026-08-14 el
    # "Si" del cliente se leyó como "sí, quiero agregar otro" y la orden no se registró.
    lines.append("Si quieres cambiar algún dato o agregar otro análisis, decímelo.")
    lines.append("¿Confirmas estos datos?")
    return "\n".join(lines)



def _order_confirmation_response(fields: dict, intro: str = "") -> dict | None:
    """Lleva la orden a su CONFIRMACIÓN: resumen + '¿Confirmas estos datos?'.

    Devuelve None si todavía no hay con qué armar el resumen. Existe como función propia
    porque con pedidos hay dos caminos que desembocan acá —terminar de fijar el análisis y
    declinar la oferta de agregar otro— y el segundo antes iba a la pregunta de pago."""
    summary = _route_confirmation_summary(fields)
    if not summary:
        return None
    ai = _base_route_response(f"{intro}\n{summary}".strip(), fields)
    ai["phase"] = CONFIRMATION_PHASE
    return ai


def _route_closure_summary(fields: dict) -> str | None:
    lines = _order_summary_lines(fields, "Quedó registrado:")
    if lines is None:
        return None
    lines.append("Nuestro motorizado pasará a recoger la muestra.")
    return "\n".join(lines)



def _analysis_settled_response(session: dict, fields: dict, intro: str) -> dict:
    # Cola de ambiguos pendientes (pedido múltiple): antes de ofrecer/avanzar, continuar
    # con el SIGUIENTE término que el cliente pidió ('perfecto, ahora vamos con...').
    pending = _offer_next_pending(session, fields, intro)
    if pending:
        return pending
    """Respuesta única tras fijar o ajustar el análisis. Si la orden YA tiene análisis y lo
    único que falta es el pago, OFRECE agregar más (se repite tras cada agregado hasta que el
    cliente siga). Si faltan otros datos, pide el siguiente; si está todo, muestra el resumen.
    Centraliza el 'paso de agregar otro análisis' para todas las vías de captura (RESUELTO-017)."""
    has_analysis = bool(
        fields.get("exam_type") or fields.get("selected_tests") or fields.get("_selected_profile_code")
    )
    # `_order_data_complete` es el que sabe leer ese momento con y sin pedidos (ver flow.py).
    if has_analysis and _order_data_complete(session, fields):
        fields["_offering_extra_analysis"] = True
        return _base_route_response(f"{intro} {_extra_analysis_offer()}", fields)
    missing = _missing_route_field(session, fields)
    if missing:
        return _base_route_response(f"{intro} {_missing_route_field_question(missing)}", fields)
    confirmacion = _order_confirmation_response(fields, intro)
    if confirmacion:
        return confirmacion
    return _base_route_response(intro, fields)



def _add_tests_to_order(fields: dict, rows: list[dict], action: str) -> None:
    """Suma (action='add') o quita (action='remove') los análisis de `rows` sobre la
    orden en curso, conservando el perfil base si lo hay. Fuente única usada tanto por
    el ajuste en confirmación como por la selección de un menú de área para agregar."""
    selected = _as_text_items(fields.get("selected_tests"))
    removed = _as_text_items(fields.get("removed_tests"))

    # Sin perfil base y sin análisis aún: el exam_type actual es el primer análisis del
    # perfil personalizado; lo sembramos para no perderlo al agregar el siguiente.
    if not fields.get("_selected_profile_code") and not selected and action == "add":
        base_rows = db.get_tests_by_codes_or_names([fields.get("exam_type")])
        if len(base_rows) == 1:
            selected = [str(base_rows[0].get("code") or base_rows[0].get("name"))]

    for row in rows:
        code = str(row.get("code") or row.get("name"))
        if action == "remove":
            if code in selected:
                selected.remove(code)
            if fields.get("_selected_profile_code") and code not in removed:
                removed.append(code)
        else:
            if code not in selected:
                selected.append(code)
            if code in removed:
                removed.remove(code)

    fields["selected_tests"] = selected
    fields["removed_tests"] = removed if fields.get("_selected_profile_code") else []
    if not fields.get("_selected_profile_code") and selected:
        fields["exam_type"] = f"Perfil personalizado ({len(selected)} análisis)"



def _area_options_for_profile_addition(fields: dict, user_message: str,
                                        require_question: bool = True) -> dict | None:
    """Si el cliente, mientras ajusta un perfil, pide análisis de un ÁREA
    ('qué análisis de orina tienen'), devuelve el menú de esa área marcado para AGREGAR
    al perfil base (no reemplazarlo). Con require_question=False también cubre el pedido
    afirmativo ('quiero agregarle un análisis de orina'): la mención de un área NUNCA se
    resuelve a un test suelto por parecido de nombre ('orina' → Cortisol en Orina; chat 4)."""
    if require_question and not _asks_for_area_options(user_message):
        return None
    area, tests = db.find_tests_by_area(user_message, fields.get("species"), limit=10)
    if not area or not tests:
        return None
    _store_test_menu_options(fields, tests)
    fields["_test_menu_adds_to_profile"] = True
    fields.pop("_awaiting_additional_test", None)
    return _base_route_response(_test_area_suggestion_reply(area, tests), fields)



def _clear_field_for_correction(fields: dict, field: str) -> None:
    fields[field] = None
    if field == "pickup_address":
        fields["_address_confirmed"] = False
        fields["_address_confirmation_pending"] = False
    if field == "exam_type":
        fields["selected_tests"] = None
        fields["removed_tests"] = None
        for key in (
            "_selected_profile_code", "_selected_profile_name", "_selected_profile_price",
            "_selected_profile_description", "_profile_detail_offered",
            "_profile_detail_confirmed", "_profile_customizing", "_profile_options_offered",
        ):
            fields.pop(key, None)



def _format_category_profile_menu(category: str, profiles: list[dict]) -> str:
    """Menú de perfiles ARMADOS de una categoría del catálogo (ej. Prequirúrgico),
    seleccionable por número, código o nombre, con precios reales."""
    lines = [f"Para {category.lower()} tenemos estos perfiles armados:"]
    lines.extend(_profile_menu_option_lines(profiles))
    lines.append(
        "Decime el número o el nombre del que prefieras y lo registro. "
        "Si prefieres, también lo armamos a medida con pruebas sueltas."
    )
    return "\n".join(lines)



def _category_profiles_menu_response(fields: dict, category_text: str) -> dict | None:
    """Si el cliente nombró una categoría de perfiles armados del catálogo (ej.
    'prequirúrgico'), ofrecerlos en un menú seleccionable con códigos y precios reales,
    en vez de la lista genérica por especie o de pruebas sueltas (ERR-045). None si el
    texto no menciona ninguna categoría con perfiles."""
    profiles = db.list_catalog_profiles_matching_category(category_text, fields.get("species"))
    if not profiles:
        return None
    _clear_field_for_correction(fields, "exam_type")
    fields.pop("_diagnostic_label", None)
    fields.pop("_correction_pending", None)
    # ERR-076: este es el embudo por el que pasan TODOS los menús de categoría de perfiles.
    # Si el pedido traía varios ítems ("un prequirúrgico, sodio y potasio"), se guarda entero:
    # cuando el cliente elija el perfil llegará solo "el 1" y los sueltos se perderían.
    if len(catalog.split_items(category_text)) > 1:
        fields["_mixed_request_text"] = category_text
    _store_profile_menu_options(fields, profiles)
    category = profiles[0].get("category") or "ese perfil"
    return _base_route_response(_format_category_profile_menu(category, profiles), fields)



def _menu_for_ambiguous_term(fields: dict, term: str) -> str | None:
    """Arma el menú (tests de área o perfiles de categoría) para UN término ambiguo y lo
    deja seleccionable. Devuelve el texto del menú, o None si el término no abre opciones."""
    area, tests = db.find_tests_by_area(term, fields.get("species"), limit=10)
    if area and tests:
        _store_test_menu_options(fields, tests)
        fields["_test_menu_adds_to_profile"] = True
        return _test_area_suggestion_reply(area, tests)
    try:
        profiles = db.list_catalog_profiles_matching_category(term, fields.get("species"), limit=11)
    except Exception:
        profiles = []
    if profiles:
        _store_profile_menu_options(fields, profiles)
        lines = [f"Para {term.strip().lower()} tenemos estos perfiles armados:"]
        lines += _profile_menu_option_lines(profiles)
        lines.append("Decime el número o el nombre del que prefieras.")
        return "\n".join(lines)
    return None


def _scan_ambiguous_terms(fields: dict, user_message: str) -> list[str]:
    """Términos del mensaje que abren OPCIONES (área de tests o categoría de perfiles),
    en el ORDEN en que el cliente los dijo. Ignora lo ya resuelto inequívoco."""
    added_names = " ".join(str(t) for t in (fields.get("selected_tests") or []))
    terms = []
    # ERR-076: si el pedido trae VARIOS ítems y alguno abre opciones, se guarda el texto
    # original. Al elegir el cliente una opción llega "el 1", y sin el pedido completo los
    # análisis sueltos de la misma frase (sodio, potasio) se perdían al fijarse el perfil.
    if len(catalog.split_items(user_message)) > 1:
        fields["_mixed_request_text"] = user_message
    for item in catalog.split_items(user_message):
        area, tests = db.find_tests_by_area(item, fields.get("species"), limit=3)
        if area and tests:
            terms.append(item)
            continue
        try:
            if db.list_catalog_profiles_matching_category(item, fields.get("species"), limit=2):
                terms.append(item)
        except Exception:
            pass
    return terms


def _offer_next_pending(session: dict, fields: dict, intro: str) -> dict | None:
    """PASO A PASO por orden de pedido (feature 2026-07-17): si quedan términos ambiguos
    en cola de un pedido múltiple ('orina y un prequirúrgico'), al resolverse uno se ofrece
    el MENÚ del siguiente automáticamente, hasta drenar la cola."""
    queue = list(fields.get("_pending_ambiguous_items") or [])
    while queue:
        term = queue.pop(0)
        fields["_pending_ambiguous_items"] = queue
        menu = _menu_for_ambiguous_term(fields, term)
        if menu:
            return _base_route_response(
                f"{intro} Ahora vamos con lo siguiente que pediste:\n{menu}", fields,
            )
    fields.pop("_pending_ambiguous_items", None)
    return None


def _profile_addition_if_mentioned(session: dict, fields: dict, user_message: str, intro: str) -> dict | None:
    """Agregados mencionados JUNTO a otra cosa (elegir el perfil, un pedido mixto). Mira el
    CONTENIDO, no el verbo — 'le quiero ARRESTAR aparte orina sodio y potasio' (typo real)
    perdía todo el agregado. Un pedido MIXTO (área ambigua + tests nombrados en la misma
    frase) se DESCOMPONE: lo inequívoco se agrega ya con precio, y el área se ofrece como
    menú — antes el menú del área respondía primero y se tragaba sodio/potasio (chat real
    2026-07-17, pedidos DOS veces y ausentes de la orden). Devuelve None si el mensaje no
    menciona nada agregable."""
    added_txt = ""
    try:
        res = catalog.resolve_tests(user_message, db.list_catalog_tests(limit=5000),
                                    fields.get("species"), collect_partial=True)
    except Exception:
        res = None
    if res is not None and res.status == catalog.EXACT and res.tests:
        _add_tests_to_order(fields, res.tests, "add")
        added_txt = f" Agrego {_format_test_items(res.tests)}."
    # Términos con OPCIONES, en orden de pedido: el primero se ofrece ya; el resto queda en
    # cola y se ofrece paso a paso a medida que el cliente vaya eligiendo.
    ambiguous = _scan_ambiguous_terms(fields, user_message)
    if ambiguous:
        first, rest = ambiguous[0], ambiguous[1:]
        menu = _menu_for_ambiguous_term(fields, first)
        if menu:
            if rest:
                fields["_pending_ambiguous_items"] = rest
            fields.pop("_awaiting_additional_test", None)
            return _base_route_response(f"{intro}{added_txt}\n{menu}", fields)
    if added_txt:
        fields["_profile_customizing"] = False
        return _analysis_settled_response(session, fields, f"{intro}{added_txt}")
    return None


def _selected_profile_addition_response(session: dict, fields: dict, user_message: str, intro: str) -> dict:
    fields["_profile_customizing"] = True
    # Primero el CONTENIDO: tests nombrados y/o menú de área (pedidos mixtos incluidos).
    mentioned = _profile_addition_if_mentioned(session, fields, user_message, intro)
    if mentioned:
        return mentioned
    # Nombre/código concreto: el mensaje completo primero (match más específico); los
    # términos sueltos solo como fallback, para no sumar tests espurios por una palabra.
    extra = (db.get_tests_by_codes_or_names([user_message])
             or db.get_tests_by_codes_or_names(_named_analysis_terms(user_message)))
    if extra:
        _add_tests_to_order(fields, extra, "add")
        fields["_profile_customizing"] = False
        # Respuesta centralizada (RESUELTO-017): re-ofrece agregar más o avanza.
        return _analysis_settled_response(session, fields, f"{intro} Agrego {_format_test_items(extra)}.")
    fields["_awaiting_additional_test"] = "add"
    return _base_route_response(f"{intro} ¿Qué análisis quieres agregarle?", fields)



def _capture_profile_menu_selection(session: dict, fields: dict, option: dict, user_message: str = "",
                                    extra_profiles: list[dict] | None = None) -> dict:
    """Guarda el perfil elegido del menú de recomendación con su código, nombre y precio
    reales (para que el resumen muestre el valor) y avanza al siguiente dato faltante.

    ERR-077: `extra_profiles` son los OTROS perfiles del mismo menú que el cliente eligió en
    la misma frase ("1, 3 y 6"). Antes se descartaban en silencio y la orden se confirmaba
    por el precio de uno solo."""
    species = fields.get("species")
    full = db.get_catalog_profiles_by_codes([option["code"]], species)
    profile = full[0] if full else option
    _store_selected_profile_fields(fields, profile)
    fields.pop("_profile_menu_options", None)
    fields.pop("_test_menu_options", None)
    fields.pop("_correction_pending", None)
    # Siempre se reescribe: fijar un perfil base nuevo no puede arrastrar los adicionales de
    # una orden anterior (multiorden).
    fields.pop("_extra_profiles", None)
    intro = f"Listo, registro {profile.get('code')} {profile.get('name')} ({_money(profile.get('price'))})."
    if extra_profiles:
        codes = [str(p.get("code")) for p in extra_profiles]
        rows = db.get_catalog_profiles_by_codes(codes, species) or extra_profiles
        fields["_extra_profiles"] = [
            {"code": r.get("code"), "name": r.get("name"), "price": int(r.get("price") or 0)}
            for r in rows
        ]
        intro = f"{intro} También registro {_format_test_items(fields['_extra_profiles'])}."
    # ERR-076: el perfil venía de un pedido MIXTO ("un prequirúrgico, sodio y potasio"). El
    # mensaje de ahora es solo la elección ("el 1"), así que los sueltos de la frase original
    # se aplican acá, ya sobre el perfil base — que es el camino que sí funciona (flujo X).
    pedido_original = fields.pop("_mixed_request_text", "")
    if pedido_original:
        # Solo los análisis INEQUÍVOCOS del pedido original. NO se re-escanean los términos
        # ambiguos: el que abrió este menú es el perfil que el cliente acaba de elegir, y
        # volver a encolarlo dejaba la orden trabada pidiendo algo ya resuelto.
        try:
            res = catalog.resolve_tests(pedido_original, db.list_catalog_tests(limit=5000),
                                        fields.get("species"), collect_partial=True)
        except Exception:
            res = None
        pendientes = [t for t in (fields.get("_pending_ambiguous_items") or [])
                      if not db.list_catalog_profiles_matching_category(t, fields.get("species"))]
        if pendientes:
            fields["_pending_ambiguous_items"] = pendientes
        else:
            fields.pop("_pending_ambiguous_items", None)
        fields.pop("_pending_offer_count", None)
        if res is not None and res.status == catalog.EXACT and res.tests:
            _add_tests_to_order(fields, res.tests, "add")
            intro = f"{intro} Agrego {_format_test_items(res.tests)}."
    if user_message:
        # CONTENIDO primero (no el verbo): 'el 152 y arrestar aparte orina sodio y potasio'
        # agrega/ofrece aunque el verbo venga con typo. Un '152' pelado no menciona nada
        # agregable y sigue el camino normal.
        mentioned = _profile_addition_if_mentioned(session, fields, user_message, intro)
        if mentioned:
            return mentioned
        if _wants_partial_analysis_change(user_message):
            return _selected_profile_addition_response(session, fields, user_message, intro)
    return _analysis_settled_response(session, fields, intro)


# ── Respuesta de PRECIO con valores reales del catálogo (movido de agent.py, 3.4a) ────

def _format_tests_total(rows: list[dict]) -> str:
    """Lista los análisis con su precio y el total. Si hay descuento por volumen, lo muestra
    explícito (subtotal → descuento → total) para que el total no parezca incoherente con la
    suma de cada precio."""
    totals = calculate_custom_profile_total(rows)
    if totals["discount"]:
        return (
            f"{_format_test_items(rows)}. Subtotal {_money(totals['subtotal'])}, "
            f"descuento por volumen {_money(totals['discount'])} → total {_money(totals['total'])}."
        )
    return f"{_format_test_items(rows)}. Total: {_money(totals['total'])}."


def _catalog_price_answer(fields: dict, user_message: str) -> str | None:
    """Responde una pregunta de precio con valores REALES del catálogo, sin inventar:
    1) el total de los análisis ya elegidos ('¿cuánto serían todos?'),
    2) un análisis puntual nombrado en la pregunta ('¿cuánto sale el hemograma?'),
    3) el perfil ya seleccionado con su valor.
    Devuelve None si no es pregunta de precio o no hay con qué responder con certeza."""
    tokens = set(_tokenize(user_message))
    if not (tokens & _PRICE_QUESTION_TOKENS):
        return None

    # 1) Total de los análisis que el cliente ya está armando (perfil personalizado).
    selected_codes = _as_text_items(fields.get("selected_tests"))
    if selected_codes and (tokens & _TOTAL_QUESTION_TOKENS or len(selected_codes) >= 2):
        rows = db.get_tests_by_codes_or_names(selected_codes)
        if rows:
            return _format_tests_total(rows)

    # 2) Análisis nombrado(s) en la propia pregunta. Resolvedor unívoco (no fuzzy palabra por
    #    palabra: 'glucosa en ayunas' NO debe arrastrar 'Colesterol Total (Ayunas)'; QA extremo).
    #    collect_partial: cotiza los análisis que se nombran e ignora el ruido de la pregunta.
    price_result = catalog.resolve_tests(user_message, db.list_catalog_tests(limit=5000),
                                         fields.get("species"), collect_partial=True)
    rows = price_result.tests if price_result.status == catalog.EXACT else []
    if not rows:
        area, area_tests = db.find_tests_by_area(user_message, fields.get("species"))
        if area and area_tests:
            lines = [f"Para {area.lower()} tenemos estas opciones:"]
            for t in area_tests[:8]:
                lines.append(f"- {t.get('code')} {t.get('name')}: {_money(t.get('price'))}")
            lines.append("Dime cuál necesitas (número, nombre o código).")
            # Con un análisis/perfil en curso, la selección posterior SUMA a la orden.
            _store_test_menu_options(fields, area_tests[:8])
            if fields.get("_selected_profile_code") or _as_text_items(fields.get("selected_tests")):
                fields["_test_menu_adds_to_profile"] = True
            return "\n".join(lines)
    if not rows:
        terms = _named_analysis_terms(user_message)
        rows = db.get_tests_by_codes_or_names(terms) if terms else []
    if not rows:
        menu = fields.get("_test_menu_options") or []
        rows = _select_tests_from_menu(user_message, menu) if menu else []
    if rows:
        if len(rows) == 1:
            r = rows[0]
            return f"El {r.get('name')} tiene un valor de {_money(r.get('price'))}."
        return _format_tests_total(rows)

    # 3) Perfil ya elegido con su precio.
    price = fields.get("_selected_profile_price")
    name = fields.get("_selected_profile_name") or fields.get("exam_type")
    if price and name:
        return f"El valor de {name} es {_money(int(price))}."
    return None


def _price_answer_for_order(fields: dict, user_message: str) -> str | None:
    """Compat: precio REAL del análisis/perfil ya elegido al confirmar. Delega en
    `_catalog_price_answer` para cubrir también el análisis puntual y el total."""
    return _catalog_price_answer(fields, user_message)
