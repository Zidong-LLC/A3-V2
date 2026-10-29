"""Preguntas cerradas con opciones numeradas (pedido de A3, 2026-10-29).

El personal de A3 pidió que las preguntas de sí/no del flujo de la orden («¿agregamos otro
análisis o la dejamos así?») se contesten con un número, como el menú de bienvenida. Un
número no tiene ambigüedad: «2» no puede caer en la rama de corrección ni leerse como otra
cosa.

Es UN mecanismo para todas las preguntas, sin lógica repetida por pregunta:
- Al salir, si la respuesta del bot contiene una pregunta cerrada conocida, se le anexan las
  opciones numeradas y se guarda qué significa cada número (`_opciones_cerradas`).
- Al entrar, si el cliente contesta solo con el número, el mensaje se traduce al texto que el
  flujo YA entiende antes de interpretarlo. La marca vive un solo turno.
"""
import re

from app.messages import (
    EXTRA_ANALYSIS_OFFER,
    PAYMENT_METHOD_QUESTION,
    PEDIDO_CLOSING_PROMPT,
    PEDIDO_CLOSING_QUESTION,
    PEDIDO_OFFER_REASK,
)

CLAVE = "_opciones_cerradas"

OBSERVACION_PREGUNTA = (
    "Por último, ¿quieres dejar alguna observación para la orden o la registramos sin observaciones?"
)
REOFERTA_ESTABLES = "¿Confirmas o quieres cambiar alguno ("

_OTRA_ORDEN_O_CIERRE = [
    ("Otra orden para otro paciente", "otra orden para otro paciente"),
    ("Continuar con el pago", "no, eso es todo, cerramos el pedido"),
]
_FORMA_DE_PAGO = [
    ("Contraentrega con el motorizado", "contraentrega"),
    ("Pago en línea", "pago en línea"),
]

# (texto de la pregunta tal como la emite el bot, [(etiqueta, texto que el flujo entiende)]).
# El orden importa: se toma la PRIMERA pregunta que aparezca en la respuesta.
PREGUNTAS: list[tuple[str, list[tuple[str, str]]]] = [
    (EXTRA_ANALYSIS_OFFER, [
        ("Agregar otro análisis", "sí, quiero agregar otro análisis"),
        ("Dejarla así", "no, la dejamos así"),
    ]),
    (OBSERVACION_PREGUNTA, [
        ("Dejar una observación", "sí, quiero dejar una observación"),
        ("Sin observaciones", "sin observaciones"),
    ]),
    (PEDIDO_CLOSING_PROMPT, _OTRA_ORDEN_O_CIERRE),
    (PEDIDO_OFFER_REASK, _OTRA_ORDEN_O_CIERRE),
    (PEDIDO_CLOSING_QUESTION, _FORMA_DE_PAGO),
    (PAYMENT_METHOD_QUESTION, _FORMA_DE_PAGO),
]

# Reoferta de datos heredados: «¿Confirmas o quieres cambiar alguno (dirección, médico o
# análisis)?» — las opciones salen del paréntesis, que varía según lo que se heredó.
_CAMBIABLES = {
    "dirección": ("Cambiar la dirección", "quiero cambiar la dirección"),
    "médico": ("Cambiar el médico", "quiero cambiar el médico"),
    "análisis": ("Cambiar el análisis", "quiero cambiar el análisis"),
    "pago": ("Cambiar la forma de pago", "quiero cambiar la forma de pago"),
}

_ELECCION = re.compile(r"^\s*(?:opci[oó]n\s*|la\s*|el\s*|n[uú]mero\s*)?(\d)\s*[.)]?\s*$", re.IGNORECASE)


def _opciones_de(reply: str) -> list[tuple[str, str]] | None:
    for pregunta, opciones in PREGUNTAS:
        if pregunta in reply:
            return opciones
    inicio = reply.find(REOFERTA_ESTABLES)
    if inicio < 0:
        return None
    dentro = reply[inicio + len(REOFERTA_ESTABLES):].split(")")[0]
    cambios = [_CAMBIABLES[c] for c in _CAMBIABLES if c in dentro]
    return [("Confirmar estos datos", "confirmo")] + cambios if cambios else None


def agregar(ai_response: dict) -> dict:
    """Anexa las opciones numeradas a la respuesta y guarda su significado para el turno
    siguiente. Con un menú de análisis/perfiles pendiente no hace nada: ahí los números ya
    son del menú."""
    fields = ai_response.get("captured_fields")
    reply = ai_response.get("reply") or ""
    if not isinstance(fields, dict) or CLAVE in fields:
        return ai_response
    if fields.get("_test_menu_options") or fields.get("_profile_menu_options"):
        return ai_response
    opciones = _opciones_de(reply)
    if not opciones:
        return ai_response
    lineas = [f"{n}. {etiqueta}" for n, (etiqueta, _) in enumerate(opciones, start=1)]
    # Línea en blanco entre la pregunta y las opciones (pedido de A3, 29/10: «que se vea
    # bien separadito»).
    ai_response["reply"] = reply.rstrip() + "\n\n" + "\n".join(lineas)
    fields[CLAVE] = {str(n): texto for n, (_, texto) in enumerate(opciones, start=1)}
    return ai_response


def traducir(prev_captured: dict, user_message: str) -> str:
    """«2» → el texto de la opción 2. Borra la marca SIEMPRE: las opciones valen solo para
    la respuesta inmediata; un «2» dos turnos después ya no significa nada."""
    opciones = prev_captured.pop(CLAVE, None) if isinstance(prev_captured, dict) else None
    if not opciones:
        return user_message
    m = _ELECCION.match(user_message or "")
    if not m:
        return user_message
    return opciones.get(m.group(1), user_message)
