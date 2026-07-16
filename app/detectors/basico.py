"""Detectores de conversación básica (texto → bool) y su vocabulario.

Parte del paquete app/detectors (Paso 3.4): funciones puras que solo dependen de la
tokenización (app.text) — sin lógica de negocio ni I/O.
"""
from app.text import tokenize as _tokenize

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
