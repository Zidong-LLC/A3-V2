"""Detectores de intención por texto (texto → bool) y su vocabulario.

Extraídos de `agent.py` (Paso 3.4 del refactor: partir el monolito). Son funciones puras
que solo dependen de la tokenización (`app.text`) y de su propio vocabulario — sin lógica de
negocio ni I/O. Cubren: conversación básica, elección de menú, cliente nuevo, perfil,
dirección/sin-propietario y confirmación/corrección/pedido de orden.

NOTA (deuda de organización): el archivo pasó de 200 líneas; cuando sume el resto de los
detectores conviene partirlo en un paquete `app/detectors/` por tema (basico/orden/cliente…).
"""
import re

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


# ── Detectores de dirección y "sin propietario" ─────────────────────────────────
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


# ── Detectores de confirmación / corrección / pedido de orden ──────────────────
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
