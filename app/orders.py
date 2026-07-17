"""Armado y resumen de la ORDEN (Paso 3.4): agregar/quitar análisis, resúmenes de
confirmación y cierre, menús de categoría y capturas de selección de perfil."""
import re

from app import catalog, state
from app.config import DISCOUNT_TIERS
from app.text import (
    tokenize as _tokenize, money as _money, as_text_items as _as_text_items,
    catalog_item_key as _catalog_item_key, strip_price_text as _strip_price_text,
)
from app.flow import (
    base_route_response as _base_route_response, missing_route_field as _missing_route_field,
    missing_route_field_question as _missing_route_field_question,
    format_test_items as _format_test_items, estimated_total_text as _estimated_total_text,
    age_has_unit as _age_has_unit, route_ready_for_payment as _route_ready_for_payment,
    ROUTE_REQUIRED_FIELDS as _ROUTE_REQUIRED_FIELDS,
    ROUTE_ORDER_FIELDS_BEFORE_PAYMENT as _ROUTE_ORDER_FIELDS_BEFORE_PAYMENT,
)
from app.detectors import (
    _asks_for_area_options,
    _looks_like_catalog_profile,
    _named_analysis_terms,
    _profile_codes_from_text,
    _wants_partial_analysis_change,
)
from app.menus import (
    _store_test_menu_options, _store_profile_menu_options, _store_selected_profile_fields,
    _test_area_suggestion_reply, _profile_menu_option_lines, _profile_description_items,
    _format_profile_recommendation,
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
    if not all(fields.get(key) for key in _ROUTE_REQUIRED_FIELDS):
        return None

    # Backstop de precio: asegurar que un perfil base elegido por texto tenga su código/precio
    # antes de calcular el total (si se agregaron análisis, no perder el valor del perfil).
    _resolve_profile_base_if_missing(fields)

    clinic_name = fields.get("clinic_name") or fields.get("_client_display_name") or "cliente registrado"
    analysis = fields.get("exam_type")
    if fields.get("_selected_profile_code"):
        analysis = f"{fields.get('_selected_profile_name') or analysis} — {_money(fields.get('_selected_profile_price'))}"
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
        f"- Forma de pago: {fields.get('payment_method')}",
    ]

    if fields.get("_selected_profile_code"):
        added_rows = db.get_tests_by_codes_or_names(_as_text_items(fields.get("selected_tests")))
        removed_rows = db.get_tests_by_codes_or_names(_as_text_items(fields.get("removed_tests")))
        base_price = int(fields.get("_selected_profile_price") or 0)
        totals = calculate_profile_adjusted_total(
            base_price,
            [row["price"] for row in added_rows],
            [row["price"] for row in removed_rows],
        )
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
    lines.append("¿Confirmas estos datos? (Sí / Corregir)")
    return "\n".join(lines)



def _route_closure_summary(fields: dict) -> str | None:
    lines = _order_summary_lines(fields, "Quedó registrado:")
    if lines is None:
        return None
    lines.append("Nuestro motorizado pasará a recoger la muestra.")
    return "\n".join(lines)



def _analysis_settled_response(session: dict, fields: dict, intro: str) -> dict:
    """Respuesta única tras fijar o ajustar el análisis. Si la orden YA tiene análisis y lo
    único que falta es el pago, OFRECE agregar más (se repite tras cada agregado hasta que el
    cliente siga). Si faltan otros datos, pide el siguiente; si está todo, muestra el resumen.
    Centraliza el 'paso de agregar otro análisis' para todas las vías de captura (RESUELTO-017)."""
    has_analysis = bool(
        fields.get("exam_type") or fields.get("selected_tests") or fields.get("_selected_profile_code")
    )
    if has_analysis and _missing_route_field(session, fields) == "payment_method":
        fields["_offering_extra_analysis"] = True
        return _base_route_response(f"{intro} {EXTRA_ANALYSIS_OFFER}", fields)
    missing = _missing_route_field(session, fields)
    if missing:
        return _base_route_response(f"{intro} {_missing_route_field_question(missing)}", fields)
    summary = _route_confirmation_summary(fields)
    if summary:
        ai = _base_route_response(f"{intro}\n{summary}", fields)
        ai["phase"] = CONFIRMATION_PHASE
        return ai
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
    _store_profile_menu_options(fields, profiles)
    category = profiles[0].get("category") or "ese perfil"
    return _base_route_response(_format_category_profile_menu(category, profiles), fields)



def _selected_profile_addition_response(session: dict, fields: dict, user_message: str, intro: str) -> dict:
    fields["_profile_customizing"] = True
    # Área mencionada (pregunta O pedido afirmativo): menú de esa área para elegir con
    # código y precio reales, antes que cualquier match difuso por nombre.
    area_response = _area_options_for_profile_addition(fields, user_message, require_question=False)
    if area_response:
        area_response["reply"] = f"{intro}\n{area_response['reply']}"
        return area_response
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



def _capture_profile_menu_selection(session: dict, fields: dict, option: dict, user_message: str = "") -> dict:
    """Guarda el perfil elegido del menú de recomendación con su código, nombre y precio
    reales (para que el resumen muestre el valor) y avanza al siguiente dato faltante."""
    species = fields.get("species")
    full = db.get_catalog_profiles_by_codes([option["code"]], species)
    profile = full[0] if full else option
    _store_selected_profile_fields(fields, profile)
    fields.pop("_profile_menu_options", None)
    fields.pop("_test_menu_options", None)
    fields.pop("_correction_pending", None)
    intro = f"Listo, registro {profile.get('code')} {profile.get('name')} ({_money(profile.get('price'))})."
    if user_message and _wants_partial_analysis_change(user_message):
        return _selected_profile_addition_response(session, fields, user_message, intro)
    return _analysis_settled_response(session, fields, intro)
