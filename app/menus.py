"""Armadores de menús y replies del catálogo (Paso 3.4).

Construyen los menús seleccionables (análisis por área, perfiles) y los textos de
recomendación/detalle. Dependen solo de flow/text/db/catálogo — desbloquean enforcers."""
import re

from app.text import tokenize as _tokenize, money as _money, as_text_items as _as_text_items,     catalog_item_key as _catalog_item_key
from app.flow import base_route_response as _base_route_response,     format_test_items as _format_test_items, estimated_total_text as _estimated_total_text
from app.detectors import _detect_which_field_is_being_asked, _last_bot_message, _asks_for_client_identity, _profile_codes_from_text, _wants_partial_analysis_change
from app.services import db




def _test_area_suggestion_reply(query: str, tests: list[dict]) -> str:
    # Lista NUMERADA: así el cliente puede elegir por número ("el 2", "el primero")
    # además de por nombre o código, y la selección se resuelve de forma determinística.
    lines = [f"Para {query.lower().strip()} tenemos estas opciones:"]
    for idx, t in enumerate(tests, start=1):
        price = t.get("price")
        suffix = f" (${int(price)//1000}k)" if price else ""
        lines.append(f"{idx}. {t.get('code')} {t.get('name')}{suffix}")
    lines.append("Decime el número (o el nombre) del que necesitas. Puedes elegir varios.")
    return "\n".join(lines)



def _store_test_menu_options(fields: dict, tests: list[dict]) -> None:
    """Guarda la lista de análisis que se le mostró al cliente, para resolver su
    selección ('el primero', 'el 2', '1601', 'parcial de orina') en el próximo turno.
    Los menús son MUTUAMENTE EXCLUYENTES: mostrar un menú de análisis descarta el de
    perfiles anterior — sin esto, un '1' posterior resolvía contra el menú VIEJO de
    perfiles y registraba un perfil no pedido pisando la orden (prueba real chat 4)."""
    fields.pop("_profile_menu_options", None)
    fields["_test_menu_options"] = [
        {"code": t.get("code"), "name": t.get("name"), "price": int(t.get("price") or 0)}
        for t in tests if t.get("code")
    ]



def _store_profile_menu_options(fields: dict, profiles: list[dict]) -> None:
    """Guarda el menú de perfiles ofrecido (código+precio reales). Mutuamente excluyente
    con el menú de análisis (misma razón que _store_test_menu_options)."""
    fields.pop("_test_menu_options", None)
    fields.pop("_test_menu_adds_to_profile", None)
    fields["_profile_menu_options"] = [
        {"code": p.get("code"), "name": p.get("name"), "price": int(p.get("price") or 0)}
        for p in profiles if p.get("code")
    ]



def _profile_lists_unchanged(prev_fields: dict, fields: dict) -> bool:
    return (
        _as_text_items(prev_fields.get("selected_tests")) == _as_text_items(fields.get("selected_tests"))
        and _as_text_items(prev_fields.get("removed_tests")) == _as_text_items(fields.get("removed_tests"))
    )



def _analysis_help_candidate(fields: dict, prev_fields: dict, user_message: str, history: list[dict]) -> str | None:
    """Término con el que buscar un área o etiqueta diagnóstica al responder el análisis.
    Prioriza lo que el AI capturó en exam_type (si es nuevo en este turno); si el AI lo
    dejó vacío pero el bot ACABA de pedir el análisis, usa el propio mensaje del usuario.
    Así la lista seleccionable no depende de que el modelo guarde el término (la regresión:
    el modelo improvisaba la lista en el texto y dejaba exam_type vacío → ver RESUELTO-016)."""
    candidate = fields.get("exam_type")
    if candidate and candidate != prev_fields.get("exam_type"):
        return candidate
    if (not candidate
            and _detect_which_field_is_being_asked(history) == "exam_type"
            and not _wants_partial_analysis_change(user_message)
            and not _profile_codes_from_text(user_message)):
        return user_message
    return None



def _test_options_response(fields: dict, tests: list[dict], reply: str) -> dict:
    fields["exam_type"] = None
    fields["selected_tests"] = []
    fields["removed_tests"] = []
    fields.pop("_test_menu_adds_to_profile", None)
    _store_test_menu_options(fields, tests)
    return _base_route_response(reply, fields)



def _store_selected_profile_fields(fields: dict, profile: dict) -> None:
    fields["exam_type"] = profile.get("name") or fields.get("exam_type")
    fields["_selected_profile_code"] = profile.get("code")
    fields["_selected_profile_name"] = profile.get("name") or fields.get("exam_type")
    fields["_selected_profile_price"] = int(profile.get("price") or 0)
    fields["_selected_profile_description"] = profile.get("description") or ""
    fields["_profile_detail_offered"] = True



def _profile_customization_reply(fields: dict) -> str:
    name = fields.get("_selected_profile_name") or fields.get("exam_type") or "perfil seleccionado"
    price = fields.get("_selected_profile_price")
    return (
        f"Perfecto, partimos del {name} con valor base {_money(price)}. "
        "Dime qué análisis quieres agregar o quitar."
    )



def _diagnostic_label_suggestion_reply(label: str, tests: list[dict]) -> str:
    lines = [f"Para un perfil {label.title()} suelo sugerir estas pruebas:"]
    for t in tests:
        price = t.get("price")
        suffix = f" (${int(price)//1000}k)" if price else ""
        lines.append(f"- {t.get('code')} {t.get('name')}{suffix}")
    lines.append(
        "¿Cuáles quieres incluir? Dime las que necesites y puedes agregar otras que no estén en la lista."
    )
    return "\n".join(lines)



def _format_profile_options_with_details(label: str | None, profiles: list[dict]) -> str:
    title = label or (profiles[0].get("category") if profiles else "ese perfil")
    lines = [f"Para {title}, estas son las combinaciones por análisis incluidos:"]
    for profile in profiles:
        code = profile.get("code") or ""
        name = profile.get("name") or "Perfil"
        description = profile.get("description") or "sin detalle registrado"
        lines.append(f"- {code} {name}: {description}. Valor: {_money(profile.get('price'))}.")
    lines.append(
        "No tienes que escoger solo por número: puedes decirme la combinación que quieres o los análisis que deseas incluir."
    )
    return "\n".join(lines)



def _client_identity_prompt_count(history: list[dict]) -> int:
    return sum(
        1 for msg in history
        if msg.get("role") == "bot" and _asks_for_client_identity(msg.get("content", ""))
    )



def _profile_menu_option_lines(profiles: list[dict]) -> list[str]:
    lines = []
    for idx, p in enumerate(profiles, start=1):
        desc = p.get("description")
        detail = f": {desc}" if desc else ""
        lines.append(f"{idx}. {p.get('code')} {p.get('name')}{detail} — {_money(p.get('price'))}")
    return lines



def _profile_description_items(description: str | None) -> list[str]:
    items = []
    current = []
    depth = 0
    for char in description or "":
        if char == "(":
            depth += 1
        elif char == ")" and depth > 0:
            depth -= 1

        if char == "," and depth == 0:
            item = "".join(current).strip()
            if item:
                items.append(item)
            current = []
        else:
            current.append(char)

    item = "".join(current).strip()
    if item:
        items.append(item)
    return items



def _catalog_row_matches_item(item: str, row: dict) -> bool:
    item_key = _catalog_item_key(item)
    code_key = _catalog_item_key(row.get("code"))
    name_key = _catalog_item_key(row.get("name"))
    return item_key == code_key or item_key == name_key or (len(item_key) >= 3 and item_key in name_key)



def _format_profile_recommendation(species: str, profiles: list[dict]) -> str:
    """Lista de perfiles recomendados para la especie en formato legible: una línea por
    perfil con código, análisis incluidos y precio. Seleccionable por número o nombre."""
    lines = [f"Para {species.lower()} te puedo recomendar estos perfiles:"]
    lines.extend(_profile_menu_option_lines(profiles))
    lines.append("Decime el número o el nombre del que prefieras y lo registro.")
    return "\n".join(lines)



def _profile_detail_reply(profile: dict) -> str:
    name = profile.get("name") or "perfil seleccionado"
    lines = [f"El {name} incluye estos análisis:"]
    for item in _profile_description_items(profile.get("description")):
        lines.append(f"- {item}")
    lines.append(f"Valor base: {_money(profile.get('price'))}.")
    lines.append("¿Lo dejamos así o quieres personalizarlo para agregar o quitar algún análisis?")
    return "\n".join(lines)



def _reply_asks_missing_field(reply: str, field: str) -> bool:
    if field == "client":
        return _asks_for_client_identity(reply)
    return _reply_asks_for_route_field(reply, field)



def _unknown_catalog_items(items: list[str], rows: list[dict]) -> list[str]:
    return [item for item in items if not any(_catalog_row_matches_item(item, row) for row in rows)]

