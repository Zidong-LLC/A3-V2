"""Detectores de confirmación / corrección / pedido de orden y su vocabulario."""
import re

from app.text import tokenize as _tokenize
from app.detectors.basico import _AFFIRMATIVE_TOKENS, _NEGATIVE_TOKENS, _is_affirmative_text

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
    "regístrame", "anota", "anotalo", "anótalo", "apunta", "agenda", "agendame", "agéndame",
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


# Palabras de relleno que acompañan a un "sí" sin agregarle ninguna intención. NO es una lista
# temática (no nombra análisis, ni campos, ni nada del dominio): es lo que se descuenta para
# ver si SOBRA contenido en el mensaje.
_CONFIRMATION_FILLERS = frozenset({
    "por", "favor", "gracias", "muchas", "muy", "amable", "ya", "esta", "está", "asi", "así",
    "eso", "esa", "ese", "todo", "y", "pero", "que", "es", "la", "el", "lo", "un", "una",
    "señor", "senor", "señora", "senora", "amigo", "amiga", "pues", "entonces", "bueno",
})


def _is_bare_confirmation(text: str) -> bool:
    """¿El mensaje es SOLO una confirmación, sin ninguna otra intención adentro?

    La pregunta no es "¿contiene un sí?" sino "¿queda algo si le sacamos el sí?". Un atajo
    determinístico solo puede responder con plantilla cuando el mensaje no dice nada más; en
    cuanto sobra contenido, la oración completa la tiene que leer el modelo.

    Nació de "Si análisis quiero perfil 653" (prueba en vivo 2026-08-14): el atajo del
    reofrecimiento de estables vio el "Si" inicial, contestó su plantilla y descartó el resto
    de la frase — el código 653 se perdía y la orden seguía con el perfil heredado.
    Se mide por lo que SOBRA, y no con una lista de palabras del dominio, justamente para que
    funcione con cualquier fraseo y no haya que ir agregando casos."""
    if not _is_order_confirmation(text):
        return False
    resto = [t for t in _tokenize(text)
             if t not in _CONFIRM_ORDER_TOKENS and t not in _CONFIRMATION_FILLERS]
    return not resto


def _is_correction_request(text: str) -> bool:
    return bool(set(_tokenize(text)) & _CORRECTION_TOKENS)


# Campo de la orden al que apunta una corrección ('la raza es tobiano' → breed).
# Movido de agent.py (ERR-069) para que los enforcers puedan consultarlo sin ciclo.
_CORRECTION_FIELD_KEYWORDS = (
    (("direccion", "dirección", "domicilio", "retiro"), "pickup_address"),
    # ERR-099: corregir el CLIENTE no estaba en esta lista, así que "el cliente, soy Animal
    # Pets" caía en patient_name por la palabra "animal" y solo se reescribía el nombre: la
    # orden quedaba con el NIT, la dirección y el motorizado del cliente anterior. Va DESPUÉS
    # de la dirección a propósito — "cambia la dirección de la veterinaria" es una corrección
    # de dirección, no de cliente — y ANTES del paciente, para que gane la palabra específica.
    (("cliente", "veterinaria", "clinica", "clínica", "sede"), "clinic_name"),
    (("medico", "médico", "solicitante", "doctor", "doctora"), "requesting_doctor"),
    (("paciente", "perro", "perra", "gato", "gata", "animal", "mascota"), "patient_name"),
    (("especie",), "species"),
    (("raza",), "breed"),
    (("sexo", "macho", "hembra"), "sex"),
    (("edad",), "patient_age"),
    (("propietario", "dueño", "dueno", "dueña", "duena"), "owner_name"),
    # Va antes de 'observaciones' y del análisis: "cambia la fecha de la toma" es de este
    # campo, no del examen. 'toma'/'tomaron' cubren "la muestra la tomaron ayer".
    (("fecha", "toma", "tomaron", "tomamos"), "sample_taken_date"),
    (("observacion", "observación", "observaciones"), "observations"),
    (("analisis", "análisis", "examen", "examenes", "exámenes", "perfil", "prueba", "pruebas"), "exam_type"),
    (("pago",), "payment_method"),
)

# Datos ESTABLES de la orden (paciente/médico/dirección): una corrección de estos campos
# no pertenece a ningún carril de análisis/pago — el carril debe ceder el turno (ERR-069).
_STABLE_ORDER_FIELDS = frozenset({
    "requesting_doctor", "patient_name", "species", "breed", "sex",
    "patient_age", "owner_name", "pickup_address", "sample_taken_date",
})


def _detect_correction_field(text: str) -> str | None:
    tokens = set(_tokenize(text))
    for keywords, field in _CORRECTION_FIELD_KEYWORDS:
        if tokens & set(keywords):
            return field
    return None


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
    (ej. 'perdón, me confundí de opción'). No es un dato a capturar.

    ERR-086: la muletilla de duda 'si no me equivoco' / 'no me confundo' NO es una
    equivocación — el token NEGADO (un 'no' hasta 2 palabras antes) no dispara. Sin esto,
    'Agrocol estamos registrados si no me equivoco' reseteaba al menú y tiraba el nombre."""
    toks = _tokenize(text)
    words = set(toks)
    if not words:
        return False
    negated_correction = False
    for i, tok in enumerate(toks):
        if tok in _OPTION_CORRECTION_TOKENS:
            if "no" in toks[max(0, i - 2):i]:
                negated_correction = True
            else:
                return True
    hints = words & _RECONSIDER_HINT_TOKENS
    if negated_correction:
        # El 'no' que NIEGA la equivocación no cuenta también como pista de volver al menú.
        hints -= {"no"}
    return bool(words & _OPTION_WORDS and hints)


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


_THATS_ALL_PHRASES = (
    "asi esta bien", "asi estamos bien", "eso es todo", "eso seria todo", "seria todo",
    "es todo", "nada mas", "ya esta", "ya estamos", "dejalo asi", "asi dejalo",
    "no mas ordenes", "no cargo mas", "ninguna mas", "ninguna otra", "no tengo mas",
)


def _says_thats_all(text: str) -> bool:
    """¿El cliente da por terminada la carga ("No, así está bien", "eso es todo")?

    Red del cierre del pedido (Ronda 6): a la oferta "¿otra orden… o cerramos?" el cliente
    contesta "No, así está bien" y el modelo suele marcarla `affirm` (lee la conformidad),
    no `negate` — la señal sola dejaba el pedido abierto y el turno se lo llevaba cualquier
    otro empuje. Frases completas normalizadas, no tokens sueltos: un "no" pelado no alcanza
    y "no, agregale una glucosa" no matchea ninguna."""
    from app.text import ACCENT_TRANSLATION
    norm = " ".join(t.translate(ACCENT_TRANSLATION) for t in _tokenize(text))
    return any(p in norm for p in _THATS_ALL_PHRASES)


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


_SAME_AS_PREVIOUS_TOKENS = frozenset({
    "mismo", "misma", "mismos", "mismas", "igual", "iguales",
    "anterior", "antes", "previo", "repetir", "repetido",
    "repetimos", "igualito", "siempre", "costumbre",
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
