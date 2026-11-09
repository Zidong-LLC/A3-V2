"""Autorización de datos antes de empezar a conversar por WhatsApp (propuesta del 28/09).

Pedido de A3: antes del menú de 4 opciones, un mensaje con la política y dos botones. Con
«Sí» sigue todo como siempre; es lo único que cambia del flujo.

Vive antes del agente y no le deja rastro: estos mensajes no entran al historial, así el
primer turno real sigue viendo una conversación vacía y saluda con el menú de siempre. La
autorización es de la persona (por su número), no de la conversación.

Reglas:
- Un «sí» solo vale si ya se le mostró la pregunta: un «Si, buenas» de entrada no autoriza.
- Lo que no se entienda («no sé», «qué política») se vuelve a preguntar, no se adivina.
- Si esta verificación falla, el bot sigue atendiendo y llega el aviso técnico: una falla
  de esta tabla no puede dejar mudo el WhatsApp de A3.
"""
import logging

from app.alerts import notify_error
from app.config import PRIVACY_POLICY_URL, WHATSAPP_PRIVACY_ENABLED, WHATSAPP_PRIVACY_ONLY_NUMBERS
from app.services import chatwoot, db, privacy_db
from app.text import tokenize

logger = logging.getLogger(__name__)

VERSION_POLITICA = "2026-11-09"
PREGUNTA = (
    "¡Hola! En A3 laboratorio clínico veterinario nos encanta atenderte 😃\n\n"
    "Tus datos serán tratados de acuerdo con la **política de tratamiento de datos personales**, "
    f"que puedes consultar aquí:\n{PRIVACY_POLICY_URL}\n\n"
    "¿Estás de acuerdo?"
)
BOTONES = [{"title": "Sí 👍", "value": "si"}, {"title": "No 👎", "value": "no"}]
RECHAZO = ("Entendido, respetamos tu decisión. Sin tu autorización no podemos seguir por este "
           "canal. Si cambias de opinión, escríbenos y te volvemos a preguntar.")

_SI = {"si", "acepto", "aceptar", "autorizo", "acuerdo", "ok", "okay", "dale", "claro", "listo",
       "vale", "confirmo", "bueno", "correcto", "perfecto"}
_NO = {"no", "nop", "negativo", "rechazo"}
_RELLENO = {"de", "estoy", "gracias", "por", "favor", "senor", "senora", "doctor", "doctora"}


def _lectura(texto: str) -> str | None:
    """«si», «no» o None si la respuesta no dice ninguna de las dos. Con ráfagas de mensajes
    manda la primera línea: es la que contesta la pregunta."""
    lineas = (texto or "").strip().splitlines()
    primera = lineas[0] if lineas else ""
    if "👍" in primera:
        return "si"
    if "👎" in primera:
        return "no"
    tokens = set(tokenize(primera))
    if not tokens:
        return None
    if tokens & _NO:  # «no acepto» y «no estoy de acuerdo» son un no; «no sé», no
        return "no" if tokens <= _NO | _RELLENO | {"acepto", "autorizo", "acuerdo", "quiero"} else None
    return "si" if tokens & _SI and tokens <= _SI | _RELLENO else None


def _retomar(chat_id: str) -> bool:
    """Tras el «sí»: una conversación nueva sigue al agente, que saluda con el menú. Una que
    ya venía en curso retoma su última pregunta; un «sí» suelto ahí se leería como otra cosa."""
    historia = db.get_recent_messages(chat_id, limit=4)
    ultimo = next((m["content"] for m in reversed(historia) if m.get("role") == "bot"), None)
    if not ultimo:
        return False
    chatwoot.send_message(chat_id, f"Gracias por tu autorización. Seguimos donde íbamos:\n\n{ultimo}")
    return True


def atender(chat_id: str, texto: str, canal: str, telefono: str) -> bool:
    """True si el mensaje quedó resuelto acá; False si el agente debe atenderlo."""
    if not WHATSAPP_PRIVACY_ENABLED or canal != "whatsapp":
        return False
    contacto = (telefono or "").strip() or f"chat:{chat_id}"
    # Modo prueba: mientras haya números configurados, el resto sigue como antes.
    solo = WHATSAPP_PRIVACY_ONLY_NUMBERS
    if solo and "".join(ch for ch in contacto if ch.isdigit()) not in solo:
        return False

    def anotar(evento: str, respuesta: str | None = None) -> None:
        privacy_db.registrar(contacto, canal, chat_id, evento, VERSION_POLITICA, PRIVACY_POLICY_URL, respuesta)

    try:
        ultimo = privacy_db.ultimo_evento(contacto)
        if ultimo == "accepted":
            return False
        lectura = _lectura(texto) if ultimo else None  # sin pregunta previa, nada autoriza
        if lectura == "si":
            anotar("accepted", texto[:500])
            return _retomar(chat_id)
        if lectura == "no":
            chatwoot.send_message(chat_id, RECHAZO)
            anotar("rejected", texto[:500])
            return True
        chatwoot.send_options(chat_id, PREGUNTA, BOTONES)
        if ultimo is None:
            anotar("asked")
        return True
    except Exception as exc:  # noqa: BLE001 — ver la última regla del docstring
        logger.error("privacidad: falló para %s: %s", chat_id, exc)
        notify_error("autorización de datos en WhatsApp", exc, f"conversación {chat_id}")
        return False
