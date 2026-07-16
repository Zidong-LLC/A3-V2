"""Detectores de confirmación / corrección / pedido de orden y su vocabulario."""
import re

from app.text import tokenize as _tokenize
from app.detectors.basico import _NEGATIVE_TOKENS, _is_affirmative_text

_CORRECTION_TOKENS = frozenset({
    "corregir", "corrige", "corrijo", "cambiar", "cambia", "cambie", "modificar",
    "modifica", "editar", "edita", "arreglar", "incorrecto", "mal", "equivocado",
    "equivoqué", "equivoque", "no",
})

_CONFIRM_ORDER_TOKENS = frozenset({
    "si", "sí", "confirmo", "confirmar", "confirmado", "correcto", "exacto",
    "dale", "ok", "okay", "listo", "perfecto", "bien", "registralo", "regístralo",
})

_ORDER_REQUEST_TOKENS = frozenset({
    "quiero", "necesito", "deseo", "dame", "hazme", "registra", "registrame",
    "regístrame", "anota", "anótalo", "apunta", "agenda", "agendame", "agéndame",
    "confirmo", "solicito", "pedimos", "programa", "programame", "prográmame",
    "confirmame", "confírmame", "confirmas", "confirmás", "confirma",
})

_OPTION_CORRECTION_TOKENS = frozenset({
    "confundi", "confundí", "confundido", "confundida", "confundir",
    "equivoque", "equivoqué", "equivoco", "equivocada", "equivocado",
})

_OPTION_WORDS = frozenset({"opcion", "opción", "opciones", "menu", "menú"})

_RECONSIDER_HINT_TOKENS = frozenset({
    "otra", "otras", "cambiar", "cambio", "cambie", "no", "volver", "regresar",
    "mal", "distinta", "distinto", "diferente",
})

_HANDOFF_ACCEPT_TOKENS = frozenset({
    "derivame", "derivar", "deriva", "deriven", "derivenme", "persona", "humano",
    "asesor", "agente", "registrar", "registra", "registrame", "regístrame", "registralo",
    "regístralo", "comunicame", "comunícame", "contactenme", "contáctenme",
})


def _is_order_confirmation(text: str) -> bool:
    tokens = set(_tokenize(text))
    if tokens & _CORRECTION_TOKENS:
        return False
    return bool(tokens & _CONFIRM_ORDER_TOKENS)


def _is_correction_request(text: str) -> bool:
    return bool(set(_tokenize(text)) & _CORRECTION_TOKENS)


def _expresses_order_request(text: str) -> bool:
    """¿El mensaje PIDE/ordena análisis (no solo consulta el precio)? 'quiero cuadro
    hemático y creatinina, ¿cuánto sale?' es un pedido con consulta — la elección debe
    capturarse, no solo responderse el valor. 'quiero saber cuánto sale' NO es pedido."""
    normalized = " ".join(_tokenize(text))
    if re.search(r"\b(quiero|necesito|deseo|quisiera)\s+(saber|preguntar|consultar|cotizar|conocer)\b", normalized):
        return False
    tokens = set(_tokenize(text))
    hits = tokens & _ORDER_REQUEST_TOKENS
    # "¿me confirmas el precio/valor?" es consulta pura, no un pedido de registrar.
    if hits <= {"confirma", "confirmas", "confirmás", "confirmame", "confírmame"} and \
            re.search(r"\bconfirm\w*\s+(el\s+|la\s+)?(precio|valor|costo|cuanto|cuánto)\b", normalized):
        return False
    return bool(hits)


def _wants_to_reconsider_option(text: str) -> bool:
    """El usuario indica que se confundió de opción o quiere volver a elegir
    (ej. 'perdón, me confundí de opción'). No es un dato a capturar."""
    words = set(_tokenize(text))
    if not words:
        return False
    if words & _OPTION_CORRECTION_TOKENS:
        return True
    return bool(words & _OPTION_WORDS and words & _RECONSIDER_HINT_TOKENS)


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


def _confirms_order_now(ai_response: dict, user_message: str) -> bool:
    """¿El cliente confirma la orden en este turno? Fuente primaria: la lectura semántica
    de la IA (`user_intent_signal`); fallback: tokens de confirmación. Si la IA leyó OTRA
    intención (corrección, negación, cambio de cliente, otra orden, cancelar) no se cierra
    por tokens — se respeta al modelo. Así 'dale, me sirve' o 'listo, cerremos' cierran
    aunque no estén en la lista, y un 'sí' incidental dentro de una corrección no dispara el
    cierre (Etapa 2 de la comprensión por IA — ERR-011 / ABIERTO-003)."""
    signal = ai_response.get("user_intent_signal")
    if signal == "affirm":
        return True
    if signal in {"negate", "correction", "change_client", "another_order", "cancel"}:
        return False
    return _is_order_confirmation(user_message)
