"""Detectores de perfil (personalización / confirmación / cierre) y su vocabulario."""
from app.text import tokenize as _tokenize

_PROFILE_CUSTOMIZE_TOKENS = frozenset({
    "personalizar", "personalizarlo", "modificar", "ajustar", "ajustarlo",
    "agregar", "agrega", "agregarle", "agregale", "agregarlo", "añadir", "anadir", "sumar", "incluir", "quitar", "quita",
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
