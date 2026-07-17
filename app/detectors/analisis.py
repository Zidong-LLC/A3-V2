"""Detectores y utilidades puras del ANÁLISIS/perfil (texto → señal).

Capa de detección que desbloquea la migración de enforcers (Paso 3.4): solo depende de
app.text/app.flow/otros detectores — sin I/O ni helpers de agent."""
import re

from app.text import tokenize as _tokenize
from app.detectors.orden import _is_same_as_previous, _SAME_AS_PREVIOUS_TOKENS
from app.detectors.basico import _AFFIRMATIVE_TOKENS, _NEGATIVE_TOKENS



_PARTIAL_KEEP_MARKERS = frozenset({"pero", "salvo", "excepto", "menos", "sin", "aunque", "mas", "más"})


_ANALYSIS_ADD_REMOVE_TOKENS = frozenset({
    "agregar", "agrega", "agregale", "agrégale", "agregarle", "agregarlo", "añadir",
    "anadir", "añade", "añadile", "sumar", "suma", "sumale", "incluir", "incluye", "incluile",
    "quitar", "quita", "quitale", "quítale", "sacar", "saca", "sacale", "sácale",
    "retirar", "retira", "remover", "remueve",
})


_ANALYSIS_CHANGE_SIGNAL_TOKENS = frozenset({
    "otro", "otra", "otros", "otras", "nuevo", "nueva", "distinto", "distinta",
    "diferente", "cambiar", "cambia", "cambie", "cambiarlo", "cambiamos",
})


_ANALYSIS_NOUN_TOKENS = frozenset({
    "analisis", "análisis", "examen", "examenes", "exámenes",
    "perfil", "perfiles", "prueba", "pruebas",
})


_PROFILE_SPECIFIC_SUFFIXES = frozenset({
    "i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x", "xi", "xii",
    "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12",
})


_PROFILE_DETAIL_TOKENS = frozenset({
    "incluye", "incluyen", "contiene", "contienen", "trae", "traen",
    "detalle", "detalles", "detallar", "componentes", "composicion", "composición",
})


_DOESNT_KNOW_PHRASES = (
    "no se", "no sé", "no estoy seguro", "no tengo claro", "ni idea",
    "no sabria", "no sabría", "no sé cuál", "no se cual",
)


_EXAM_ITEM_SEPARATOR = re.compile(r",|;|\n|\b y \b|\b e \b|\+", re.IGNORECASE)


_RECOMMENDATION_TOKENS = frozenset({
    "recomienda", "recomiendas", "recomiende", "recomienden", "recomiendan",
    "recomiendame", "recomiéndame", "recomendacion", "recomendación",
    "sugieres", "sugiere", "sugieran", "sugieren", "sugerencia", "sugerencias",
    "aconsejas", "aconseja", "conviene", "convienen", "convendria", "convendría",
})


_PRICE_QUESTION_TOKENS = frozenset({"cuanto", "cuánto", "cuesta", "costaria", "costaría", "valor", "precio", "cotizar", "cotizacion", "cotización"})

_TOTAL_QUESTION_TOKENS = frozenset({
    "todos", "todas", "total", "todo", "junto", "juntos", "completo", "suma", "sumando",
    "conjunto", "sumados",
})

_PRICE_STOPWORDS = _PRICE_QUESTION_TOKENS | _TOTAL_QUESTION_TOKENS | {
    "el", "la", "los", "las", "un", "una", "unos", "unas", "de", "del", "ese", "esos",
    "esa", "esas", "esto", "este", "estos", "y", "e", "o", "u", "me", "que", "es", "son",
    "seria", "serían", "serian", "sería", "sale", "saldria", "saldría", "para", "por",
    "con", "sin", "mas", "más", "todos", "analisis", "análisis", "examen", "examenes",
    "exámenes", "prueba", "pruebas", "perfil", "perfiles", "cada", "uno",
}


_ACTION_STOPWORDS = frozenset({
    "quiero", "quiere", "queria", "quería", "necesito", "agregar", "agrega", "agregame",
    "agregue", "agregarle", "agregarme", "sumar", "suma", "añadir", "anadir", "poner",
    "ponme", "incluir", "incluye", "otro", "otra", "otros", "otras", "tambien", "también",
    "quitar", "quita", "sacar", "saca", "eliminar", "elimina", "cambiar", "cambia",
})


_REMOVE_TOKENS = frozenset({"quitar", "quita", "quitale", "quítale", "sacar", "saca", "sacale",
                            "sácale", "sin", "menos", "retirar", "remover", "remueve"})


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



def _wants_to_change_analysis(text: str) -> bool:
    """¿El cliente quiere reemplazar el análisis/perfil por otro TOTALMENTE distinto
    (empezar el análisis de cero)? Ej.: 'con otro análisis', 'quisiste hacer otro análisis',
    'cambiemos el perfil'. NO aplica a un ajuste parcial ('el mismo pero sin X'): eso se
    mantiene y se personaliza, no se limpia."""
    if _wants_partial_analysis_change(text):
        return False
    tokens = set(_tokenize(text))
    return bool(tokens & _ANALYSIS_NOUN_TOKENS) and bool(tokens & _ANALYSIS_CHANGE_SIGNAL_TOKENS)



def _looks_like_catalog_profile(value: str | None) -> bool:
    text = (value or "").strip()
    if not text:
        return False
    tokens = set(_tokenize(text))
    return text.isdigit() or bool(tokens & {"perfil", "panel"})



def _looks_like_specific_profile_query(value: str | None) -> bool:
    tokens = _tokenize(value or "")
    return bool(tokens and (tokens[-1] in _PROFILE_SPECIFIC_SUFFIXES or any(token.isdigit() for token in tokens)))



def _is_profile_detail_question(text: str) -> bool:
    return bool(set(_tokenize(text)) & _PROFILE_DETAIL_TOKENS)



def _is_generic_blood_analysis(text: str | None) -> bool:
    tokens = set(_tokenize(text or ""))
    if not tokens or {"oculta", "oculto"} & tokens:
        return False
    return "sangre" in tokens and bool(tokens & {"analisis", "análisis", "examen", "prueba"})



def _doesnt_know_what_to_ask(text: str) -> bool:
    """¿El cliente responde que no sabe qué análisis pedir o pide ayuda/opciones?"""
    lower = (text or "").lower()
    if any(p in lower for p in _DOESNT_KNOW_PHRASES):
        return True
    return bool(set(_tokenize(text)) & {
        "opciones", "ayuda", "ayudame", "ayúdame", "orienta", "orientame",
        "oriéntame", "muestrame", "muéstrame", "orientas",
    })



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



def _profile_codes_from_text(text: str) -> list[str]:
    codes = []
    for code in re.findall(r"\b\d{3,4}\b", text or ""):
        if code not in codes:
            codes.append(code)
    return codes



def _last_bot_message(history: list[dict]) -> str:
    for msg in reversed(history):
        if msg["role"] == "bot":
            return msg["content"]
    return ""



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



def _wants_profile_recommendation(text: str) -> bool:
    """¿El cliente pide que le recomendemos o sugiramos un análisis o perfil?"""
    return bool(set(_tokenize(text)) & _RECOMMENDATION_TOKENS)



def _named_analysis_terms(text: str) -> list[str]:
    """Palabras de la pregunta que podrían nombrar un análisis (descarta las de precio,
    artículos, muletillas y verbos de acción). Sirve para resolver '¿cuánto sale el hemograma?'.
    Los dígitos sueltos de 1-2 cifras NO son códigos de análisis (los códigos tienen ≥3):
    admitirlos hacía que 'parasitológico 3' resolviera a 'T3 Total' por parecido de nombre."""
    stop = _PRICE_STOPWORDS | _ACTION_STOPWORDS
    return [
        t for t in _tokenize(text)
        if ((len(t) >= 4) or (t.isdigit() and len(t) >= 3)) and t not in stop
    ]



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



def _payment_method_from_text(text: str) -> str | None:
    tokens = set(_tokenize(text))
    if "contraentrega" in tokens or "efectivo" in tokens:
        return "contraentrega"
    if "pse" in tokens or "transferencia" in tokens or "tarjeta" in tokens:
        return "pago_linea"
    if ({"pago", "pagar"} & tokens) and ({"linea", "línea", "online"} & tokens):
        return "pago_linea"
    return None
