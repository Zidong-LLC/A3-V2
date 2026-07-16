"""Detectores de dirección y "sin propietario" y su vocabulario."""
import re

from app.text import tokenize as _tokenize
from app.detectors.basico import _AFFIRMATIVE_TOKENS, _NEGATIVE_TOKENS, _is_negative_text

_ADDRESS_CONFIRM_TOKENS = _AFFIRMATIVE_TOKENS | {
    "ese", "esa", "eso", "esos", "esas", "correcta", "correcto",
    "asi", "así", "afirmativo", "confirmo", "confirmado", "seguro", "vale",
}

_NO_OWNER_TOKENS = frozenset({
    "ninguno", "ninguna", "callejero", "callejera", "callejeros", "callejeras",
    "rescatado", "rescatada", "rescate",
})
_NO_OWNER_PHRASES = (
    "sin dueño", "sin dueno", "sin propietario", "sin amo",
    "no tiene dueño", "no tiene dueno", "no tiene propietario", "no tiene amo",
    "no hay dueño", "no hay dueno", "no aplica", "no sabemos",
)


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


def _says_no_owner(text: str) -> bool:
    """El cliente indica que el paciente NO tiene propietario (callejero, rescatado, etc.).
    Solo se usa cuando se está pidiendo el propietario, así 'ninguna' es inequívoco ahí."""
    low = (text or "").lower()
    if any(p in low for p in _NO_OWNER_PHRASES):
        return True
    return bool(set(_tokenize(text)) & _NO_OWNER_TOKENS)
