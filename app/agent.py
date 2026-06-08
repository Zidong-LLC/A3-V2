import re
from typing import Callable

from app.services import ai, db
from app.rules import TERMINAL_PHASES, calculate_custom_profile_total, calculate_profile_adjusted_total

CLIENT_LOOKUP_PROGRESS_MESSAGE = "Permíteme un momentico mientras reviso nuestros registros 🔍"

WELCOME_MESSAGE = (
    "Hola! Buen día, me alegra que nos visites.\n"
    "Bienvenido a A3 laboratorio clínico veterinario 🧪 🧫\n"
    "Atendemos clínicas y profesionales veterinarios registrados.\n\n"
    "¿Con qué te ayudamos hoy? Respóndeme con el número:\n"
    "1. Programar análisis y recogida de muestra\n"
    "2. Consultar resultados\n"
    "3. Pagos\n"
    "4. Otro"
)

FINAL_USER_MESSAGE = (
    "A3 trabaja directamente con clínicas y profesionales veterinarios registrados. "
    "Para procesar muestras o programar recogidas, por favor gestiona la solicitud a través de tu veterinaria."
)

CLIENT_IDENTIFICATION_REQUIRED_MESSAGE = (
    "Para gestionar pedidos, A3 atiende clínicas y profesionales veterinarios registrados. "
    "Para continuar necesito una de estas dos opciones: 1) el NIT, o 2) el nombre exacto de la veterinaria o médico veterinario."
)

CLIENT_NOT_FOUND_MESSAGE = (
    "En este momento no encuentro el cliente registrado en nuestra base de datos.\n"
    "Para poder coordinar el retiro de muestras, primero necesitamos realizar el registro del cliente.\n"
    "Te voy a comunicar con atención al cliente para que puedan ayudarte con este proceso."
)

CLIENT_SEARCH_FAILED_MESSAGE = (
    "No encuentro ningún cliente registrado con ese dato.\n"
    "¿Eres cliente nuevo?"
)

CLIENT_RETRY_NOT_FOUND_MESSAGE = (
    "Tampoco encuentro un cliente registrado con ese dato. "
    "¿Me confirmas si es cliente nuevo para ponerte en contacto con atención al cliente?"
)

CLIENT_IDENTIFIER_RETRY_MESSAGE = (
    "Para ubicar el cliente registrado, compárteme el NIT o el nombre exacto de la veterinaria o médico veterinario."
)

POST_TERMINAL_GREETING_REPLY = "Hola. ¿En qué podemos ayudarte hoy?"

# Flujo B — captura de datos del cliente no registrado (cliente potencial).
NEW_CLIENT_INTRO = (
    "No te encontré en nuestro sistema, pero no te preocupes. 😊\n"
    "Vamos a dejar tus datos para que nuestro equipo te contacte.\n"
)
NEW_CLIENT_VERIFY_QUESTION = "¿Eres médico veterinario o representas una clínica veterinaria? (Sí / No)"
NEW_CLIENT_PRO_STEPS = ("clinic", "doctor", "address", "phone")
NEW_CLIENT_PARTICULAR_STEPS = ("pname", "pphone")
NEW_CLIENT_QUESTIONS = {
    "clinic":  "¿Cuál es el nombre de tu clínica o consultorio?",
    "doctor":  "¿Cuál es el nombre del médico veterinario?",
    "address": "¿Cuál es la dirección?",
    "phone":   "¿Cuál es el teléfono de contacto?",
    "pname":   "¿Cuál es tu nombre?",
    "pphone":  "¿Cuál es tu teléfono de contacto?",
}
NEW_CLIENT_FIELDS = {
    "clinic":  "_nc_clinic",
    "doctor":  "_nc_doctor",
    "address": "_nc_address",
    "phone":   "_nc_phone",
    "pname":   "_nc_name",
    "pphone":  "_nc_phone",
}
NEW_CLIENT_DONE_MESSAGE = (
    "Perfecto. ✅ Tus datos quedaron registrados.\n"
    "Un agente se comunicará contigo para completar el registro y tomar tu primera solicitud.\n"
    "En horario hábil te contactamos en un máximo de 30 minutos; fuera de horario, al inicio del día hábil siguiente."
)
NEW_CLIENT_PARTICULAR_DONE_MESSAGE = (
    "Gracias por tus datos. 🐾\n"
    "Ten en cuenta que A3 trabaja a través de clínicas y profesionales veterinarios registrados, "
    "pero un asesor se comunicará contigo para orientarte.\n"
    "En horario hábil te contactamos en un máximo de 30 minutos; fuera de horario, al inicio del día hábil siguiente."
)
_MENTION_PROFESSIONAL_TOKENS = frozenset({
    "veterinario", "veterinaria", "clinica", "clínica", "medico", "médico",
    "doctor", "doctora", "profesional", "consultorio", "hospital",
})
_NEW_CLIENT_FLOW_KEYS = (
    "_nc_capturing", "_nc_step", "_nc_kind",
    "_nc_clinic", "_nc_doctor", "_nc_address", "_nc_phone", "_nc_name",
)
_NC_FILLER_TOKENS = frozenset({
    "hola", "holi", "ola", "buenas", "buenos", "buen", "dia", "días", "dias",
    "tarde", "tardes", "noche", "noches", "hey", "hi", "saludos", "bien",
    "ok", "okay", "listo", "si", "no", "que", "tal", "como", "estas", "estás",
    "gracias", "please", "porfa",
})

def _nc_name_invalid(text: str) -> bool:
    stripped = text.strip()
    if len(stripped) < 2:
        return True
    if stripped.replace(" ", "").isdigit():
        return True
    return set(_tokenize(stripped)) <= _NC_FILLER_TOKENS

def _nc_phone_invalid(text: str) -> bool:
    import re as _re
    return len(_re.sub(r"\D", "", text)) < 6

ORDER_NUMBER_NEEDS_CLIENT_MESSAGE = (
    "Para darte el número de tu orden necesito identificarte primero. "
    "¿Me compartes el NIT o el nombre de la veterinaria o médico veterinario?"
)
ORDER_NUMBER_NOT_FOUND_MESSAGE = (
    "Todavía no encuentro una orden registrada a tu nombre. ¿Quieres que programemos una recogida?"
)

FAREWELL_REPLY = (
    "Con mucho gusto, para eso estamos! "
    "Si en algún momento necesitas algo más, acá seguimos. ¡Hasta luego, cuídate!"
)

_FAREWELL_TOKENS = frozenset({
    "gracias", "dale", "ok", "okay", "listo", "perfecto", "entendido",
    "chao", "chau", "bye", "hasta", "luego", "claro", "excelente", "genial",
    "bien", "super", "súper", "👍", "de nada", "con gusto", "bueno",
})

_CONTINUE_TOKENS = frozenset({
    "consulta", "pregunta", "quiero", "necesito", "puedo", "podria", "podrías", "podrias",
    "otra", "adicional", "tambien", "también", "informacion", "información", "perfil", "perfiles",
    "cotizar", "resultado", "resultados", "muestra", "ruta", "retiro", "agendar", "programar",
})

_GREETING_TOKENS = frozenset({"hola", "buenos", "buenas", "dias", "días", "tardes", "noches"})

# Consulta del número de orden ya creada (no confundir con crear una orden nueva)
_ORDER_QUERY_TOKENS = frozenset({"orden", "ordenes", "órdenes", "pedido", "pedidos", "solicitud", "radicado"})
_ORDER_NUMBER_TOKENS = frozenset({
    "numero", "número", "num", "codigo", "código", "rastreo", "rastrear",
    "seguimiento", "radicado", "referencia",
})
_ORDER_CREATE_TOKENS = frozenset({
    "crear", "crea", "nueva", "nuevo", "otra", "otro", "hacer", "haz", "programar",
    "generar", "agendar", "necesito", "quiero", "registrar",
})


def _is_order_number_query(text: str) -> bool:
    tokens = set(_tokenize(text))
    if tokens & _ORDER_CREATE_TOKENS:
        return False
    return bool(tokens & _ORDER_QUERY_TOKENS) and bool(tokens & _ORDER_NUMBER_TOKENS)


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


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9áéíóúñü]+", text.lower())


def _age_has_unit(value: str | None) -> bool:
    """La edad solo es válida si trae unidad (años/meses/días)."""
    return bool(set(_tokenize(value or "")) & _AGE_UNIT_TOKENS)


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


def _is_farewell(text: str) -> bool:
    tokens = _tokenize(text)
    if not tokens:
        return False

    words = set(tokens)
    if words & _CONTINUE_TOKENS:
        return False

    if len(tokens) <= 6 and all(token in _FAREWELL_TOKENS for token in tokens):
        return True

    return len(tokens) <= 3 and tokens[0] in _FAREWELL_TOKENS


def _is_greeting_only(text: str) -> bool:
    tokens = _tokenize(text)
    return bool(tokens) and len(tokens) <= 3 and all(token in _GREETING_TOKENS for token in tokens)


_AFFIRMATIVE_TOKENS = frozenset({
    "si", "sí", "ok", "okay", "listo", "perfecto", "claro", "bien",
    "correcto", "exacto", "dale", "sip", "aja", "ajá",
})

_NEGATIVE_TOKENS = frozenset({"no", "nop", "negativo", "incorrecto", "otra", "diferente"})

_HANDOFF_INTENTS = frozenset({"accounting", "new_client"})

PAYMENT_METHODS = frozenset({"contraentrega", "pago_linea"})
PAYMENT_METHOD_QUESTION = "Antes de cerrar, ¿cómo prefieres el pago: contraentrega con el motorizado o pago en línea?"
PAYMENT_ONLINE_HANDOFF_MESSAGE = (
    "Tu orden quedó registrada. Como elegiste pago en línea, nuestro equipo de contabilidad "
    "te contactará en breve para enviarte el link y procesar el pago. "
    "La recogida de la muestra sigue programada con normalidad."
)

AGE_QUESTION = "¿Qué edad tiene el paciente? Indícame número y unidad, por ejemplo: 5 años, 3 meses o 45 días."
_AGE_UNIT_TOKENS = frozenset({"año", "años", "ano", "anos", "mes", "meses", "dia", "dias", "día", "días"})

# Campos de texto libre que se normalizan a Mayúscula inicial (Sección 11 del spec).
# No incluye exam_type (códigos/nombres de perfil) ni observations (texto libre).
_TITLECASE_FIELDS = ("clinic_name", "patient_name", "species", "breed", "owner_name", "requesting_doctor")

# Confirmación editable previa al registro (Sección 7.1 del spec).
CONFIRMATION_PHASE = "fase_4_confirmacion"
CORRECTION_PROMPT = (
    "Claro. ¿Qué dato quieres corregir? "
    "(dirección, médico, paciente, especie, raza, sexo, edad, propietario, observaciones, análisis o forma de pago)"
)
_CORRECTION_TOKENS = frozenset({
    "corregir", "corrige", "corrijo", "cambiar", "cambia", "cambie", "modificar",
    "modifica", "editar", "edita", "arreglar", "incorrecto", "mal", "equivocado",
    "equivoqué", "equivoque", "no",
})
_CONFIRM_ORDER_TOKENS = frozenset({
    "si", "sí", "confirmo", "confirmar", "confirmado", "correcto", "exacto",
    "dale", "ok", "okay", "listo", "perfecto", "bien", "registralo", "regístralo",
})
_CORRECTION_FIELD_KEYWORDS = (
    (("direccion", "dirección", "domicilio", "retiro"), "pickup_address"),
    (("medico", "médico", "solicitante", "doctor", "doctora"), "requesting_doctor"),
    (("paciente",), "patient_name"),
    (("especie",), "species"),
    (("raza",), "breed"),
    (("sexo", "macho", "hembra"), "sex"),
    (("edad",), "patient_age"),
    (("propietario", "dueño", "dueno", "dueña", "duena"), "owner_name"),
    (("observacion", "observación", "observaciones"), "observations"),
    (("analisis", "análisis", "examen", "examenes", "exámenes", "perfil", "prueba", "pruebas"), "exam_type"),
    (("pago",), "payment_method"),
)
MAX_CLIENT_MATCH_OPTIONS = 5
_ROUTE_ORDER_FIELDS_BEFORE_PAYMENT = (
    "pickup_address", "requesting_doctor",
    "patient_name", "species", "breed", "sex", "patient_age",
    "owner_name", "observations", "exam_type",
)
_ROUTE_REQUIRED_FIELDS = _ROUTE_ORDER_FIELDS_BEFORE_PAYMENT + ("payment_method",)

_ORDER_RESET_FIELDS = frozenset({
    "exam_type", "patient_name", "species", "patient_age", "requesting_doctor",
    "owner_name", "breed", "sex", "observations", "payment_method", "selected_tests", "removed_tests",
    "_selected_profile_code", "_selected_profile_name", "_selected_profile_price",
    "_selected_profile_description", "_profile_detail_offered",
    "_profile_detail_confirmed", "_profile_customizing",
    "_profile_options_offered", "_diagnostic_label",
})

_IDENTIFICATION_RETRY_RESET_FIELDS = frozenset({
    "clinic_name", "tax_id", "pickup_address",
    "_client_found", "_client_not_found", "_client_display_name", "_client_address",
    "_handoff_announced", "_asked_if_new_client",
    "_address_confirmation_pending", "_address_confirmed",
    "_client_match_query", "_client_match_options",
})

_PROFILE_CUSTOMIZE_TOKENS = frozenset({
    "personalizar", "personalizarlo", "modificar", "ajustar", "ajustarlo",
    "agregar", "agrega", "añadir", "sumar", "incluir", "quitar", "quita",
    "sacar", "saca", "retirar", "remover", "cambiar",
})

_PROFILE_CONFIRM_TOKENS = frozenset({
    "si", "sí", "asi", "así", "dejalo", "dejarlo", "confirmo", "confirmado",
    "correcto", "exacto", "listo", "ok", "okay", "perfecto", "ese", "esa",
})

_AMBIGUOUS_PROFILE_TOKENS = frozenset({
    "ese", "esa", "eso", "esos", "esas", "otro", "otra", "otros", "otras",
    "mismo", "misma", "mismos", "mismas",
})

_PROFILE_DETAIL_TOKENS = frozenset({
    "incluye", "incluyen", "contiene", "contienen", "trae", "traen",
    "detalle", "detalles", "detallar", "componentes", "composicion", "composición",
})

_PROFILE_SPECIFIC_SUFFIXES = frozenset({
    "i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x", "xi", "xii",
    "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12",
})

_FINAL_USER_PHRASES = (
    "cliente final", "persona particular", "soy particular", "soy dueño",
    "soy dueno", "soy el dueño", "soy el dueno", "soy propietario",
    "soy el propietario", "dueño de mascota", "dueno de mascota",
    "tutor de mascota", "mi mascota", "mi perro", "mi gato",
    "no soy veterinario", "no soy veterinaria", "no soy de una veterinaria",
    "no tengo veterinaria",
)

_ORDINAL_SELECTIONS = {
    "primera": 1, "primero": 1,
    "segunda": 2, "segundo": 2,
    "tercera": 3, "tercero": 3,
    "cuarta": 4, "cuarto": 4,
    "quinta": 5, "quinto": 5,
}

_NON_IDENTIFIER_TOKENS = frozenset({
    "paciente", "mascota", "perro", "gato", "examen", "analisis", "análisis",
    "muestra", "hemograma", "perfil", "llama", "resultado", "resultados",
})


def _strip_question_sentences(text: str) -> str:
    chunks = [c.strip() for c in re.split(r"(?<=[.!?])\s+", (text or "").strip()) if c.strip()]
    kept = [chunk for chunk in chunks if "?" not in chunk and "¿" not in chunk]
    return " ".join(kept).strip()


def _default_handoff_reply(handoff_area: str | None) -> str:
    if handoff_area == "contabilidad":
        return "Para este tema te voy a comunicar con contabilidad para que te ayuden."
    if handoff_area == "operaciones":
        return "Te voy a comunicar con atención al cliente para ayudarte con este proceso."
    return "Te voy a comunicar con el equipo correspondiente para ayudarte mejor."


def _money(value: int | None) -> str:
    return f"${int(value or 0):,} COP"


def _format_test_items(rows: list[dict]) -> str:
    if not rows:
        return "ninguno"
    return ", ".join(f"{r['code']}-{r['name']} ${int(r.get('price') or 0)//1000}k" for r in rows)


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


def _profile_detail_reply(profile: dict) -> str:
    name = profile.get("name") or "perfil seleccionado"
    lines = [f"El {name} incluye estos análisis:"]
    for item in _profile_description_items(profile.get("description")):
        lines.append(f"- {item}")
    lines.append(f"Valor base: {_money(profile.get('price'))}.")
    lines.append("¿Lo dejamos así o quieres personalizarlo para agregar o quitar algún análisis?")
    return "\n".join(lines)


def _profile_customization_reply(fields: dict) -> str:
    name = fields.get("_selected_profile_name") or fields.get("exam_type") or "perfil seleccionado"
    price = fields.get("_selected_profile_price")
    return (
        f"Perfecto, partimos del {name} con valor base {_money(price)}. "
        "Dime qué análisis quieres agregar o quitar."
    )


def _is_profile_customization_request(text: str) -> bool:
    return bool(set(_tokenize(text)) & _PROFILE_CUSTOMIZE_TOKENS)


def _is_profile_confirmation(text: str) -> bool:
    tokens = set(_tokenize(text))
    return bool(tokens & _PROFILE_CONFIRM_TOKENS) and not _is_profile_customization_request(text)


def _as_text_items(value) -> list[str]:
    if isinstance(value, list):
        raw_items = value
    elif isinstance(value, str):
        raw_items = [value]
    else:
        return []
    return [str(item).strip() for item in raw_items if str(item or "").strip()]


def _catalog_item_key(value) -> str:
    text = str(value or "").strip().lower()
    text = text.translate(str.maketrans("áéíóúüñ", "aeiouun"))
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


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


def _catalog_row_matches_item(item: str, row: dict) -> bool:
    item_key = _catalog_item_key(item)
    code_key = _catalog_item_key(row.get("code"))
    name_key = _catalog_item_key(row.get("name"))
    return item_key == code_key or item_key == name_key or (len(item_key) >= 3 and item_key in name_key)


def _unknown_catalog_items(items: list[str], rows: list[dict]) -> list[str]:
    return [item for item in items if not any(_catalog_row_matches_item(item, row) for row in rows)]


def _is_ambiguous_profile_change(text: str) -> bool:
    tokens = set(_tokenize(text))
    return bool(tokens & _PROFILE_CUSTOMIZE_TOKENS) and bool(tokens & _AMBIGUOUS_PROFILE_TOKENS)


def _is_profile_detail_question(text: str) -> bool:
    return bool(set(_tokenize(text)) & _PROFILE_DETAIL_TOKENS)


def _profile_codes_from_text(text: str) -> list[str]:
    codes = []
    for code in re.findall(r"\b\d{3,4}\b", text or ""):
        if code not in codes:
            codes.append(code)
    return codes


def _looks_like_specific_profile_query(value: str | None) -> bool:
    tokens = _tokenize(value or "")
    return bool(tokens and (tokens[-1] in _PROFILE_SPECIFIC_SUFFIXES or any(token.isdigit() for token in tokens)))


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


def _store_selected_profile_fields(fields: dict, profile: dict) -> None:
    fields["exam_type"] = profile.get("name") or fields.get("exam_type")
    fields["_selected_profile_code"] = profile.get("code")
    fields["_selected_profile_name"] = profile.get("name") or fields.get("exam_type")
    fields["_selected_profile_price"] = int(profile.get("price") or 0)
    fields["_selected_profile_description"] = profile.get("description") or ""
    fields["_profile_detail_offered"] = True


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


def _enforce_diagnostic_label_help(session: dict, ai_response: dict, user_message: str) -> dict:
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

    # Solo el análisis que el AI capturó (exam_type). No usar el mensaje suelto,
    # para no disparar la sugerencia cuando el cliente apenas confirma la clínica.
    candidate = fields.get("exam_type")
    if not candidate:
        return ai_response
    # Si pide un perfil de catálogo específico (con versión "I/II" o código),
    # respetar ese flujo; las etiquetas son para necesidades clínicas genéricas.
    if _looks_like_specific_profile_query(candidate):
        return ai_response
    label = db.find_diagnostic_label(candidate)
    if not label:
        return ai_response
    tests = db.get_tests_for_label(label)
    if not tests:
        return ai_response

    fields["exam_type"] = None
    fields["selected_tests"] = []
    fields["removed_tests"] = []
    fields["_diagnostic_label"] = label
    return _base_route_response(_diagnostic_label_suggestion_reply(label, tests), fields)


def _enforce_catalog_profile_help(session: dict, ai_response: dict, user_message: str, history: list[dict]) -> dict:
    if ai_response.get("intent") != "route_scheduling":
        return ai_response

    fields = ai_response.get("captured_fields", {})
    if not (session.get("client_id") or fields.get("_client_found")):
        return ai_response

    detail_question = _is_profile_detail_question(user_message)
    species = fields.get("species")

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


def _profile_lists_unchanged(prev_fields: dict, fields: dict) -> bool:
    return (
        _as_text_items(prev_fields.get("selected_tests")) == _as_text_items(fields.get("selected_tests"))
        and _as_text_items(prev_fields.get("removed_tests")) == _as_text_items(fields.get("removed_tests"))
    )


def _is_final_user_text(text: str) -> bool:
    normalized = " ".join(_tokenize(text))
    return any(phrase in normalized for phrase in _FINAL_USER_PHRASES)


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


def _escalate_unfound_client(fields: dict) -> dict:
    # El cliente dice no ser nuevo pero no aparece en la base: derivar a un humano
    # en vez de seguir pidiendo el identificador en bucle.
    fields["_handoff_announced"] = True
    fields["_blocked"] = True
    return {
        "reply": CLIENT_NOT_FOUND_MESSAGE,
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


def _client_identity_prompt_count(history: list[dict]) -> int:
    return sum(
        1 for msg in history
        if msg.get("role") == "bot" and _asks_for_client_identity(msg.get("content", ""))
    )


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
    lines = [f"Encontré varios clientes registrados con '{label}'. ¿Cuál es el correcto?"]
    for idx, match in enumerate(shown, start=1):
        name = match.get("clinic_name") or "Sin nombre"
        address = match.get("address") or "sin dirección registrada"
        lines.append(f"{idx}) {name} - {address}")
    lines.append("Responde con el número o el nombre exacto.")
    if has_more:
        lines.append("Si ninguna es la tuya, compárteme el NIT o un nombre más exacto.")
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


def _select_client_match(text: str, fields: dict) -> dict | None:
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

    text_key = _catalog_item_key(text)
    query_key = _catalog_item_key(fields.get("_client_match_query"))
    if not text_key or text_key == query_key:
        return None
    for option in options:
        name_key = _catalog_item_key(option.get("clinic_name"))
        if len(text_key) >= 4 and (text_key == name_key or text_key in name_key or name_key in text_key):
            return option
    return None


def _looks_like_catalog_profile(value: str | None) -> bool:
    text = (value or "").strip()
    if not text:
        return False
    tokens = set(_tokenize(text))
    return text.isdigit() or bool(tokens & {"perfil", "panel"})


def _base_route_response(reply: str, fields: dict) -> dict:
    return {
        "reply": reply,
        "phase": "fase_2_recogida_datos",
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


def _reset_order_fields(fields: dict) -> None:
    for field in _ORDER_RESET_FIELDS:
        fields.pop(field, None)
    fields.pop("_custom_profile_summary", None)
    fields.pop("_pending_intents", None)


def _start_followup_service_order_response(fields: dict) -> dict:
    return _base_route_response(
        "Perfecto, creamos otra orden de servicio para otro paciente. ¿Cuál es el médico solicitante?",
        fields,
    )


def _client_found_reply(fields: dict) -> str:
    name = fields.get("_client_display_name") or fields.get("clinic_name") or "el cliente"
    address = fields.get("_client_address") or fields.get("pickup_address")
    if address:
        return f"Perfecto, encontramos {name}. Tenemos como domicilio de retiro: {address}. ¿Es correcta?"
    return f"Perfecto, encontramos {name}, pero no veo dirección registrada. ¿Cuál es la dirección de retiro?"


def _confirms_new_client(text: str) -> bool:
    tokens = _tokenize(text)
    if not tokens or any(token == "no" for token in tokens):
        return False

    words = set(tokens)
    if "cliente" in words and "nuevo" in words:
        return True
    return len(tokens) <= 4 and bool(words & _AFFIRMATIVE_TOKENS) and not any(token.isdigit() for token in tokens)


def _claims_unregistered_client(text: str) -> bool:
    normalized = " ".join(_tokenize(text))
    phrases = (
        "no estoy registrado", "no estamos registrados", "no esta registrado",
        "no está registrado", "no estoy en la base", "no estamos en la base",
    )
    return any(phrase in normalized for phrase in phrases)


def _asks_if_new_client(reply: str) -> bool:
    return "cliente nuevo" in " ".join(_tokenize(reply))


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


def _is_affirmative_text(text: str) -> bool:
    words = set(_tokenize(text))
    return bool(words & _AFFIRMATIVE_TOKENS) and len(words) <= 5


def _is_negative_text(text: str) -> bool:
    words = set(_tokenize(text))
    return bool(words & _NEGATIVE_TOKENS) and len(words) <= 8


def _wants_another_service_order(text: str) -> bool:
    words = set(_tokenize(text))
    if not words or "no" in words:
        return False
    if words & _AFFIRMATIVE_TOKENS:
        return True
    return bool(words & {"otra", "orden", "servicio", "paciente", "animal", "muestra", "ruta"})


def _same_text(left: str | None, right: str | None) -> bool:
    return " ".join(_tokenize(left or "")) == " ".join(_tokenize(right or ""))


def _last_bot_message(history: list[dict]) -> str:
    for msg in reversed(history):
        if msg["role"] == "bot":
            return msg["content"]
    return ""


def _awaiting_client_identifier(history: list[dict]) -> bool:
    last_bot = _last_bot_message(history).lower()
    return "nit" in last_bot and (
        "veterinaria" in last_bot or "médico" in last_bot or "medico" in last_bot
        or "nombre" in last_bot or "cliente" in last_bot
    )


def _is_no_identifier_text(text: str) -> bool:
    words = set(_tokenize(text))
    return "no" in words and bool(words & {"se", "sé", "tengo", "dato", "ninguno"})


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
    if _is_no_identifier_text(text):
        return None
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


def _apply_identification_fallbacks(fields: dict, user_message: str, history: list[dict]) -> None:
    waiting_identifier = _awaiting_client_identifier(history)
    if not fields.get("tax_id"):
        tax_id = _extract_tax_id_candidate(user_message, allow_unlabeled=waiting_identifier)
        if tax_id:
            fields["tax_id"] = tax_id
    # Si el bot está pidiendo el identificador y el usuario da un nombre NUEVO
    # (distinto al actual), reemplazarlo y re-buscar. Esto evita quedar pegado a
    # una búsqueda anterior con demasiadas coincidencias.
    if waiting_identifier and not fields.get("tax_id"):
        clinic_name = _extract_clinic_name_candidate(user_message)
        if clinic_name and not _same_text(clinic_name, fields.get("clinic_name")):
            fields["clinic_name"] = clinic_name
            _clear_client_match_options(fields)
            fields.pop("_client_not_found", None)
            fields.pop("_client_found", None)


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
        return "Para avanzar, puedes decirme: 1) el análisis o perfil que van a enviar, o 2) si quieres ver opciones del catálogo."
    if {"medico", "médico", "solicitante"} & tokens:
        return "Para avanzar, dime el nombre del médico solicitante de la orden."
    if {"raza", "sexo", "edad", "propietario", "observaciones"} & tokens:
        return "Para avanzar, dime ese dato de la orden o indícame si no aplica."
    return "Para avanzar, dime el dato que tengas a mano o escribe 'hablar con alguien' y te comunico con el equipo."


def _avoid_repeated_question(ai_response: dict, history: list[dict]) -> dict:
    if ai_response.get("requires_handoff") or ai_response.get("phase") in TERMINAL_PHASES:
        return ai_response

    # Mientras se arma o personaliza un perfil, repetir "¿agregás otro análisis?"
    # es parte natural de la selección, no un bucle. No reescribir esas preguntas.
    fields = ai_response.get("captured_fields", {})
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
            ai_response["reply"] = _rephrased_repeated_question(ai_response["reply"])
            break
    return ai_response


def _asks_for_client_identity(reply: str) -> bool:
    tokens = set(_tokenize(reply))
    return "nit" in tokens and ("veterinaria" in tokens or "nombre" in tokens)


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
        ai_response["reply"] = "Ya tengo el cliente identificado. ¿Qué análisis o perfil van a enviar?"
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


def _reply_asks_for_route_field(reply: str, field: str) -> bool:
    text = " ".join(_tokenize(reply))
    if field == "requesting_doctor":
        return "medico solicitante" in text or "médico solicitante" in text
    if field == "exam_type":
        return (
            "que tipo de analisis" in text or "qué tipo de análisis" in text
            or "analisis o perfil exacto" in text or "análisis o perfil exacto" in text
            or "cual van a enviar" in text or "cuál van a enviar" in text
        )
    if field == "patient_name":
        return "nombre del paciente" in text
    if field == "species":
        return "canino felino" in text or "otra especie" in text
    if field == "breed":
        return "raza del paciente" in text
    if field == "sex":
        return "macho o hembra" in text
    if field == "patient_age":
        return "edad tiene" in text
    if field == "owner_name":
        return "nombre del propietario" in text
    if field == "observations":
        return "observacion" in text or "observación" in text or "observaciones" in text
    if field == "payment_method":
        return "contraentrega" in text and ("linea" in text or "línea" in text)
    return False


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


def _route_ready_for_payment(session: dict, fields: dict) -> bool:
    has_client = bool(session.get("client_id") or fields.get("_client_found"))
    has_route_data = all(fields.get(k) for k in _ROUTE_ORDER_FIELDS_BEFORE_PAYMENT)
    return has_client and has_route_data and not fields.get("_address_confirmation_pending")


def _missing_route_field(session: dict, fields: dict) -> str | None:
    if not (session.get("client_id") or fields.get("_client_found")):
        return "client"
    if fields.get("_address_confirmation_pending"):
        return "pickup_address"
    for field in _ROUTE_REQUIRED_FIELDS:
        if not fields.get(field):
            return field
        if field == "patient_age" and not _age_has_unit(fields.get(field)):
            return field
    return None


def _missing_route_field_question(field: str) -> str:
    if field == "client":
        return "¿Me compartes el NIT o el nombre de la veterinaria o médico veterinario para ver si está registrado?"
    if field == "pickup_address":
        return "¿Cuál es la dirección de retiro?"
    if field == "requesting_doctor":
        return "¿Cuál es el médico solicitante?"
    if field == "exam_type":
        return "Para avanzar necesito el análisis o perfil exacto. ¿Cuál van a enviar?"
    if field == "patient_name":
        return "¿Cuál es el nombre del paciente?"
    if field == "species":
        return "¿Es canino, felino u otra especie?"
    if field == "breed":
        return "¿Cuál es la raza del paciente?"
    if field == "sex":
        return "¿El paciente es macho o hembra?"
    if field == "patient_age":
        return AGE_QUESTION
    if field == "owner_name":
        return "¿Cuál es el nombre del propietario?"
    if field == "observations":
        return "¿Quieres dejar alguna observación para la orden o la registramos sin observaciones?"
    return PAYMENT_METHOD_QUESTION


def _prevent_incomplete_route_closure(session: dict, ai_response: dict, fields: dict) -> dict:
    if ai_response.get("intent") != "route_scheduling" or ai_response.get("phase") not in TERMINAL_PHASES:
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


def _enforce_payment_step(session: dict, ai_response: dict, fields: dict) -> dict:
    if ai_response.get("intent") != "route_scheduling":
        return ai_response

    if not _route_ready_for_payment(session, fields):
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

    ai_response["reply"] = PAYMENT_METHOD_QUESTION
    ai_response["phase"] = "fase_2_recogida_datos"
    ai_response["intent"] = "route_scheduling"
    ai_response["service_area"] = "route_scheduling"
    ai_response["requires_handoff"] = False
    ai_response["handoff_area"] = None
    ai_response["message_mode"] = "flow_progress"
    ai_response["pending_intents"] = ai_response.get("pending_intents", [])
    return ai_response


def _enforce_profile_detail_step(session: dict, ai_response: dict, fields: dict, user_message: str) -> dict:
    if ai_response.get("intent") != "route_scheduling":
        return ai_response
    if fields.get("_profile_detail_confirmed") or fields.get("_profile_customizing"):
        return ai_response
    if fields.get("selected_tests") is not None and not fields.get("_selected_profile_code"):
        return ai_response

    if fields.get("_profile_detail_offered"):
        if _is_profile_customization_request(user_message):
            fields["_profile_customizing"] = True
            if not isinstance(fields.get("selected_tests"), list):
                fields["selected_tests"] = []
            if not isinstance(fields.get("removed_tests"), list):
                fields["removed_tests"] = []
            return _base_route_response(_profile_customization_reply(fields), fields)
        if _is_profile_confirmation(user_message):
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


def _enforce_profile_customization_changes(ai_response: dict, prev_fields: dict, user_message: str) -> dict:
    fields = ai_response.get("captured_fields", {})
    if ai_response.get("intent") != "route_scheduling" or not fields.get("_profile_customizing"):
        return ai_response

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


def _order_summary_lines(fields: dict, header: str) -> list[str] | None:
    if not all(fields.get(key) for key in _ROUTE_REQUIRED_FIELDS):
        return None

    clinic_name = fields.get("clinic_name") or fields.get("_client_display_name") or "cliente registrado"
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
        f"- Análisis: {fields.get('exam_type')}",
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
        profile_name = fields.get("_selected_profile_name") or fields.get("exam_type")
        lines.append(f"- Perfil base: {profile_name} ({_money(base_price)})")
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
        lines.append(f"- Valor estimado: {_money(totals['total'])}")

    return lines


def _route_closure_summary(fields: dict) -> str | None:
    lines = _order_summary_lines(fields, "Quedó registrado:")
    if lines is None:
        return None
    lines.append("Nuestro motorizado pasará a recoger la muestra. ¿Necesitás crear otra orden de servicio para otro paciente o animal?")
    return "\n".join(lines)


def _route_confirmation_summary(fields: dict) -> str | None:
    lines = _order_summary_lines(fields, "Antes de registrar, te resumo la orden:")
    if lines is None:
        return None
    lines.append("¿Confirmas estos datos? (Sí / Corregir)")
    return "\n".join(lines)


def _is_correction_request(text: str) -> bool:
    return bool(set(_tokenize(text)) & _CORRECTION_TOKENS)


def _is_order_confirmation(text: str) -> bool:
    tokens = set(_tokenize(text))
    if tokens & _CORRECTION_TOKENS:
        return False
    return bool(tokens & _CONFIRM_ORDER_TOKENS)


def _detect_correction_field(text: str) -> str | None:
    tokens = set(_tokenize(text))
    for keywords, field in _CORRECTION_FIELD_KEYWORDS:
        if tokens & set(keywords):
            return field
    return None


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


def _enforce_confirmation_step(session: dict, ai_response: dict, fields: dict, previous_phase: str, user_message: str) -> dict:
    """Antes de registrar una orden completa, mostrar el resumen y pedir
    confirmación (Sí / Corregir). Solo deja cerrar cuando el usuario ya confirmó."""
    if ai_response.get("intent") != "route_scheduling":
        return ai_response
    if ai_response.get("message_mode") == "cancellation":
        return ai_response
    if ai_response.get("phase") not in TERMINAL_PHASES:
        return ai_response
    if _missing_route_field(session, fields):
        return ai_response
    # Ya se mostró el resumen y el usuario confirmó: dejar cerrar.
    if previous_phase == CONFIRMATION_PHASE and _is_order_confirmation(user_message):
        return ai_response

    summary = _route_confirmation_summary(fields)
    if not summary:
        return ai_response
    ai_response["reply"] = summary
    ai_response["phase"] = CONFIRMATION_PHASE
    ai_response["requires_handoff"] = False
    ai_response["handoff_area"] = None
    ai_response["message_mode"] = "flow_progress"
    return ai_response


def _apply_route_closure_summary(ai_response: dict) -> dict:
    if ai_response.get("message_mode") == "cancellation":
        return ai_response
    if ai_response.get("intent") != "route_scheduling" or ai_response.get("phase") != "fase_6_cierre":
        return ai_response
    summary = _route_closure_summary(ai_response.get("captured_fields", {}))
    if summary:
        ai_response["reply"] = summary
    return ai_response


def _append_courier_notification(reply: str, courier: dict | None) -> str:
    if not courier:
        return reply
    name = (courier.get("name") or "").strip()
    phone = (courier.get("phone") or "").strip()
    if not name and not phone:
        return reply
    if name and phone:
        notification = f"Motorizado asignado: {name} ({phone})."
    elif name:
        notification = f"Motorizado asignado: {name}."
    else:
        notification = f"Telefono del motorizado asignado: {phone}."
    return f"{reply}\n\n{notification}"


def _finalize_request(chat_id: str, session: dict, ai_response: dict, started_from_escalation: bool, previous_phase: str) -> dict:
    """Crea la solicitud en BD cuando el turno cierra/escala una orden nueva y
    decora el reply con el motorizado asignado y el número de orden."""
    new_phase = ai_response["phase"]
    should_create_request = (
        new_phase in TERMINAL_PHASES
        and previous_phase not in TERMINAL_PHASES
        and not started_from_escalation
        and ai_response.get("message_mode") != "cancellation"
    )
    if not should_create_request:
        return ai_response

    order_info = db.create_request(chat_id, session, ai_response)
    if ai_response.get("intent") == "route_scheduling" and session.get("client_id"):
        courier = db.get_courier_for_client(session["client_id"])
        ai_response["reply"] = _append_courier_notification(ai_response["reply"], courier)
        ai_response["reply"] = _append_order_number(ai_response["reply"], order_info)
    return ai_response


def _base_new_client_response(reply: str, fields: dict) -> dict:
    return {
        "reply": reply,
        "phase": "fase_2_recogida_datos",
        "intent": "new_client",
        "service_area": "new_client",
        "requires_handoff": False,
        "handoff_area": None,
        "captured_fields": fields,
        "confidence": 1.0,
        "message_mode": "flow_progress",
        "pending_intents": [],
        "resume_prompt": "",
    }


def _start_new_client_capture(fields: dict) -> dict:
    # Antes de tomar datos, verificar si es profesional veterinario o un particular.
    fields["_nc_capturing"] = True
    fields["_nc_step"] = "verify"
    return _base_new_client_response(NEW_CLIENT_INTRO + NEW_CLIENT_VERIFY_QUESTION, fields)


def _mentions_professional(text: str) -> bool:
    return bool(set(_tokenize(text)) & _MENTION_PROFESSIONAL_TOKENS)


def _new_client_steps(fields: dict) -> tuple:
    return NEW_CLIENT_PRO_STEPS if fields.get("_nc_kind") == "pro" else NEW_CLIENT_PARTICULAR_STEPS


def _new_client_summary(fields: dict) -> str:
    if fields.get("_nc_kind") == "particular":
        return (
            "Estos son tus datos:\n"
            f"- Nombre: {fields.get('_nc_name')}\n"
            f"- Teléfono: {fields.get('_nc_phone')}\n"
            "¿Son correctos? (Sí / Corregir)"
        )
    return (
        "Estos son tus datos:\n"
        f"- Clínica: {fields.get('_nc_clinic')}\n"
        f"- Médico: {fields.get('_nc_doctor')}\n"
        f"- Dirección: {fields.get('_nc_address')}\n"
        f"- Teléfono: {fields.get('_nc_phone')}\n"
        "¿Son correctos? (Sí / Corregir)"
    )


def _save_new_client_pending(fields: dict) -> None:
    if fields.get("_nc_kind") == "particular":
        db.create_pending_client_review(
            {"clinic_name": f"Particular: {fields.get('_nc_name')}", "phone": fields.get("_nc_phone"),
             "address": "Particular - pendiente", "billing_type": "cash", "is_active": False},
            {"source": "telegram", "status": "PARTICULAR - PENDIENTE", "kind": "particular",
             "name": fields.get("_nc_name"), "phone": fields.get("_nc_phone")},
        )
    else:
        db.create_pending_client_review(
            {"clinic_name": fields.get("_nc_clinic"), "phone": fields.get("_nc_phone"),
             "address": fields.get("_nc_address"), "billing_type": "cash", "is_active": False},
            {"source": "telegram", "status": "CLIENTE NUEVO - PENDIENTE DE REGISTRO", "kind": "profesional",
             "clinic_name": fields.get("_nc_clinic"), "doctor": fields.get("_nc_doctor"),
             "address": fields.get("_nc_address"), "phone": fields.get("_nc_phone")},
        )


def _new_client_done_response(fields: dict) -> dict:
    done_msg = NEW_CLIENT_DONE_MESSAGE if fields.get("_nc_kind") == "pro" else NEW_CLIENT_PARTICULAR_DONE_MESSAGE
    for key in _NEW_CLIENT_FLOW_KEYS:
        fields.pop(key, None)
    # Tras derivar al asesor, el bot deja de responder (queda en manos del equipo).
    fields["_blocked"] = True
    return {
        "reply": done_msg,
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


def _handle_new_client_capture(chat_id: str, fields: dict, user_message: str) -> str:
    step = fields.get("_nc_step")

    # Verificación inicial: ¿profesional veterinario o particular?
    if step == "verify":
        if _is_final_user_text(user_message) or (_is_negative_text(user_message) and not _mentions_professional(user_message)):
            fields["_nc_kind"] = "particular"
        elif _is_affirmative_text(user_message) or _mentions_professional(user_message):
            fields["_nc_kind"] = "pro"
        else:
            return _persist_turn(chat_id, user_message, _base_new_client_response(NEW_CLIENT_VERIFY_QUESTION, fields))
        first = _new_client_steps(fields)[0]
        fields["_nc_step"] = first
        return _persist_turn(chat_id, user_message, _base_new_client_response(NEW_CLIENT_QUESTIONS[first], fields))

    steps = _new_client_steps(fields)
    if step in steps:
        question = NEW_CLIENT_QUESTIONS[step]
        if step in ("phone", "pphone"):
            if _nc_phone_invalid(user_message):
                interp = ai.interpret_nc_step(question, user_message)
                if interp.get("action") == "save" and interp.get("value"):
                    value = interp["value"]
                else:
                    reply = interp.get("reply") or "Ese dato no parece un número de teléfono 📱 Por favor enviame solo los dígitos."
                    return _persist_turn(chat_id, user_message, _base_new_client_response(reply, fields))
            else:
                value = _extract_phone_candidate(user_message, allow_unlabeled=True) or user_message.strip()
        elif step in ("clinic", "doctor", "pname"):
            if _nc_name_invalid(user_message):
                interp = ai.interpret_nc_step(question, user_message)
                if interp.get("action") == "save" and interp.get("value"):
                    value = _titlecase_value(interp["value"])
                else:
                    reply = interp.get("reply") or question
                    return _persist_turn(chat_id, user_message, _base_new_client_response(reply, fields))
            else:
                value = _titlecase_value(user_message.strip())
        else:
            value = user_message.strip()
        fields[NEW_CLIENT_FIELDS[step]] = value

        idx = steps.index(step)
        if idx + 1 < len(steps):
            next_step = steps[idx + 1]
            fields["_nc_step"] = next_step
            ai_response = _base_new_client_response(NEW_CLIENT_QUESTIONS[next_step], fields)
        else:
            fields["_nc_step"] = "confirm"
            ai_response = _base_new_client_response(_new_client_summary(fields), fields)
        return _persist_turn(chat_id, user_message, ai_response)

    # step == "confirm"
    if _is_correction_request(user_message):
        first = steps[0]
        fields["_nc_step"] = first
        ai_response = _base_new_client_response(
            "Sin problema, empecemos de nuevo. " + NEW_CLIENT_QUESTIONS[first], fields
        )
        return _persist_turn(chat_id, user_message, ai_response)

    if _is_order_confirmation(user_message):
        _save_new_client_pending(fields)
        return _persist_turn(chat_id, user_message, _new_client_done_response(fields))

    # Ni corrección ni confirmación clara: re-mostrar el resumen.
    ai_response = _base_new_client_response(_new_client_summary(fields), fields)
    return _persist_turn(chat_id, user_message, ai_response)


def _persist_turn(chat_id: str, user_message: str, ai_response: dict) -> str:
    db.save_message(chat_id, user_message, "user")
    db.save_message(chat_id, ai_response["reply"], "bot")
    fields = ai_response.get("captured_fields", {})
    fields["_pending_intents"] = ai_response.get("pending_intents", [])
    ai_response["captured_fields"] = fields
    db.update_session(chat_id, ai_response)
    return ai_response["reply"]


def process_turn(chat_id: str, user_message: str, on_progress: Callable[[str], None] | None = None) -> str | None:
    session = db.get_or_create_session(chat_id)
    history = db.get_recent_messages(chat_id, limit=8)
    started_from_escalation = session.get("phase_current") == "fase_7_escalado"

    # Cliente final/particular ya identificado: A3 no le presta servicio y el
    # agente deja de responder (sin saludo, sin procesar el turno).
    if (session.get("captured_fields") or {}).get("_blocked"):
        return None

    # Primer mensaje: saludo exacto, sin llamar al AI
    if len(history) == 0:
        db.save_message(chat_id, user_message, "user")
        db.save_message(chat_id, WELCOME_MESSAGE, "bot")
        return WELCOME_MESSAGE

    # Despedida después de fase terminal: cerrar sin llamar al AI
    if session.get("phase_current") in TERMINAL_PHASES and _is_farewell(user_message):
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

    # Flujo B — captura de datos del cliente nuevo en curso (Sección 9).
    if prev_captured.get("_nc_capturing"):
        return _handle_new_client_capture(chat_id, prev_captured, user_message)

    # Confirmación editable de la orden (Sección 7.1): si el usuario pide corregir,
    # se limpia ese campo y se repregunta, sin volver a llamar al AI. La respuesta
    # afirmativa sigue el pipeline normal (el cierre lo permite _enforce_confirmation_step).
    if (session.get("phase_current") == CONFIRMATION_PHASE
            and session.get("intent_current") == "route_scheduling"
            and _is_correction_request(user_message)):
        field = _detect_correction_field(user_message)
        if field:
            _clear_field_for_correction(prev_captured, field)
            ai_response = _base_route_response(_missing_route_field_question(field), prev_captured)
        else:
            ai_response = _base_route_response(CORRECTION_PROMPT, prev_captured)
        return _persist_turn(chat_id, user_message, ai_response)

    if session.get("phase_current") in TERMINAL_PHASES and session.get("intent_current") == "route_scheduling":
        if _wants_another_service_order(user_message):
            _reset_order_fields(prev_captured)
            ai_response = _start_followup_service_order_response(prev_captured)
            ai_response["captured_fields"]["_pending_intents"] = []
            db.save_message(chat_id, user_message, "user")
            db.save_message(chat_id, ai_response["reply"], "bot")
            db.update_session(chat_id, ai_response)
            return ai_response["reply"]
        if _is_negative_text(user_message):
            db.save_message(chat_id, user_message, "user")
            db.save_message(chat_id, FAREWELL_REPLY, "bot")
            return FAREWELL_REPLY

    if session.get("client_id") and prev_captured.get("_client_not_found"):
        db.clear_client_from_session(chat_id)
        session["client_id"] = None

    if session.get("client_id") and prev_captured and not prev_captured.get("_client_found"):
        client = db.get_client_by_id(session["client_id"])
        if client:
            _store_client_context(prev_captured, client)
            session["captured_fields"] = prev_captured

    # Nueva orden en misma sesión: fase terminal + no es despedida -> limpiar datos de la orden anterior
    if session.get("phase_current") in TERMINAL_PHASES:
        _reset_order_fields(prev_captured)
        session["phase_current"] = "fase_1_clasificacion"
        session["intent_current"] = "unknown"
        pending = []

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
                    f"Base ${totals['base']:,} COP. "
                    f"Agregados: {_format_test_items(added_rows)}. "
                    f"Quitados: {_format_test_items(removed_rows)}. "
                    f"Total ${totals['total']:,} COP."
                )
            elif selected:
                added_rows = db.get_tests_by_codes(selected)
                totals = calculate_custom_profile_total(added_rows)
                session["_custom_profile_summary"] = (
                    f"PERFIL PERSONALIZADO EN CONSTRUCCIÓN ({totals['count']} análisis): {_format_test_items(added_rows)}. "
                    f"Subtotal ${totals['subtotal']:,} COP. Total ${totals['total']:,} COP."
                )
        elif not prev_fields.get("exam_type"):
            catalog_ctx = db.get_catalog_context(prev_fields.get("species"))
            labels = db.list_diagnostic_labels()
            if labels:
                catalog_ctx = (catalog_ctx or "") + (
                    "\nPerfiles sugeridos por necesidad diagnóstica (etiquetas): " + ", ".join(labels)
                )

    ai_response = ai.generate_turn(
        session=session,
        history=history,
        user_message=user_message,
        pending_intents=pending,
        catalog_context=catalog_ctx,
    )

    fields = ai_response.get("captured_fields", {})

    # Mantener metadata de turno anterior (campos con _)
    for k, v in prev_captured.items():
        if k.startswith("_") and k != "_pending_intents" and k not in fields:
            fields[k] = v

    _merge_existing_route_fields(prev_captured, fields)

    client = None
    skip_client_lookup = False
    if not session.get("client_id"):
        # El bot ya preguntó "¿eres cliente nuevo?": la siguiente respuesta es sí/no
        # a esa pregunta, no un nuevo nombre para volver a buscar. Sin esto, cualquier
        # mensaje corto ("Registrame", "Qué hacemos") se toma como veterinaria y la
        # búsqueda entra en bucle infinito de "no encuentro".
        if (
            prev_captured.get("_client_not_found")
            and prev_captured.get("_asked_if_new_client")
            and _asks_if_new_client(_last_bot_message(history))
            and not _provides_new_identifier(user_message, prev_captured)
        ):
            if _is_final_user_text(user_message):
                fields["clinic_name"] = None
                fields["tax_id"] = None
                _clear_client_match_options(fields)
                fields["_blocked"] = True
                return _persist_turn(chat_id, user_message, _unsupported_final_user_response(fields))
            if _is_negative_text(user_message):
                return _persist_turn(chat_id, user_message, _escalate_unfound_client(fields))
            return _persist_turn(chat_id, user_message, _start_new_client_capture(fields))

        _apply_identification_fallbacks(fields, user_message, history)
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
                if _confirms_new_client(user_message) or _claims_unregistered_client(user_message):
                    # Flujo B: capturar datos mínimos del cliente potencial.
                    return _persist_turn(chat_id, user_message, _start_new_client_capture(fields))
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
                    selected_client = _select_client_match(user_message, fields)
                    current_query = fields.get("clinic_name")
                    if selected_client:
                        client = selected_client
                        fields["clinic_name"] = client.get("clinic_name") or fields.get("clinic_name")
                        fields["tax_id"] = client.get("tax_id") or fields.get("tax_id")
                        _clear_client_match_options(fields)
                    elif current_query and not _same_text(current_query, previous_query):
                        _clear_client_match_options(fields)
                    else:
                        ai_response = _base_route_response(
                            _client_match_options_reply(previous_query, fields.get("_client_match_options") or []),
                            fields,
                        )
                        skip_client_lookup = True

            if not client and not skip_client_lookup:
                ai_response = _enforce_client_identification_gate(session, ai_response, history)
                fields = ai_response.get("captured_fields", fields)

    if not skip_client_lookup and prev_captured.get("_address_confirmation_pending"):
        if _is_negative_text(user_message):
            fields["pickup_address"] = None
            fields["_address_confirmation_pending"] = False
            fields["_address_confirmed"] = False
            ai_response = _base_route_response(
                "¿Cuál es la dirección correcta donde debemos retirar la muestra?",
                fields,
            )
        elif _is_affirmative_text(user_message):
            fields["pickup_address"] = prev_captured.get("pickup_address") or prev_captured.get("_client_address")
            fields["_address_confirmation_pending"] = False
            fields["_address_confirmed"] = True

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
            matches = db.find_client_matches(fields.get("clinic_name"), limit=MAX_CLIENT_MATCH_OPTIONS + 1)
            if len(matches) > 1:
                # Aunque haya muchas, mostrar siempre un listado (las primeras) y,
                # si hay más, invitar a afinar con NIT o nombre más exacto.
                has_more = len(matches) > MAX_CLIENT_MATCH_OPTIONS
                shown = matches[:MAX_CLIENT_MATCH_OPTIONS]
                _store_client_match_options(fields, fields.get("clinic_name"), shown)
                ai_response = _base_route_response(
                    _client_match_options_reply(fields.get("clinic_name"), shown, has_more=has_more),
                    fields,
                )
                skip_client_lookup = True
            elif len(matches) == 1:
                client = matches[0]

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
                    # Ya se preguntó y confirmó cliente nuevo -> iniciar Flujo B.
                    return _persist_turn(chat_id, user_message, _start_new_client_capture(fields))
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
            if registered_address and (not supplied_address or _same_text(supplied_address, registered_address)):
                fields["pickup_address"] = registered_address
                fields["_address_confirmation_pending"] = True
                fields["_address_confirmed"] = False
                ai_response = _base_route_response(_client_found_reply(fields), fields)
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

    ai_response = _enforce_diagnostic_label_help(session, ai_response, user_message)
    fields = ai_response.get("captured_fields", fields)
    ai_response = _enforce_catalog_profile_help(session, ai_response, user_message, history)
    fields = ai_response.get("captured_fields", fields)
    ai_response = _enforce_profile_detail_step(session, ai_response, fields, user_message)
    fields = ai_response.get("captured_fields", fields)
    ai_response = _enforce_payment_step(session, ai_response, fields)
    ai_response = _prevent_incomplete_route_closure(session, ai_response, fields)
    ai_response = _enforce_profile_customization_changes(ai_response, prev_captured, user_message)
    fields = ai_response.get("captured_fields", fields)
    _normalize_name_fields(fields)
    ai_response["captured_fields"] = fields
    ai_response = _apply_handoff_guardrails(ai_response)
    ai_response = _avoid_redundant_client_identity_question(session, ai_response)
    ai_response = _avoid_forbidden_route_question(session, ai_response)
    ai_response = _avoid_redundant_route_field_question(session, ai_response)
    ai_response = _avoid_repeated_question(ai_response, history)
    ai_response = _apply_route_closure_summary(ai_response)

    previous_phase = session.get("phase_current", "")
    ai_response = _enforce_confirmation_step(session, ai_response, fields, previous_phase, user_message)
    ai_response = _finalize_request(chat_id, session, ai_response, started_from_escalation, previous_phase)

    return _persist_turn(chat_id, user_message, ai_response)
