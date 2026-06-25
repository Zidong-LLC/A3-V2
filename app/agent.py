import re
import logging
from typing import Callable
from datetime import datetime

from app import billing
from app.config import ALEGRA_ENABLED, APP_TIMEZONE
from app.services import ai, db, alegra
from app.rules import TERMINAL_PHASES, calculate_custom_profile_total, calculate_profile_adjusted_total

logger = logging.getLogger(__name__)

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

CLIENT_NEW_REGISTRATION_MESSAGE = (
    "Como aún no estás registrado, el alta la debe hacer atención al cliente. "
    "Te voy a comunicar con ellos para que puedan ayudarte con ese proceso."
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

# Opción 2 del menú (consultar resultados). Todavía no se resuelve por este medio:
# la consulta de estados se habilitará cuando se integre la plataforma.
RESULTS_PENDING_MESSAGE = (
    "Por ahora la consulta de resultados y estados de muestra todavía no está disponible por este medio. "
    "La estamos integrando con nuestra plataforma y muy pronto vas a poder consultarlos por aquí 🙌.\n"
    "Si necesitas un resultado puntual, escríbenos y con gusto te comunicamos con el equipo. "
    "¿Te ayudo con algo más, como programar una recogida?"
)

# El usuario se confundió de opción o quiere volver a elegir: se reofrece el menú.
OPTION_RECONSIDER_MESSAGE = (
    "Tranquilo, sin problema 🙂. ¿Con qué te ayudo? Respóndeme con el número:\n"
    "1. Programar análisis y recogida de muestra\n"
    "2. Consultar resultados\n"
    "3. Pagos\n"
    "4. Otro"
)

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

# Oferta de agregar más análisis antes del pago. Se repite tras cada agregado hasta que el
# cliente decida seguir (decline o dé el método de pago). El "si ya está, seguimos con el
# pago" deja la salida clara para no caer en bucle.
EXTRA_ANALYSIS_OFFER = (
    "¿Quieres agregar otro análisis o perfil, o personalizar este? "
    "Si ya está, seguimos con el pago."
)

# Cierre cordial al final de una orden registrada: ofrecer otra orden o terminar.
CLOSING_PROMPT = (
    "Si necesitas crear otra orden para otro paciente, escríbeme: otra orden. "
    "Si eso es todo, quedamos atentos. 🙂"
)


def _payment_method_from_text(text: str) -> str | None:
    tokens = set(_tokenize(text))
    if "contraentrega" in tokens or "efectivo" in tokens:
        return "contraentrega"
    if "pse" in tokens or "transferencia" in tokens or "tarjeta" in tokens:
        return "pago_linea"
    if ({"pago", "pagar"} & tokens) and ({"linea", "línea", "online"} & tokens):
        return "pago_linea"
    return None


NO_COURIER_HANDOFF_MESSAGE = (
    "Recibimos la orden. En este momento no veo un motorizado asignado al cliente, "
    "así que operaciones la va a coordinar manualmente."
)

AGE_QUESTION = "¿Qué edad tiene el paciente? Indícame número y unidad, por ejemplo: 5 años, 3 meses o 45 días."
_AGE_UNIT_TOKENS = frozenset({"año", "años", "ano", "anos", "mes", "meses", "dia", "dias", "día", "días"})

# Campos de texto libre que se normalizan a Mayúscula inicial (Sección 11 del spec).
# No incluye exam_type (códigos/nombres de perfil) ni observations (texto libre).
_TITLECASE_FIELDS = ("clinic_name", "patient_name", "species", "breed", "owner_name", "requesting_doctor", "sex")

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
_SAME_AS_PREVIOUS_TOKENS = frozenset({
    "mismo", "misma", "mismos", "mismas", "igual", "iguales",
    "anterior", "antes", "previo", "repetir", "repetido",
    "repetimos", "igualito", "siempre", "costumbre",
})

# Señal de que un campo es lo que CAMBIA (no "el mismo"): "el mismo, solo CAMBIA el paciente".
_CHANGE_TOKENS = frozenset({
    "cambia", "cambiaba", "cambian", "cambiar", "cambie", "cambio", "cambió",
    "distinto", "distinta", "diferente", "otro", "otra", "menos", "excepto", "salvo",
})

_SAME_AS_PHRASES = (
    "el mismo", "la misma", "lo mismo", "los mismos", "las mismas",
    "el de siempre", "la de siempre", "lo de siempre", "como siempre",
    "el de costumbre", "lo de costumbre", "de siempre",
    "el de antes", "la de antes", "lo de antes",
    "igual que el", "igual que la", "igual que lo",
    "como el anterior", "como la anterior", "como lo anterior",
    "el anterior", "la anterior", "lo anterior",
    "mismo que", "misma que", "lo de la vez anterior",
    "lo de la orden anterior", "repetir", "lo mismo de",
    "igual al anterior", "igual a la anterior",
    "el del otro", "la del otro",
    "el de la orden pasada", "la de la orden pasada", "como la vez pasada",
    "de la vez pasada", "dejalo como antes", "déjalo como antes",
    "dejalo igual", "déjalo igual", "el de la otra", "la de la otra",
    "como la otra",
)

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

_FIELD_LABELS = {
    "requesting_doctor": "médico solicitante",
    "patient_name": "nombre del paciente",
    "species": "especie",
    "breed": "raza",
    "sex": "sexo",
    "patient_age": "edad",
    "owner_name": "nombre del propietario",
    "pickup_address": "dirección de retiro",
    "exam_type": "análisis o perfil",
    "observations": "observaciones",
    "payment_method": "forma de pago",
}

_CORRECTION_FIELD_KEYWORDS = (
    (("direccion", "dirección", "domicilio", "retiro"), "pickup_address"),
    (("medico", "médico", "solicitante", "doctor", "doctora"), "requesting_doctor"),
    (("paciente", "perro", "perra", "gato", "gata", "animal", "mascota"), "patient_name"),
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
    "agregar", "agrega", "agregarle", "agregale", "agregarlo", "añadir", "sumar", "incluir", "quitar", "quita",
    "sacar", "saca", "retirar", "remover", "cambiar",
})

_PROFILE_CONFIRM_TOKENS = frozenset({
    "si", "sí", "asi", "así", "dejalo", "dejarlo", "confirmo", "confirmado",
    "correcto", "exacto", "listo", "ok", "okay", "perfecto", "ese", "esa",
})

# Cierre EXPLÍCITO de un perfil personalizado armado desde cero. No incluye "sí"
# ni "ya" sueltos para no cerrar por error mientras el cliente navega el catálogo.
_CLOSE_PROFILE_TOKENS = frozenset({
    "cerramos", "cerrar", "cierra", "cierralo", "ciérralo", "cierre", "cerremos",
    "completo", "completa", "suficiente", "listo", "lista", "nada", "eso",
})
_CLOSE_PROFILE_PHRASES = (
    "asi esta", "asi nomas", "asi nada", "asi quedamos", "dejalo asi",
    "ya esta", "nada mas", "es todo", "eso es todo", "esos no mas", "esos nomas",
)

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
    "motivo", "motivos", "muerte", "muerto", "muerta", "fallecio", "falleció",
    "registrado", "registrados", "registrada", "registradas", "registrarme",
    "dije", "dicho",
    # Correcciones / confusión de opción: nunca son el NIT ni el nombre del cliente.
    "confundi", "confundí", "confundido", "confundida", "equivoque", "equivoqué",
    "equivoco", "equivocado", "equivocada", "opcion", "opción", "opciones", "menu", "menú",
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


def _wants_to_close_custom_profile(text: str) -> bool:
    if _is_profile_customization_request(text):
        return False
    normalized = " ".join(_tokenize(text))
    if any(phrase in normalized for phrase in _CLOSE_PROFILE_PHRASES):
        return True
    return bool(set(_tokenize(text)) & _CLOSE_PROFILE_TOKENS)


def _as_text_items(value) -> list[str]:
    if isinstance(value, list):
        raw_items = value
    elif isinstance(value, str):
        raw_items = [value]
    else:
        return []
    return [str(item).strip() for item in raw_items if str(item or "").strip()]


_EXAM_ITEM_SEPARATOR = re.compile(r",|;|\n|\b y \b|\b e \b|\+", re.IGNORECASE)


def _split_multiple_exam_items(text: str | None) -> list[str]:
    """Parte un texto de análisis en ítems individuales ('hemograma, química y
    urianálisis' -> 3 ítems). Devuelve >=2 solo si claramente hay varios."""
    if not text:
        return []
    items = []
    for part in _EXAM_ITEM_SEPARATOR.split(text):
        item = part.strip(" .,:;-")
        if len(item) >= 2:
            items.append(item)
    return items


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


_RECOMMENDATION_TOKENS = frozenset({
    "recomienda", "recomiendas", "recomiende", "recomienden", "recomiendan",
    "recomiendame", "recomiéndame", "recomendacion", "recomendación",
    "sugieres", "sugiere", "sugieran", "sugieren", "sugerencia", "sugerencias",
    "aconsejas", "aconseja", "conviene", "convienen", "convendria", "convendría",
})
_DOESNT_KNOW_PHRASES = (
    "no se", "no sé", "no estoy seguro", "no tengo claro", "ni idea",
    "no sabria", "no sabría", "no sé cuál", "no se cual",
)
_ANALYSIS_NOUN_TOKENS = frozenset({
    "analisis", "análisis", "examen", "examenes", "exámenes",
    "perfil", "perfiles", "prueba", "pruebas",
})
_ANALYSIS_CHANGE_SIGNAL_TOKENS = frozenset({
    "otro", "otra", "otros", "otras", "nuevo", "nueva", "distinto", "distinta",
    "diferente", "cambiar", "cambia", "cambie", "cambiarlo", "cambiamos",
})
# Verbos de AGREGAR/QUITAR análisis: marcan un ajuste PARCIAL del perfil base (no
# empezar de cero). Distinto de "cambiar el análisis por otro" (cambio total).
_ANALYSIS_ADD_REMOVE_TOKENS = frozenset({
    "agregar", "agrega", "agregale", "agrégale", "agregarle", "agregarlo", "añadir",
    "anadir", "añade", "añadile", "sumar", "suma", "sumale", "incluir", "incluye", "incluile",
    "quitar", "quita", "quitale", "quítale", "sacar", "saca", "sacale", "sácale",
    "retirar", "retira", "remover", "remueve",
})
# Marcadores de "mantener lo de antes, salvo un detalle" (incluye 'más' = agregar algo).
_PARTIAL_KEEP_MARKERS = frozenset({"pero", "salvo", "excepto", "menos", "sin", "aunque", "mas", "más"})


def _wants_profile_recommendation(text: str) -> bool:
    """¿El cliente pide que le recomendemos o sugiramos un análisis o perfil?"""
    return bool(set(_tokenize(text)) & _RECOMMENDATION_TOKENS)


def _wants_partial_analysis_change(text: str) -> bool:
    """¿El cliente quiere MANTENER el análisis/perfil anterior y solo ajustarlo
    (agregar o quitar pruebas), no empezar de cero? Ej.: 'el mismo pero sin coproscópico',
    'igual más glucosa', 'sacale estas dos'. En ese caso NO se limpia: se personaliza el
    perfil base por el camino existente (`_profile_customizing`)."""
    tokens = set(_tokenize(text))
    if tokens & _ANALYSIS_ADD_REMOVE_TOKENS:
        return True
    if (tokens & {"extra", "extras", "adicional", "adicionales"}
            and tokens & {"analisis", "análisis", "examen", "examenes", "exámenes", "prueba", "pruebas"}):
        return True
    if tokens & {"personalizar", "personalizarlo", "ajustar", "ajustarlo", "modificar"}:
        return True
    if (_is_same_as_previous(text) or tokens & _SAME_AS_PREVIOUS_TOKENS) and tokens & _PARTIAL_KEEP_MARKERS:
        return True
    return False


def _doesnt_know_what_to_ask(text: str) -> bool:
    """¿El cliente responde que no sabe qué análisis pedir o pide ayuda/opciones?"""
    lower = (text or "").lower()
    if any(p in lower for p in _DOESNT_KNOW_PHRASES):
        return True
    return bool(set(_tokenize(text)) & {
        "opciones", "ayuda", "ayudame", "ayúdame", "orienta", "orientame",
        "oriéntame", "muestrame", "muéstrame", "orientas",
    })


def _wants_to_change_analysis(text: str) -> bool:
    """¿El cliente quiere reemplazar el análisis/perfil por otro TOTALMENTE distinto
    (empezar el análisis de cero)? Ej.: 'con otro análisis', 'quisiste hacer otro análisis',
    'cambiemos el perfil'. NO aplica a un ajuste parcial ('el mismo pero sin X'): eso se
    mantiene y se personaliza, no se limpia."""
    if _wants_partial_analysis_change(text):
        return False
    tokens = set(_tokenize(text))
    return bool(tokens & _ANALYSIS_NOUN_TOKENS) and bool(tokens & _ANALYSIS_CHANGE_SIGNAL_TOKENS)


def _format_profile_recommendation(species: str, profiles: list[dict]) -> str:
    """Lista de perfiles recomendados para la especie en formato legible: una línea por
    perfil con código, análisis incluidos y precio. Seleccionable por número o nombre."""
    lines = [f"Para {species.lower()} te puedo recomendar estos perfiles:"]
    for idx, p in enumerate(profiles, start=1):
        desc = p.get("description")
        detail = f": {desc}" if desc else ""
        lines.append(f"{idx}. {p.get('code')} {p.get('name')}{detail} — {_money(p.get('price'))}")
    lines.append("Decime el número o el nombre del que prefieras y lo registro.")
    return "\n".join(lines)


def _select_profile_from_menu(text: str, options: list[dict]) -> dict | None:
    """Resuelve qué perfil eligió el cliente de la lista recomendada (número, ordinal,
    código o nombre). Un perfil es una sola elección: devuelve el primero que matchee."""
    picks = _select_tests_from_menu(text, options)
    return picks[0] if picks else None


def _selected_profile_addition_response(session: dict, fields: dict, user_message: str, intro: str) -> dict:
    fields["_profile_customizing"] = True
    area_response = _area_options_for_profile_addition(fields, user_message)
    if area_response:
        area_response["reply"] = f"{intro}\n{area_response['reply']}"
        return area_response
    extra = db.get_tests_by_codes_or_names(_named_analysis_terms(user_message))
    if extra:
        _add_tests_to_order(fields, extra, "add")
        missing = _missing_route_field(session, fields)
        reply = f"{intro} Agrego {_format_test_items(extra)}."
        if missing and missing != "exam_type":
            reply += f" {_missing_route_field_question(missing)}"
        return _base_route_response(reply, fields)
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
    if len(profiles) != 1:
        return ai_response
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
        price = int(row.get("price") or 0) // 1000
        lines.append(f"{idx}. {row.get('code')} {row.get('name')} ({category}) (${price}k)")
    lines.append("Dime el número, el nombre o el área que necesitas revisar.")
    return "\n".join(lines)


def _is_generic_blood_analysis(text: str | None) -> bool:
    tokens = set(_tokenize(text or ""))
    if not tokens or {"oculta", "oculto"} & tokens:
        return False
    return "sangre" in tokens and bool(tokens & {"analisis", "análisis", "examen", "prueba"})


def _is_catalog_overview_question(text: str | None) -> bool:
    tokens = set(_tokenize(text or ""))
    if not tokens:
        return False
    asks_catalog = bool(tokens & {"catalogo", "catálogo", "opciones", "tipos", "tipo", "hacen", "ofrecen", "puedo"})
    asks_analysis = bool(tokens & {"analisis", "análisis", "examen", "examenes", "exámenes", "prueba", "pruebas"})
    return asks_catalog and asks_analysis


def _test_options_response(fields: dict, tests: list[dict], reply: str) -> dict:
    fields["exam_type"] = None
    fields["selected_tests"] = []
    fields["removed_tests"] = []
    fields.pop("_test_menu_adds_to_profile", None)
    _store_test_menu_options(fields, tests)
    return _base_route_response(reply, fields)


def _store_test_menu_options(fields: dict, tests: list[dict]) -> None:
    """Guarda la lista de análisis que se le mostró al cliente, para resolver su
    selección ('el primero', 'el 2', '1601', 'parcial de orina') en el próximo turno."""
    fields["_test_menu_options"] = [
        {"code": t.get("code"), "name": t.get("name"), "price": int(t.get("price") or 0)}
        for t in tests if t.get("code")
    ]


def _select_tests_from_menu(text: str, options: list[dict]) -> list[dict]:
    """Resuelve qué análisis eligió el cliente de la lista mostrada: por número de
    opción (1..N), ordinal ('el primero'), código de catálogo (1601) o nombre."""
    if not options:
        return []
    codes = {str(o.get("code")): o for o in options}
    selected: list[dict] = []
    seen: set = set()

    def _add(opt):
        if opt and opt["code"] not in seen:
            seen.add(opt["code"])
            selected.append(opt)

    for token in _tokenize(text):
        if token.isdigit():
            n = int(token)
            if token in codes:                                  # código del catálogo
                _add(codes[token])
            elif len(token) <= 2 and 1 <= n <= len(options):    # número de opción 1..N
                _add(options[n - 1])
        elif token in _ORDINAL_SELECTIONS:
            n = _ORDINAL_SELECTIONS[token]
            if 1 <= n <= len(options):
                _add(options[n - 1])
    if selected:
        return selected

    # Sin número: por nombre. El match exacto gana; si varios coinciden por substring
    # (ej. hay 4 "Parcial de Orina ...") es ambiguo: no elegir ninguno y que el cliente
    # use el número. Evita capturar varios análisis al azar por un nombre genérico.
    text_key = _catalog_item_key(text)
    if len(text_key) < 4:
        return []
    exact = [o for o in options if _catalog_item_key(o.get("name")) == text_key]
    if exact:
        return [exact[0]]
    partial = [
        o for o in options
        if _catalog_item_key(o.get("name")) and (
            _catalog_item_key(o.get("name")) in text_key or text_key in _catalog_item_key(o.get("name"))
        )
    ]
    return partial if len(partial) == 1 else []


def _capture_test_menu_selection(session: dict, fields: dict, selected: list[dict]) -> dict:
    """Guarda los análisis elegidos del menú (con su código real) y avanza: pide el
    siguiente dato faltante o, si la orden está completa, muestra el resumen."""
    fields["selected_tests"] = [t["code"] for t in selected]
    fields["removed_tests"] = []
    if len(selected) == 1:
        fields["exam_type"] = f"{selected[0]['code']} {selected[0]['name']}"
    else:
        fields["exam_type"] = f"Perfil personalizado ({len(selected)} análisis)"
    fields.pop("_test_menu_options", None)
    fields.pop("_test_menu_adds_to_profile", None)

    # Mostrar el precio al lado de cada análisis (y el total si son varios), no solo el nombre.
    intro = f"Listo, registro {_format_test_items(selected)}."
    if len(selected) >= 2:
        total = calculate_custom_profile_total(selected)["total"]
        intro += f" Valor estimado: {_money(total)}."
    return _analysis_settled_response(session, fields, intro)


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


_AREA_OPTION_QUESTION_TOKENS = frozenset({
    "que", "qué", "cuales", "cuáles", "cual", "cuál", "tienen", "tienes", "tiene",
    "hay", "ofrecen", "ofreces", "manejan", "maneja", "disponibles", "disponible",
    "opciones", "tipos", "tipo", "muestrame", "muéstrame", "muestra", "lista",
})


def _asks_for_area_options(text: str) -> bool:
    """¿El mensaje es una pregunta abierta por opciones de un área ('qué análisis de
    orina tienen', 'qué tipos de sangre manejan'), en vez de nombrar un test exacto?"""
    tokens = set(_tokenize(text))
    return bool(tokens & _AREA_OPTION_QUESTION_TOKENS) or "?" in (text or "")


def _area_options_for_profile_addition(fields: dict, user_message: str) -> dict | None:
    """Si el cliente, mientras ajusta un perfil, pregunta por análisis de un ÁREA
    ('qué análisis de orina tienen'), devuelve el menú de esa área marcado para AGREGAR
    al perfil base (no reemplazarlo). None si el mensaje no es una pregunta por área."""
    if not _asks_for_area_options(user_message):
        return None
    area, tests = db.find_tests_by_area(user_message, fields.get("species"), limit=10)
    if not area or not tests:
        return None
    _store_test_menu_options(fields, tests)
    fields["_test_menu_adds_to_profile"] = True
    fields.pop("_awaiting_additional_test", None)
    return _base_route_response(_test_area_suggestion_reply(area, tests), fields)


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


_PROCEED_TO_PAYMENT_TOKENS = frozenset({
    "no", "nada", "ninguno", "ninguna", "listo", "lista", "seguimos", "sigamos", "sigue",
    "continuemos", "continua", "continúa", "ya", "pago", "paga", "pagar", "cerramos",
    "cierra", "finalizar", "terminar", "eso", "suficiente", "completo", "completa",
})
_PROCEED_TO_PAYMENT_PHRASES = (
    "asi esta", "asi está", "esta bien", "está bien", "asi nomas", "nada mas", "nada más",
    "es todo", "con eso", "sigamos con el pago", "seguimos con el pago", "vamos al pago",
    "asi quedamos", "ya esta", "ya está", "dejalo asi", "déjalo así",
)
_REMOVE_TOKENS = frozenset({"quitar", "quita", "quitale", "quítale", "sacar", "saca", "sacale",
                            "sácale", "sin", "menos", "retirar", "remover", "remueve"})


def _wants_to_proceed_to_payment(text: str) -> bool:
    """Ante la oferta de agregar más, ¿el cliente decide SEGUIR al pago (o ya dio el método)?
    Una orden de agregar/quitar ('agregale X') nunca cuenta como seguir."""
    if _payment_method_from_text(text):
        return True
    ordered = _tokenize(text)
    tokens = set(ordered)
    if tokens & (_ANALYSIS_ADD_REMOVE_TOKENS | _REMOVE_TOKENS):
        return False
    normalized = " ".join(ordered)  # ORDENADO: las frases necesitan el orden original
    if any(p in normalized for p in _PROCEED_TO_PAYMENT_PHRASES):
        return True
    return bool(tokens & _PROCEED_TO_PAYMENT_TOKENS)


def _handle_extra_analysis_answer(session: dict, fields: dict, user_message: str) -> dict | None:
    """Interpreta la respuesta del cliente a la oferta '¿agregar otro análisis o seguimos con
    el pago?'. Devuelve la respuesta del bot, o None si dio el método de pago (que el pipeline
    normal capture). Se repite tras cada agregado hasta que el cliente decida seguir."""
    # 1) Sigue al pago: dio el método o dijo que ya está.
    if _wants_to_proceed_to_payment(user_message):
        fields.pop("_offering_extra_analysis", None)
        if _payment_method_from_text(user_message):
            return None  # el pipeline normal captura el método de pago
        return _base_route_response(PAYMENT_METHOD_QUESTION, fields)

    tokens = set(_tokenize(user_message))

    # 2) Pregunta por opciones de un área ('qué análisis de orina tienen') -> menú que SUMA.
    area_resp = _area_options_for_profile_addition(fields, user_message)
    if area_resp:
        return area_resp

    # 3) Pide recomendación / no sabe / 'otro perfil' -> lista de perfiles por especie.
    species = fields.get("species")
    if species and (_wants_profile_recommendation(user_message) or _doesnt_know_what_to_ask(user_message)
                    or ("perfil" in tokens and tokens & {"otro", "otra", "mas", "más"})):
        profiles = db.list_catalog_profiles_for_species(species, limit=6)
        if profiles:
            fields["_profile_menu_options"] = [
                {"code": p.get("code"), "name": p.get("name"), "price": int(p.get("price") or 0)}
                for p in profiles if p.get("code")
            ]
            return _base_route_response(_format_profile_recommendation(species, profiles), fields)

    # 4) Nombró análisis concreto(s) para agregar o quitar.
    rows = db.get_tests_by_codes_or_names([user_message] + _named_analysis_terms(user_message))
    if rows:
        action = "remove" if (tokens & _REMOVE_TOKENS) else "add"
        _add_tests_to_order(fields, rows, action)
        fields.pop("_awaiting_additional_test", None)
        verb = "quito" if action == "remove" else "agrego"
        return _analysis_settled_response(session, fields, f"Listo, {verb} {_format_test_items(rows)}.")

    # 5) Quiere agregar pero no dijo cuál (un 'sí' suelto o 'personalizar').
    if _is_affirmative_text(user_message) or _is_profile_customization_request(user_message):
        fields["_awaiting_additional_test"] = "add"
        return _base_route_response("Claro. ¿Qué análisis quieres agregar? Decime el nombre o el código.", fields)

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
    # No interferir si hay un menú/selección de análisis a medio resolver.
    if (fields.get("_test_menu_options") or fields.get("_profile_menu_options")
            or fields.get("_test_menu_adds_to_profile") or fields.get("_diagnostic_label")):
        return ai_response
    has_analysis = bool(fields.get("exam_type") or fields.get("selected_tests") or fields.get("_selected_profile_code"))
    if not has_analysis:
        return ai_response
    analysis_new = (
        (fields.get("exam_type") or None) != (prev_fields.get("exam_type") or None)
        or _as_text_items(fields.get("selected_tests")) != _as_text_items(prev_fields.get("selected_tests"))
        or fields.get("_selected_profile_code") != prev_fields.get("_selected_profile_code")
    )
    if not analysis_new or _missing_route_field(session, fields) != "payment_method":
        return ai_response
    exam = fields.get("_selected_profile_name") or fields.get("exam_type")
    return _analysis_settled_response(session, fields, f"Listo, queda {exam}.")


def _enforce_multiple_tests_capture(session: dict, ai_response: dict, prev_fields: dict) -> dict:
    """Si el cliente pidió varios análisis en un mismo mensaje y cada uno mapea
    1:1 a un test del catálogo, los registra de una vez como perfil personalizado
    en lugar de repreguntar el tipo de análisis (evita el bucle reportado). Si
    algún ítem es ambiguo o no existe, no toca nada: deja el flujo normal."""
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

    items = _split_multiple_exam_items(candidate)
    if len(items) < 2:
        return ai_response

    rows = []
    seen = set()
    for item in items:
        matches = db.get_tests_by_codes_or_names([item])
        if len(matches) != 1:
            return ai_response  # ambiguo o inexistente -> dejar el flujo normal
        row = matches[0]
        if row.get("code") in seen:
            return ai_response  # dos ítems al mismo test -> dejar el flujo normal
        seen.add(row.get("code"))
        rows.append(row)

    totals = calculate_custom_profile_total(rows)
    fields["selected_tests"] = [r["code"] for r in rows]
    fields["removed_tests"] = []
    fields["exam_type"] = f"Perfil personalizado ({len(rows)} análisis)"

    intro = (
        f"Listo, registro estos {len(rows)} análisis: {_format_test_items(rows)}. "
        f"Valor estimado: {_money(totals['total'])}."
    )
    return _analysis_settled_response(session, fields, intro)


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

    fields["exam_type"] = None
    fields["selected_tests"] = []
    fields["removed_tests"] = []
    _store_test_menu_options(fields, tests)
    return _base_route_response(_test_area_suggestion_reply(area or candidate, tests), fields)


def _enforce_analysis_help_fallback(session: dict, ai_response: dict, prev_fields: dict,
                                    user_message: str, history: list[dict]) -> dict:
    """Red de seguridad final del paso de análisis: si el bot pidió el análisis y el cliente
    respondió algo VAGO (un síntoma/necesidad que no mapeó a área ni etiqueta, o no supo qué
    pedir) y el AI dejó exam_type vacío, mostrar perfiles de la especie en una lista
    seleccionable con precios REALES, en vez de dejar que el modelo improvise una lista sin
    menú detrás (no seleccionable y con riesgo de inventar precios). Ver RESUELTO-016."""
    if ai_response.get("intent") != "route_scheduling":
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
    fields["_profile_menu_options"] = [
        {"code": p.get("code"), "name": p.get("name"), "price": int(p.get("price") or 0)}
        for p in profiles if p.get("code")
    ]
    return _base_route_response(_format_profile_recommendation(species, profiles), fields)


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


def _catalog_overview_response(fields: dict) -> dict:
    tests = db.list_catalog_tests(limit=500)
    choices = _catalog_overview_choices(tests)
    return _test_options_response(fields, choices, _test_catalog_overview_reply(choices))


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
    fields["_profile_menu_options"] = [
        {"code": p.get("code"), "name": p.get("name"), "price": int(p.get("price") or 0)}
        for p in profiles if p.get("code")
    ]
    return _base_route_response(_format_profile_recommendation(species, profiles), fields)


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


def _escalate_unfound_client(fields: dict, reply: str = CLIENT_NOT_FOUND_MESSAGE) -> dict:
    # El cliente dice no ser nuevo pero no aparece en la base: derivar a un humano
    # en vez de seguir pidiendo el identificador en bucle.
    fields["_handoff_announced"] = True
    fields["_blocked"] = True
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


_REJECT_ALL_MATCH_TOKENS = frozenset({
    "ninguno", "ninguna", "ningun", "ningún", "ningunos", "ningunas", "tampoco",
})

# Palabras comunes que NO deben tratarse como un nombre de cliente en la búsqueda exacta de
# refuerzo (segundo intento). Evita falsos positivos al probar palabras sueltas del mensaje.
_EXACT_RETRY_STOPWORDS = frozenset({
    "ninguno", "ninguna", "ningun", "ningunos", "ningunas", "tampoco", "esos", "esas",
    "veterinaria", "clinica", "consultorio", "hospital", "laboratorio", "centro",
    "llama", "llamo", "nombre", "mejor", "busca", "buscar", "tengo", "quiero", "registrada",
    "registrado", "registrados", "cliente", "nueva", "nuevo", "somos", "soy",
    "pero", "entonces", "creo", "entiendo", "perdon", "perdón",
})


def _rejects_match_options(text: str) -> bool:
    """El cliente indica que NINGUNA de las coincidencias listadas es la suya
    ('ninguno de esos', 'no es ninguna', 'tampoco')."""
    return bool(set(_tokenize(text)) & _REJECT_ALL_MATCH_TOKENS)


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


_TIME_QUESTION_TOKENS = frozenset({
    "cuanto", "cuánto", "cuando", "cuándo", "tiempo", "tardan", "tarda",
    "demoran", "demora", "demorar", "promedio", "aproximado", "aproximadamente",
    "hora", "horas", "dia", "dias", "día", "días", "plazo", "urgente",
    "rapido", "rápido", "llega", "llegan", "llegaria", "llegaría", "pasan",
})
_RESULT_TOKENS = frozenset({"resultado", "resultados", "entrega", "entregan", "entregar"})
_ANALYSIS_TOKENS = frozenset({"analisis", "análisis", "examen", "examenes", "exámenes", "perfil", "prueba", "muestra", "muestras"})
_ROUTE_TIMING_TOKENS = frozenset({
    "motorizado", "motorizados", "repartidor", "mensajero", "ruta", "recogida",
    "retiro", "retirar", "recoger", "pasan", "pasar", "llega", "llegaria", "llegaría",
})
_PRICE_QUESTION_TOKENS = frozenset({"cuanto", "cuánto", "cuesta", "costaria", "costaría", "valor", "precio", "cotizar", "cotizacion", "cotización"})
# El cliente pregunta por el TOTAL de varios análisis ("¿cuánto serían todos?", "en total").
_TOTAL_QUESTION_TOKENS = frozenset({
    "todos", "todas", "total", "todo", "junto", "juntos", "completo", "suma", "sumando",
    "conjunto", "sumados",
})
# Palabras que NO nombran un análisis: se descartan al buscar el precio de uno puntual.
_PRICE_STOPWORDS = _PRICE_QUESTION_TOKENS | _TOTAL_QUESTION_TOKENS | {
    "el", "la", "los", "las", "un", "una", "unos", "unas", "de", "del", "ese", "esos",
    "esa", "esas", "esto", "este", "estos", "y", "e", "o", "u", "me", "que", "es", "son",
    "seria", "serían", "serian", "sería", "sale", "saldria", "saldría", "para", "por",
    "con", "sin", "mas", "más", "todos", "analisis", "análisis", "examen", "examenes",
    "exámenes", "prueba", "pruebas", "perfil", "perfiles", "cada", "uno",
}
# Marcadores de que el cliente PREGUNTA por el servicio de recogida (vs. ORDENA
# impacientemente "programen la recogida ya"). Sin esto, cualquier mención de
# "recogida/recoger" disparaba la respuesta operativa fija y metía bucle.
_SERVICE_QUESTION_MARKERS = frozenset({
    "hacen", "atienden", "recogen", "retiran", "pueden", "puede", "tienen",
    "ofrecen", "como", "cómo", "cual", "cuál", "sirve", "sirven", "trabajan",
    "manejan", "cubren", "donde", "dónde", "ustedes", "hay",
})
# Verbos imperativos: el cliente PIDE que se programe, no pregunta por el servicio.
_SCHEDULING_IMPERATIVE_TOKENS = frozenset({
    "programen", "programa", "programen", "agenden", "agende", "agenda",
    "coordinen", "coordina", "manden", "manda", "envien", "envíen", "envia",
    "envía", "recogela", "recógela", "ya", "hoy", "urgente", "rapido", "rápido",
})


def _is_service_question(text: str, tokens: set) -> bool:
    """¿El mensaje es una PREGUNTA sobre el servicio (no una orden impaciente)?"""
    has_imperative = bool(tokens & _SCHEDULING_IMPERATIVE_TOKENS)
    has_question = ("?" in text or "¿" in text or bool(tokens & _SERVICE_QUESTION_MARKERS))
    return has_question and not has_imperative


def _operational_side_question_answer(text: str) -> str | None:
    """Preguntas operativas de A3: responder sin inventar, antes de retomar el flujo."""
    tokens = set(_tokenize(text))
    if not tokens:
        return None

    asks_time = bool(tokens & _TIME_QUESTION_TOKENS)
    if asks_time and tokens & (_RESULT_TOKENS | _ANALYSIS_TOKENS):
        return (
            "Depende del análisis y de la muestra; para no darte un tiempo incorrecto, "
            "dime qué prueba necesitas y te oriento con el tiempo estimado."
        )
    if asks_time and tokens & _ROUTE_TIMING_TOKENS:
        return (
            "La hora exacta de recogida la confirma operaciones según la ruta y la disponibilidad "
            "del motorizado; si es urgente, lo dejamos marcado para priorizar la coordinación."
        )
    # Las preguntas de precio NO se deflectan acá con una frase genérica: el precio real lo
    # resuelve `_catalog_price_answer` (casos seguros) o el LLM, que recibe el catálogo con
    # precios y conoce los sinónimos (hemograma = Cuadro Hemático). Deflectar bloqueaba esa
    # respuesta y el cliente dejaba de ver el precio.
    if tokens & {"animal", "animales", "especie", "especies"} and tokens & {"cantidad", "cuantos", "cuántos", "cuales", "cuáles", "que", "qué", "hacen", "atienden"}:
        return (
            "Trabajamos principalmente con pacientes veterinarios como caninos y felinos; "
            "otras especies se revisan según el análisis y la muestra."
        )
    if tokens & {"retirar", "retiran", "recoger", "recogen", "recogida", "motorizado", "motorizados"}:
        # Solo si es una PREGUNTA por el servicio; si el cliente ORDENA que programen
        # ("recógela hoy", "programen la recogida ya"), no es duda operativa: dejar
        # que el flujo siga capturando/cerrando en vez de soltar la frase fija (bucle).
        if _is_service_question(text, tokens):
            return "Sí, recogemos muestras con motorizado asignado para clientes registrados en Bogotá."
        return None
    return None


def _has_active_route_context(session: dict, fields: dict) -> bool:
    return (
        session.get("intent_current") == "route_scheduling"
        or bool(session.get("client_id") or fields.get("_client_found"))
        or any(fields.get(k) for k in _ROUTE_REQUIRED_FIELDS)
    )


def _results_pending_response(fields: dict | None = None, pending_intents: list | None = None) -> dict:
    """Respuesta de la opción 2 (consultar resultados): informa que aún no está
    disponible por este medio y cierra el turno sin pedir datos. Si quedan
    intenciones pendientes (p. ej. una ruta), se preservan para retomarlas."""
    pending = pending_intents or []
    return {
        "reply": RESULTS_PENDING_MESSAGE,
        "phase": "fase_2_recogida_datos" if pending else "fase_6_cierre",
        "intent": "results",
        "service_area": "results",
        "requires_handoff": False,
        "handoff_area": None,
        "captured_fields": fields or {},
        "confidence": 1.0,
        "message_mode": "side_question",
        "pending_intents": pending,
        "resume_prompt": "",
    }


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
_CLIENT_NOUN_TOKENS = frozenset({
    "veterinaria", "veterinarias", "clinica", "clínica", "clinicas", "clínicas",
    "consultorio", "hospital", "cliente", "clientes",
})
_CLIENT_CHANGE_SIGNAL_TOKENS = frozenset({
    "otra", "otras", "otro", "otros", "cambiar", "cambia", "cambio", "cambió", "distinta", "distinto",
    "diferente", "no", "equivoque", "equivoqué", "equivoco", "equivocado", "equivocada",
    "nueva", "nuevo",
})


def _wants_to_change_client(text: str) -> bool:
    """¿El usuario indica que la orden es para OTRA veterinaria/cliente?
    Exige un sustantivo de cliente + una señal de cambio para no confundir un
    'confirmo los datos del cliente' con un cambio real."""
    tokens = set(_tokenize(text))
    return bool(tokens & _CLIENT_NOUN_TOKENS) and bool(tokens & _CLIENT_CHANGE_SIGNAL_TOKENS)


# Sucursal/sede nueva NO registrada: requiere un sustantivo de sede + una señal de
# "nueva/registrar", para no confundir la SELECCIÓN de una sede ya registrada
# ("la sede del norte") con el alta de una sede nueva.
_BRANCH_NOUN_TOKENS = frozenset({"sucursal", "sucursales", "sede", "sedes", "local", "locales"})
_BRANCH_NEW_SIGNAL_TOKENS = frozenset({
    "nueva", "nuevo", "nuevas", "nuevos", "registrar", "registro",
    "agregar", "añadir", "anadir", "abrir", "abrimos", "abrieron", "abrio", "abrió",
    "inaugurar", "inauguramos", "ninguna", "ninguno",
})


def _wants_new_branch(text: str) -> bool:
    """¿El usuario quiere usar/registrar una SUCURSAL o SEDE nueva no registrada?"""
    tokens = set(_tokenize(text))
    return bool(tokens & _BRANCH_NOUN_TOKENS) and bool(tokens & _BRANCH_NEW_SIGNAL_TOKENS)


def _restart_identification_for_new_client(chat_id: str, session: dict, fields: dict) -> dict:
    """Cambio de cliente a mitad del armado: descarta la identificación y la orden
    anteriores (incluido el client_id en BD) y vuelve a pedir el NIT o nombre para
    verificar contra el registro. A partir de ahí sigue el flujo normal de
    identificación: si está registrado continúa; si es nuevo, se deriva."""
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


def _followup_wants_new_analysis(text: str) -> bool:
    """En el mismo mensaje de 'otra orden', ¿el cliente pidió CAMBIAR el análisis?
    Ej.: 'otra orden con los mismos datos pero cambiale el análisis a glucosa'. Exige
    nombrar el análisis/examen/perfil junto a una señal de cambio para no confundir con
    'otra orden para otro paciente' (que mantiene el análisis anterior)."""
    tokens = set(_tokenize(text))
    if not (tokens & _ANALYSIS_TOKENS):
        return False
    if re.search(r"(?i)\bcambi", text or ""):
        return True
    return bool(tokens & {"otro", "otra", "nuevo", "nueva", "distinto", "distinta", "diferente"})


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
    for field in ("pickup_address", "requesting_doctor", "payment_method"):
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
    lines.append("¿Confirmas o quieres cambiar alguno (dirección, médico, forma de pago o análisis)?")
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


def _is_same_as_previous(text: str) -> bool:
    lower = (text or "").lower().strip()
    if not lower:
        return False
    tokens = set(_tokenize(text))
    if tokens & _SAME_AS_PREVIOUS_TOKENS and len(tokens) <= 6:
        if not tokens & _AFFIRMATIVE_TOKENS or len(tokens) <= 3:
            return True
    for phrase in _SAME_AS_PHRASES:
        if phrase in lower:
            return True
    return False


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


def _detect_which_field_is_being_asked(history: list[dict]) -> str | None:
    bot_msg = _last_bot_message(history).lower()
    field_patterns = [
        ("medico solicitante", "requesting_doctor"),
        ("médico solicitante", "requesting_doctor"),
        ("nombre del paciente", "patient_name"),
        ("nombre del propietario", "owner_name"),
        ("propietario", "owner_name"),
        ("especie", "species"),
        ("canino", "species"),
        ("felino", "species"),
        ("raza", "breed"),
        ("macho o hembra", "sex"),
        ("sexo", "sex"),
        ("edad", "patient_age"),
        ("dirección de retiro", "pickup_address"),
        ("domicilio", "pickup_address"),
        ("retiro", "pickup_address"),
        ("análisis", "exam_type"),
        ("perfil", "exam_type"),
        ("examen", "exam_type"),
        ("observaci", "observations"),
        ("pago", "payment_method"),
        ("contraentrega", "payment_method"),
    ]
    for pattern, field in field_patterns:
        if pattern in bot_msg:
            return field
    return None


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

    assigned_text = ", ".join(
        f"el {_FIELD_LABELS.get(assigned_field, assigned_field)} es el mismo: {value}"
        for assigned_field, value in assigned
    )
    reply = f"Entiendo que {assigned_text}. Lo confirmo para registrar."
    if next_missing and next_missing in _FIELD_LABELS:
        reply += f" ¿Cuál es {_FIELD_LABELS[next_missing]}?"

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


def _confirms_new_client(text: str) -> bool:
    tokens = _tokenize(text)
    if not tokens or any(token == "no" for token in tokens):
        return False

    words = set(tokens)
    if "cliente" in words and "nuevo" in words:
        return True
    return len(tokens) <= 4 and bool(words & _AFFIRMATIVE_TOKENS) and not any(token.isdigit() for token in tokens)


def _explicitly_says_new_client(text: str) -> bool:
    """Mención EXPLÍCITA de ser cliente nuevo ('soy cliente nuevo', 'cliente nuevo').
    A diferencia de `_confirms_new_client`, no cuenta una afirmación pelada ('sí',
    'la uno'): esas solo significan 'soy nuevo' si el bot acaba de preguntarlo (L46)."""
    words = set(_tokenize(text))
    if "no" in words:
        return False
    return "cliente" in words and "nuevo" in words


def _claims_unregistered_client(text: str) -> bool:
    normalized = " ".join(_tokenize(text))
    phrases = (
        "no estoy registrado", "no estamos registrados", "no esta registrado",
        "no está registrado", "no estoy en la base", "no estamos en la base",
        # Formas naturales de decir que no está registrado / es independiente / es nuevo
        "de forma independiente", "soy independiente", "trabajo independiente",
        "trabajo de forma independiente", "de manera independiente", "por mi cuenta",
        "me tendria que registrar", "me tendría que registrar", "tendria que registrarme",
        "tendría que registrarme", "tengo que registrarme", "me tengo que registrar",
        "registrarme de nuevo", "no me he registrado", "todavia no estoy registrado",
        "todavía no estoy registrado", "aun no estoy registrado", "aún no estoy registrado",
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


# Confirmación de la dirección registrada: la gente confirma con deícticos
# ("sí es ese", "esa misma", "esa está bien") y a veces mezcla una pregunta en
# el mismo mensaje. No exigimos longitud corta ni palabras exactas; una negación
# explícita siempre gana.
_ADDRESS_CONFIRM_TOKENS = _AFFIRMATIVE_TOKENS | {
    "ese", "esa", "eso", "esos", "esas", "correcta", "correcto",
    "asi", "así", "afirmativo", "confirmo", "confirmado", "seguro", "vale",
}


def _confirms_address(text: str) -> bool:
    words = set(_tokenize(text))
    if not words or words & _NEGATIVE_TOKENS:
        return False
    if words == {"1"}:  # respondió la opción "1) sí, esa dirección está bien"
        return True
    if words & _ADDRESS_CONFIRM_TOKENS:
        return True
    # Confirmaciones coloquiales pegadas o alargadas: "sisi", "sisisi", "siii", "sí sí".
    return any(re.fullmatch(r"(s[ií]+)+", w) for w in words)


def _rejects_address(text: str) -> bool:
    words = set(_tokenize(text))
    if words == {"2"}:  # respondió la opción "2) enviarme la dirección correcta"
        return True
    return _is_negative_text(text)


_RESULTS_CHOICE_TOKENS = frozenset({"2", "dos", "resultado", "resultados"})
_OTHER_CHOICE_TOKENS = frozenset({"4", "cuatro", "otro", "otra"})


def _is_results_choice(text: str) -> bool:
    """El usuario eligió la opción 2 del menú (consultar resultados)."""
    words = _tokenize(text)
    return bool(set(words) & _RESULTS_CHOICE_TOKENS) and len(words) <= 4


def _is_other_choice(text: str) -> bool:
    """El usuario eligió la opción 4 del menú (otro)."""
    words = _tokenize(text)
    return bool(set(words) & _OTHER_CHOICE_TOKENS) and len(words) <= 4


_OPTION_CORRECTION_TOKENS = frozenset({
    "confundi", "confundí", "confundido", "confundida", "confundir",
    "equivoque", "equivoqué", "equivoco", "equivocada", "equivocado",
})
_OPTION_WORDS = frozenset({"opcion", "opción", "opciones", "menu", "menú"})
_RECONSIDER_HINT_TOKENS = frozenset({
    "otra", "otras", "cambiar", "cambio", "cambie", "no", "volver", "regresar",
    "mal", "distinta", "distinto", "diferente",
})


def _wants_to_reconsider_option(text: str) -> bool:
    """El usuario indica que se confundió de opción o quiere volver a elegir
    (ej. 'perdón, me confundí de opción'). No es un dato a capturar."""
    words = set(_tokenize(text))
    if not words:
        return False
    if words & _OPTION_CORRECTION_TOKENS:
        return True
    return bool(words & _OPTION_WORDS and words & _RECONSIDER_HINT_TOKENS)


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
        "reply": "Te voy a comunicar con una persona del equipo para que te ayude con eso.",
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
_HANDOFF_ACCEPT_TOKENS = frozenset({
    "derivame", "derivar", "deriva", "deriven", "derivenme", "persona", "humano",
    "asesor", "agente", "registrar", "registra", "registrame", "regístrame", "registralo",
    "regístralo", "comunicame", "comunícame", "contactenme", "contáctenme",
})


def _accepts_handoff_offer(text: str, signal: str | None) -> bool:
    """¿El usuario acepta la oferta de derivación? Fuente primaria: la señal de la IA;
    fallback: tokens de aceptación / afirmación, salvo que niegue explícitamente."""
    if signal == "affirm":
        return True
    if signal == "negate":
        return False
    tokens = set(_tokenize(text))
    if tokens & _NEGATIVE_TOKENS:
        return False
    return bool(tokens & _HANDOFF_ACCEPT_TOKENS) or _is_affirmative_text(text)


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


def _enforce_results_message(session: dict, ai_response: dict, user_message: str) -> dict:
    """Si el turno se clasificó como consulta de resultados, responde con el
    mensaje fijo. Si junto con los resultados quedó pendiente programar una
    recogida, entrega el mensaje fijo Y retoma la ruta en el mismo turno, para
    no perder la intención de recogida (resume determinístico)."""
    if ai_response.get("intent") != "results":
        return ai_response
    fields = ai_response.get("captured_fields") or {}
    pending = ai_response.get("pending_intents") or []

    operational_answer = _operational_side_question_answer(user_message)
    if operational_answer:
        response = _base_route_response(operational_answer, fields)
        response["message_mode"] = "side_question"
        return _resume_route_after_lateral_turn(session, response) if _has_active_route_context(session, fields) else response

    if "route_scheduling" in pending:
        missing = _missing_route_field(session, fields)
        question = _missing_route_field_question(missing) if missing else "¿Confirmas que programamos la recogida?"
        resumed = _base_route_response(
            f"{RESULTS_PENDING_MESSAGE}\n\nMientras tanto, sigamos con la recogida que me pedías. {question}",
            fields,
        )
        resumed["message_mode"] = "side_question"
        resumed["captured_fields"]["_pending_intents"] = []
        return resumed

    return _results_pending_response(fields, pending)


_FOLLOWUP_NEW_TOKENS = frozenset({"otra", "otras", "otro", "otros", "nueva", "nuevo", "nuevas", "nuevos"})
_FOLLOWUP_OBJECT_TOKENS = frozenset({
    "orden", "ordenes", "órdenes", "servicio", "pedido", "pedidos", "muestra",
    "muestras", "ruta", "recogida", "retiro", "paciente", "animal", "analisis", "análisis",
})
_FOLLOWUP_CREATE_TOKENS = frozenset({
    "crear", "crea", "hacer", "haz", "programar", "agendar", "generar", "necesito", "quiero",
})


def _wants_another_service_order(text: str) -> bool:
    return _explicitly_wants_another_order(text)


def _explicitly_wants_another_order(text: str) -> bool:
    """Pide explícitamente OTRA orden. A diferencia de `_wants_another_service_order`,
    NO se conforma con un 'sí' suelto: se usa fuera de la fase terminal (cuando no venimos
    de la pregunta '¿necesitas otra orden?'), por eso exige señal fuerte de nueva orden."""
    words = set(_tokenize(text))
    if not words or "no" in words:
        return False
    if words & _FOLLOWUP_NEW_TOKENS and (words & _FOLLOWUP_OBJECT_TOKENS or len(words) <= 3):
        return True
    return bool(words & _FOLLOWUP_CREATE_TOKENS) and bool(words & _FOLLOWUP_OBJECT_TOKENS)


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
    if _is_no_identifier_text(text) or _claims_unregistered_client(text):
        return None

    def _clean_candidate(cand: str) -> str | None:
        cand = cand.strip(" .,:;-")
        cand = re.sub(r"(?i)^(?:m[ií]a|m[ií]o|mi|nuestra|nuestro)\s+(?:es|se llama)\s+", "", cand).strip(" .,:;-")
        cand = re.sub(r"(?i)^(?:es|se llama)\s+", "", cand).strip(" .,:;-")
        if cand and any(ch.isalpha() for ch in cand) and len(_tokenize(cand)) <= 4 \
                and not (set(_tokenize(cand)) & _NON_IDENTIFIER_TOKENS):
            return cand
        return None

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


def _looks_like_bare_client_name(text: str) -> bool:
    if _claims_unregistered_client(text):
        return False
    tokens = _tokenize(text)
    if not tokens or len(tokens) > 4:
        return False
    if tokens[0] in {"para", "por", "porque", "como", "cómo", "que", "qué", "cual", "cuál", "tengo"}:
        return False
    return not (set(tokens) & _NON_IDENTIFIER_TOKENS)


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


_NO_OWNER_TOKENS = frozenset({
    "ninguno", "ninguna", "callejero", "callejera", "callejeros", "callejeras",
    "rescatado", "rescatada", "rescate",
})
_NO_OWNER_PHRASES = (
    "sin dueño", "sin dueno", "sin propietario", "sin amo",
    "no tiene dueño", "no tiene dueno", "no tiene propietario", "no tiene amo",
    "no hay dueño", "no hay dueno", "no aplica", "no sabemos",
)


def _says_no_owner(text: str) -> bool:
    """El cliente indica que el paciente NO tiene propietario (callejero, rescatado, etc.).
    Solo se usa cuando se está pidiendo el propietario, así 'ninguna' es inequívoco ahí."""
    low = (text or "").lower()
    if any(p in low for p in _NO_OWNER_PHRASES):
        return True
    return bool(set(_tokenize(text)) & _NO_OWNER_TOKENS)


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
    # NIT canónico del cliente (de la BD): necesario para facturar en Alegra cuando el
    # cliente se identificó por NOMBRE. Sin esto, `_try_invoice_in_alegra` recibía
    # tax_id=None y la facturación se saltaba en silencio aunque el cliente tuviera NIT.
    if client.get("tax_id"):
        fields["tax_id"] = client.get("tax_id")


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


def _avoid_repeated_question(ai_response: dict, history: list[dict], prev_fields: dict) -> dict:
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


def _reply_asks_for_route_field(reply: str, field: str) -> bool:
    text = " ".join(_tokenize(reply))
    if field == "requesting_doctor":
        return "medico solicitante" in text or "médico solicitante" in text
    if field == "exam_type":
        return (
            "que tipo de analisis" in text or "qué tipo de análisis" in text
            or "analisis o perfil exacto" in text or "análisis o perfil exacto" in text
            or "cual van a enviar" in text or "cuál van a enviar" in text
            or "perfil desean" in text
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


def _enforce_first_missing_after_progress(session: dict, ai_response: dict, prev_fields: dict) -> dict:
    if ai_response.get("intent") != "route_scheduling" or ai_response.get("requires_handoff"):
        return ai_response
    if ai_response.get("phase") in TERMINAL_PHASES or ai_response.get("phase") == CONFIRMATION_PHASE:
        return ai_response

    fields = ai_response.get("captured_fields", {})
    if fields.get("_client_match_options") or fields.get("_client_not_found"):
        return ai_response
    # Oferta de agregar otro análisis activa (Parte B): no pisarla con la pregunta de pago.
    if fields.get("_offering_extra_analysis"):
        return ai_response
    if fields.get("_test_menu_options") or (fields.get("selected_tests") is not None and not fields.get("exam_type")):
        return ai_response
    progressed = any(fields.get(f) and fields.get(f) != prev_fields.get(f) for f in _ROUTE_REQUIRED_FIELDS)
    if not progressed:
        return ai_response

    missing = _missing_route_field(session, fields)
    if not missing or _reply_asks_missing_field(ai_response.get("reply", ""), missing):
        return ai_response
    if missing == "pickup_address" and fields.get("_address_confirmation_pending"):
        return ai_response

    ai_response["reply"] = f"Perfecto, lo anoto. {_missing_route_field_question(missing)}"
    return ai_response


def _reply_asks_missing_field(reply: str, field: str) -> bool:
    if field == "client":
        return _asks_for_client_identity(reply)
    return _reply_asks_for_route_field(reply, field)


def _resume_route_after_lateral_turn(session: dict, ai_response: dict) -> dict:
    if ai_response.get("intent") != "route_scheduling" or ai_response.get("requires_handoff"):
        return ai_response
    if ai_response.get("phase") in TERMINAL_PHASES or ai_response.get("message_mode") == "cancellation":
        return ai_response
    if (
        ai_response.get("message_mode") not in {"side_question", "small_talk"}
        and ai_response.get("user_intent_signal") not in {"off_topic", "unclear"}
    ):
        return ai_response

    fields = ai_response.get("captured_fields") or {}
    missing = _missing_route_field(session, fields)
    if not missing:
        return ai_response

    reply = (ai_response.get("reply") or "").strip()
    if "?" in reply and _reply_asks_missing_field(reply, missing):
        return ai_response

    base = _strip_question_sentences(reply)
    question = _missing_route_field_question(missing)
    ai_response["reply"] = f"{base} {question}".strip() if base else question
    return ai_response


# Datos del paciente que deben responderse con un valor concreto: si en su lugar
# llega un saludo o small talk, hay que reencauzar en vez de capturar basura.
# exam_type queda fuera (lo gobierna el flujo de catálogo/perfil); cliente,
# dirección, pago y observaciones tienen su propio manejo dedicado.
_COHERENCE_GUARDED_FIELDS = frozenset({
    "requesting_doctor", "patient_name", "species", "breed", "sex", "patient_age", "owner_name",
})

# Señales baratas de respuesta off-topic: saludos y cortesía social. Si TODA la
# respuesta cabe acá, no contesta el dato pedido. Ningún valor válido de los campos
# guardados (canino/felino, macho/hembra, nombres, edad con unidad) cae en este set.
_OFF_TOPIC_SMALL_TALK_TOKENS = frozenset({
    "hola", "holi", "ola", "buenas", "buenos", "buen", "dia", "dias",
    "tarde", "tardes", "noche", "noches", "hey", "hi", "saludos",
    "como", "estas", "va", "vas", "andas", "anda", "todo", "bien",
    "que", "tal", "mas", "gracias", "jaja", "jeje", "jajaja", "uy",
    # conectores y muletillas que acompañan al small talk
    "y", "ah", "ahh", "ay", "oye", "pero", "pues", "eh", "este",
    "ok", "okay", "che", "ja", "bueno",
})

# Frases sociales completas: aunque el mensaje traiga conectores, si contiene una de
# estas claramente no responde el dato pedido.
_SOCIAL_PHRASES = (
    "como vas", "como estas", "como andas", "como te va", "como va",
    "que mas", "que tal", "todo bien", "que cuentas", "que hubo",
    "como amaneciste", "como sigues", "como va todo",
)

_ACCENT_TRANSLATION = str.maketrans("áéíóúüñ", "aeiouun")


def _looks_off_topic_smalltalk(text: str) -> bool:
    # El tokenizador conserva acentos; se normalizan para comparar.
    norm = " ".join(t.translate(_ACCENT_TRANSLATION) for t in _tokenize(text))
    if not norm:
        return False
    if any(phrase in norm for phrase in _SOCIAL_PHRASES):
        return True
    return set(norm.split()) <= _OFF_TOPIC_SMALL_TALK_TOKENS


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


# Variantes y errores de tipeo comunes de los campos enumerados. Si el modelo no
# captura la respuesta (p. ej. "kanino", "perrito", "masho"), la recuperamos nosotros
# para no repreguntar en bucle. Valores genuinamente ambiguos (ej. "Kany") quedan
# para que el modelo confirme con el usuario.
_RECOVERABLE_SPECIES = {
    "canino": "Canino", "kanino": "Canino", "canina": "Canino", "can": "Canino",
    "perro": "Canino", "perra": "Canino", "perrito": "Canino", "perrita": "Canino",
    "cachorro": "Canino", "felino": "Felino", "felina": "Felino", "gato": "Felino",
    "gata": "Felino", "gatito": "Felino", "gatita": "Felino", "michi": "Felino",
    "equino": "Equino", "caballo": "Equino", "yegua": "Equino",
    "conejo": "Conejo", "ave": "Ave", "loro": "Ave", "reptil": "Reptil", "reptiles": "Reptil",
    "porcino": "Porcino", "cerdo": "Porcino", "bovino": "Bovino", "ovino": "Ovino", "caprino": "Caprino",
}
_RECOVERABLE_SEX = {
    "macho": "Macho", "masho": "Macho", "machito": "Macho", "m": "Macho",
    "hembra": "Hembra", "embra": "Hembra", "hembrita": "Hembra", "h": "Hembra",
}
_IMPLIED_ANIMAL_FIELDS = {
    "perra": ("Canino", "Hembra"), "perrita": ("Canino", "Hembra"),
    "perro": ("Canino", None), "perrito": ("Canino", None), "cachorro": ("Canino", None),
    "gata": ("Felino", "Hembra"), "gatita": ("Felino", "Hembra"),
    "gato": ("Felino", None), "gatito": ("Felino", None), "michi": ("Felino", None),
    "yegua": ("Equino", "Hembra"), "caballo": ("Equino", None),
}


def _apply_implied_animal_fields(fields: dict, user_message: str) -> None:
    for token in (t.translate(_ACCENT_TRANSLATION) for t in _tokenize(user_message)):
        implied = _IMPLIED_ANIMAL_FIELDS.get(token)
        if not implied:
            continue
        species, sex = implied
        current_species = str(fields.get("species") or "").lower().translate(_ACCENT_TRANSLATION)
        if not fields.get("species") or current_species in _RECOVERABLE_SPECIES:
            fields["species"] = species
        current_sex = str(fields.get("sex") or "").lower().translate(_ACCENT_TRANSLATION)
        if sex and (not fields.get("sex") or current_sex in _RECOVERABLE_SEX):
            fields["sex"] = sex
        break


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


def _recover_implied_animal_fields(ai_response: dict, prev_fields: dict, user_message: str) -> dict:
    if ai_response.get("intent") != "route_scheduling" or ai_response.get("requires_handoff"):
        return ai_response
    fields = ai_response.get("captured_fields", {})
    _apply_implied_animal_fields(fields, user_message)
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
        return "Por último, ¿qué análisis o perfil desean?"
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
    if fields.get("_profile_customizing"):
        return ai_response
    # Mientras está activa la oferta de agregar otro análisis (Parte B), no saltar al pago:
    # ese paso lo decide _handle_extra_analysis_answer cuando el cliente diga que sigue.
    if fields.get("_offering_extra_analysis"):
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
        lines.append(f"- Valor estimado: {_money(totals['total'])}")

    return lines


def _route_closure_summary(fields: dict) -> str | None:
    lines = _order_summary_lines(fields, "Quedó registrado:")
    if lines is None:
        return None
    lines.append("Nuestro motorizado pasará a recoger la muestra.")
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


def _extract_correction_value(field: str, text: str) -> str | None:
    if field != "patient_name":
        return None
    matches = list(re.finditer(
        r"(?i)(?:se llama|llama|ahora es|paciente es|paciente:)\s+([A-Za-zÁÉÍÓÚÑáéíóúñüÜ' -]{2,40})\s*$",
        text or "",
    ))
    if not matches:
        return None
    value = matches[-1].group(1).strip(" .,:;-")
    value = re.sub(r"(?i)^(?:ahora\s+)?(?:se\s+)?llama\s+", "", value).strip()
    return value or None


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


def _named_analysis_terms(text: str) -> list[str]:
    """Palabras de la pregunta que podrían nombrar un análisis (descarta las de precio,
    artículos y muletillas). Sirve para resolver '¿cuánto sale el hemograma?'."""
    return [t for t in _tokenize(text) if (len(t) >= 4 or t.isdigit()) and t not in _PRICE_STOPWORDS]


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

    # 2) Análisis nombrado(s) en la propia pregunta. Resolver por catálogo o por el menú
    #    que se acabe de mostrar ('¿cuánto el primero?').
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


def _confirmation_analysis_adjustment(session: dict, fields: dict, user_message: str, signal: str | None) -> dict | None:
    pending_action = fields.get("_awaiting_additional_test")
    if not pending_action and not _wants_partial_analysis_change(user_message):
        return None

    tokens = set(_tokenize(user_message))
    action = pending_action or "add"
    if tokens & {"quitar", "quita", "quitale", "quítale", "sacar", "saca", "sin", "menos", "retirar", "remover"}:
        action = "remove"

    rows = db.get_tests_by_codes_or_names([user_message] + _named_analysis_terms(user_message))
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
            and _is_order_confirmation(user_message)
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
    if ALEGRA_ENABLED and ai_response.get("intent") == "route_scheduling" and order_info:
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
        ai_response["reply"] = f"{ai_response['reply']}\n\n{CLOSING_PROMPT}"
    return ai_response


def _try_invoice_in_alegra(order_info: dict, ai_response: dict) -> None:
    """Factura la orden en Alegra (borrador) al cerrarla. La facturación es complementaria:
    cualquier fallo se loggea y se ignora — nunca rompe el cierre ni la recogida del cliente.
    Guarda los IDs de Alegra como evento `alegra_invoiced` (no toca el esquema de Supabase)."""
    try:
        fields = ai_response.get("captured_fields", {})
        profile = (order_info.get("event_payload") or {}).get("profile")
        lines = billing.build_invoice_lines(profile)
        if not lines:
            return
        nit = fields.get("tax_id")
        name = fields.get("clinic_name") or fields.get("_client_display_name") or "Cliente A3"
        date = datetime.now(APP_TIMEZONE).date().isoformat()
        extra = {"email": fields.get("_client_email"), "phone": fields.get("_client_phone")}
        result = billing.invoice_order(nit, name, lines, date, {k: v for k, v in extra.items() if v})
        if result and result.get("invoice_id"):
            db.create_request_event(order_info["request_id"], "alegra_invoiced", result)
    except alegra.AlegraError as e:
        logger.warning("Alegra: no se pudo facturar la orden %s: %s", order_info.get("request_id"), e)
    except Exception as e:  # noqa: BLE001 — la facturación jamás debe tumbar el cierre
        logger.warning("Alegra: error inesperado facturando %s: %s", order_info.get("request_id"), e)


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


def _persist_turn(chat_id: str, user_message: str, ai_response: dict) -> str:
    db.save_message(chat_id, user_message, "user")
    db.save_message(chat_id, ai_response["reply"], "bot")
    fields = ai_response.get("captured_fields", {})
    fields["_pending_intents"] = ai_response.get("pending_intents", [])
    _remember_client_fields(fields)
    ai_response["captured_fields"] = fields
    db.update_session(chat_id, ai_response)
    return ai_response["reply"]


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

    # Cliente que declara EXPLÍCITAMENTE no estar registrado: escalar a recepción de
    # inmediato (regla de negocio invariante), aunque el mensaje mencione un nombre o
    # pida "que me programen la recogida". Sin esto, las respuestas de preventa/servicio
    # (frase del motorizado) interceptaban y metían bucle de "compárteme el NIT" (ERR-037).
    if not session.get("client_id") and _claims_unregistered_client(user_message):
        fields = dict(prev_captured)
        fields["clinic_name"] = None
        fields["tax_id"] = None
        fields.pop("_client_found", None)
        fields.pop("_client_not_found", None)
        _clear_client_match_options(fields)
        return _escalate_new_client_turn(
            chat_id, session, user_message, fields,
            started_from_escalation, CLIENT_NEW_REGISTRATION_MESSAGE,
        )

    if (
        not session.get("client_id")
        and not any(prev_captured.get(k) for k in ("clinic_name", "tax_id", "_client_match_options"))
        and not (_has_client_marker(user_message) or _extract_tax_id_candidate(user_message, allow_unlabeled=True))
        # Si ya pedimos el NIT/nombre, lo que diga el usuario es su identificación: que el
        # LLM lea el mensaje COMPLETO (no que un token suelto como "Colombia" lo desvíe a
        # una respuesta de cortesía). El atajo de servicio solo aplica al contacto inicial.
        and not _awaiting_client_identifier(history)
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
        price_answer = _catalog_price_answer(dict(prev_captured), user_message)
        if price_answer and not _payment_method_from_text(user_message):
            response = _base_route_response(price_answer, dict(prev_captured))
            response["message_mode"] = "side_question"
            response = _resume_route_after_lateral_turn(session, response)
            return _persist_turn(chat_id, user_message, response)
        operational_answer = _operational_side_question_answer(user_message)
        if operational_answer and not _payment_method_from_text(user_message):
            response = _base_route_response(operational_answer, dict(prev_captured))
            response["message_mode"] = "side_question"
            response = _resume_route_after_lateral_turn(session, response)
            return _persist_turn(chat_id, user_message, response)
        if _is_catalog_overview_question(user_message):
            return _persist_turn(chat_id, user_message, _catalog_overview_response(dict(prev_captured)))

    # Selección de un perfil de la lista recomendada ('no sé / qué me recomiendas'): el
    # cliente elige por número, ordinal, código o nombre. Se captura el perfil REAL con su
    # código y precio (para que el resumen muestre el valor), sin depender del modelo.
    if prev_captured.get("_profile_menu_options"):
        chosen_profile = _select_profile_from_menu(user_message, prev_captured["_profile_menu_options"])
        if chosen_profile:
            return _persist_turn(
                chat_id, user_message,
                _capture_profile_menu_selection(session, prev_captured, chosen_profile, user_message),
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
        # Sin selección clara (preguntó otra cosa): seguir el pipeline normal.

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
        rec_profiles = db.list_catalog_profiles_for_species(prev_captured.get("species"), limit=6)
        if rec_profiles:
            _clear_field_for_correction(prev_captured, "exam_type")
            prev_captured["_profile_menu_options"] = [
                {"code": p.get("code"), "name": p.get("name"), "price": int(p.get("price") or 0)}
                for p in rec_profiles if p.get("code")
            ]
            return _persist_turn(
                chat_id, user_message,
                _base_route_response(
                    _format_profile_recommendation(prev_captured.get("species"), rec_profiles),
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
        # Cambio TOTAL de análisis ('otro análisis', 'cambiemos el perfil'): limpiar el
        # análisis reofrecido de la orden anterior y dejar que el flujo lo vuelva a pedir
        # (recomendación o selección). El ajuste PARCIAL ('el mismo pero sin X') NO entra
        # acá: lo maneja la personalización del perfil base más adelante.
        if _wants_to_change_analysis(user_message):
            _clear_field_for_correction(prev_captured, "exam_type")
            # No retornamos: el resto del mensaje puede traer datos del paciente; el flujo
            # sigue capturando y, al llegar al análisis vacío, recomienda o pregunta.
        if _is_correction_request(user_message) or _is_negative_text(user_message):
            field = _detect_correction_field(user_message)
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
        if _is_order_confirmation(user_message):
            missing = _missing_route_field(session, prev_captured)
            question = _missing_route_field_question(missing) if missing else "¿Qué análisis o perfil desean?"
            guide = "Listo. Para esta orden cambia normalmente el paciente, el propietario y el análisis. "
            return _persist_turn(chat_id, user_message, _base_route_response(guide + question, prev_captured))
        # Respuesta con datos del paciente u otra cosa: seguir el pipeline normal
        # (los datos estables ya están cargados y se conservan al fusionar).

    # "el de siempre" / "el mismo" para un campo del que NO hay dato recordado: pedirlo
    # normal, en vez de que el modelo reofrezca otro dato disponible (p. ej. la dirección).
    if (
        session.get("intent_current") == "route_scheduling"
        and session.get("phase_current") not in TERMINAL_PHASES
        and (session.get("client_id") or prev_captured.get("_client_found"))
        and _is_same_as_previous(user_message)
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
            and (_is_correction_request(user_message) or _wants_to_change_analysis(user_message))):
        field = _detect_correction_field(user_message)
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
        operational_answer = _operational_side_question_answer(user_message)
        if operational_answer:
            ai_response = _base_route_response(f"{operational_answer}\n\n{CLOSING_PROMPT}", dict(prev_captured))
            ai_response["phase"] = session.get("phase_current")
            ai_response["message_mode"] = "side_question"
            return _persist_turn(chat_id, user_message, ai_response)

        close_words = {"cierra", "cerrar", "cerramos", "cierralo", "ciérralo", "cerrada", "cerrado"}
        if not _explicitly_wants_another_order(user_message) and (
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
        if _is_negative_text(user_message):
            db.save_message(chat_id, user_message, "user")
            db.save_message(chat_id, FAREWELL_REPLY, "bot")
            return FAREWELL_REPLY
        tokens = set(_tokenize(user_message))
        if tokens & {"reptil", "reptiles"} or (tokens & {"hacen", "atienden"} and tokens & _ANALYSIS_TOKENS):
            return _persist_turn(chat_id, user_message, _unknown_handoff_response(dict(prev_captured)))

    # Nueva orden tras una YA registrada, aunque la conversación haya seguido con turnos
    # intermedios (charla, agradecimiento) que sacaron la sesión de la fase terminal. Sin
    # esto, el pedido de "otra orden" no reiniciaba y arrastraba los datos de la orden previa.
    # Se dispara también cuando el cliente vuelve con la sesión identificada (client_id) pero
    # el intent_current no es exactamente "route_scheduling" (ej. sesión parcialmente reiniciada),
    # evitando que el AI salte directo a "¿Cuál es el médico solicitante?" sin contexto.
    if (
        prev_captured.get("_order_registered")
        and session.get("phase_current") not in TERMINAL_PHASES
        and not prev_captured.get("_stable_confirm_pending")
        and (session.get("intent_current") == "route_scheduling" or session.get("client_id"))
        and _explicitly_wants_another_order(user_message)
    ):
        if _wants_to_change_client(user_message):
            return _persist_turn(
                chat_id, user_message,
                _restart_identification_for_new_client(chat_id, session, prev_captured),
            )
        return _persist_turn(chat_id, user_message, _begin_followup_order(prev_captured, user_message))

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

    # Mantener metadata de turno anterior (campos con _)
    for k, v in prev_captured.items():
        if k.startswith("_") and k != "_pending_intents" and k not in fields:
            fields[k] = v

    _merge_existing_route_fields(prev_captured, fields)
    _apply_common_order_fallbacks(fields, user_message)

    # Paciente sin dueño (callejero/rescatado): si se está pidiendo el propietario y el cliente
    # indica que no hay, se registra como "Sin propietario" y se avanza, en vez de repreguntar
    # en bucle (regla de negocio confirmada 2026-06-23).
    if _says_no_owner(user_message) and _detect_which_field_is_being_asked(history) == "owner_name":
        fields["owner_name"] = "Sin propietario"

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
        missing = _missing_route_field(session, fields)
        if missing and missing != "payment_method":
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
            and _select_client_match(user_message, fields)
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
                    selected_client = _select_client_match(user_message, fields)
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

    if not skip_client_lookup and prev_captured.get("_address_confirmation_pending"):
        # Si el flujo ya avanzó más allá de la dirección, esta quedó confirmada de
        # hecho: bajamos el flag para no reinterpretar un "no" posterior (p. ej. de
        # observaciones) como rechazo de la dirección.
        progressed = any(
            fields.get(f) or prev_captured.get(f)
            for f in ("requesting_doctor", "patient_name", "species", "exam_type")
        )
        if progressed and (fields.get("pickup_address") or prev_captured.get("pickup_address")):
            fields["_address_confirmation_pending"] = False
            fields["_address_confirmed"] = True
        elif _rejects_address(user_message):
            fields["pickup_address"] = None
            fields["_address_confirmation_pending"] = False
            fields["_address_confirmed"] = False
            ai_response = _base_route_response(
                "¿Cuál es la dirección correcta donde debemos retirar la muestra?",
                fields,
            )
        elif _confirms_address(user_message):
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
            if prev_captured.get("_awaiting_exact_name"):
                # SEGUNDO intento (el cliente rechazó la lista y le repreguntamos el nombre):
                # SOLO match EXACTO. Si el nombre coincide exacto con un registrado, se identifica;
                # si no, queda como no encontrado y abajo se pregunta si es cliente nuevo. Se prueba
                # el nombre que leyó el LLM y, de refuerzo (a veces lo captura con ruido), las
                # palabras significativas del mensaje. NUNCA match parcial aquí.
                fields.pop("_awaiting_exact_name", None)
                for cand in [fields.get("clinic_name")] + [
                    t for t in _tokenize(user_message)
                    if len(t) >= 4 and t not in _EXACT_RETRY_STOPWORDS
                ]:
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
                    if matches:
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
    ai_response = _enforce_multiple_tests_capture(session, ai_response, prev_captured)
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
    ai_response = _enforce_payment_step(session, ai_response, fields)
    ai_response = _enforce_profile_customization_changes(ai_response, prev_captured, user_message)
    fields = ai_response.get("captured_fields", fields)
    _normalize_name_fields(fields)
    ai_response["captured_fields"] = fields
    ai_response = _recover_enumerated_answer(ai_response, prev_captured, user_message, history)
    fields = ai_response.get("captured_fields", fields)
    ai_response = _recover_implied_animal_fields(ai_response, prev_captured, user_message)
    fields = ai_response.get("captured_fields", fields)
    ai_response = _clarify_ambiguous_species(ai_response, prev_captured, user_message, history)
    fields = ai_response.get("captured_fields", fields)
    ai_response = _recover_doctor_from_text(ai_response, prev_captured, user_message, history)
    fields = ai_response.get("captured_fields", fields)
    ai_response = _apply_handoff_guardrails(ai_response)
    ai_response = _avoid_redundant_client_identity_question(session, ai_response)
    ai_response = _avoid_forbidden_route_question(session, ai_response)
    ai_response = _avoid_redundant_route_field_question(session, ai_response)
    ai_response = _avoid_repeated_question(ai_response, history, prev_captured)
    ai_response = _apply_route_closure_summary(ai_response)
    ai_response = _clarify_captured_field(ai_response, prev_captured)
    ai_response = _enforce_field_coherence(session, ai_response, prev_captured, user_message, history)
    ai_response = _enforce_first_missing_after_progress(session, ai_response, prev_captured)
    ai_response = _resume_route_after_lateral_turn(session, ai_response)
    fields = ai_response.get("captured_fields", fields)

    previous_phase = session.get("phase_current", "")
    ai_response = _enforce_confirmation_step(session, ai_response, fields, previous_phase, user_message)
    # Red final antes de registrar: ninguna orden de ruta incompleta debe cerrarse/escalar.
    # Corre tras TODOS los guardrails de cierre (incluido el handoff por pago en línea
    # heredado en una orden de seguimiento), para no registrar órdenes vacías.
    fields = ai_response.get("captured_fields", fields)
    ai_response = _prevent_incomplete_route_closure(session, ai_response, fields)
    ai_response = _finalize_request(chat_id, session, ai_response, started_from_escalation, previous_phase)

    return _persist_turn(chat_id, user_message, ai_response)
