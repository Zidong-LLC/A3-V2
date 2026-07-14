"""Detectores de intención conversacional básica (texto → bool).

Extraídos de `agent.py` (Paso 3.4 del refactor: partir el monolito). Son funciones puras
que solo dependen de la tokenización (`app.text`) y de su propio vocabulario — sin lógica de
negocio ni I/O. Este módulo es el primer grupo de detectores movido; irán sumándose más a
medida que se confirme que cada grupo es cerrado (no llama a funciones que quedan en agent).
"""
from app.text import tokenize as _tokenize

# ── Vocabulario ─────────────────────────────────────────────────────────────────
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

_AFFIRMATIVE_TOKENS = frozenset({
    "si", "sí", "ok", "okay", "listo", "perfecto", "claro", "bien",
    "correcto", "exacto", "dale", "sip", "aja", "ajá",
})

_NEGATIVE_TOKENS = frozenset({"no", "nop", "negativo", "incorrecto", "otra", "diferente"})

_RESULTS_CHOICE_TOKENS = frozenset({"2", "dos", "resultado", "resultados"})
_OTHER_CHOICE_TOKENS = frozenset({"4", "cuatro", "otro", "otra"})

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

_ARMED_PROFILE_TOKENS = frozenset({
    "armado", "armados", "armadas", "prearmado", "prearmados", "prearmadas",
    "predefinido", "predefinidos", "predefinida", "predefinidas", "hechos", "listos",
})


# ── Detectores ──────────────────────────────────────────────────────────────────
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


def _is_affirmative_text(text: str) -> bool:
    words = set(_tokenize(text))
    return bool(words & _AFFIRMATIVE_TOKENS) and len(words) <= 5


def _is_negative_text(text: str) -> bool:
    words = set(_tokenize(text))
    return bool(words & _NEGATIVE_TOKENS) and len(words) <= 8


def _is_results_choice(text: str) -> bool:
    """El usuario eligió la opción 2 del menú (consultar resultados)."""
    words = _tokenize(text)
    return bool(set(words) & _RESULTS_CHOICE_TOKENS) and len(words) <= 4


def _is_other_choice(text: str) -> bool:
    """El usuario eligió la opción 4 del menú (otro)."""
    words = _tokenize(text)
    return bool(set(words) & _OTHER_CHOICE_TOKENS) and len(words) <= 4


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


# ── Detectores de perfil (personalización / confirmación / cierre) ──────────────
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


def _is_ambiguous_profile_change(text: str) -> bool:
    tokens = set(_tokenize(text))
    return bool(tokens & _PROFILE_CUSTOMIZE_TOKENS) and bool(tokens & _AMBIGUOUS_PROFILE_TOKENS)


def _asks_for_armed_profiles(text: str) -> bool:
    """¿El cliente pregunta por perfiles ya armados/prearmados del catálogo?
    Ej.: '¿no tienes perfiles armados?'."""
    tokens = set(_tokenize(text))
    return bool(tokens & {"perfil", "perfiles"}) and bool(tokens & _ARMED_PROFILE_TOKENS)
