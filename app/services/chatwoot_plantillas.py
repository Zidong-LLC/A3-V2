"""Mensajes con plantilla de WhatsApp por Chatwoot (informe de A3 del 25/11, punto 6).

WhatsApp solo deja escribirle a alguien dentro de las 24 h desde su último mensaje. Fuera de
esa ventana hace falta una PLANTILLA aprobada por Meta en el WhatsApp Manager de A3. Esto
permite avisarle al motorizado aunque no haya escrito ese día (antes tenía que escribir cada
mañana). Chatwoot 4.11: `template_params` con `processed_params.body` (documentación oficial).

No hace falta configurar nada: el canal de WhatsApp y la plantilla se leen de Chatwoot, que
sincroniza las plantillas de Meta. Mientras la plantilla no esté APROBADA, no se usa.
"""
import json
import urllib.parse
import urllib.request

from app.config import CHATWOOT_API_TOKEN
from app.services.chatwoot import _BASE, _TIMEOUT

_HEADERS = {"Content-Type": "application/json", "api_access_token": CHATWOOT_API_TOKEN}


def _pedir(metodo: str, ruta: str, cuerpo: dict | None = None) -> dict:
    datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
    req = urllib.request.Request(f"{_BASE}{ruta}", data=datos, headers=_HEADERS, method=metodo)
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
        crudo = r.read()
    return json.loads(crudo) if crudo else {}


def plantilla_aprobada(nombre: str) -> dict | None:
    """{inbox_id, idioma} si el canal de WhatsApp tiene esa plantilla aprobada por Meta."""
    for inbox in _pedir("GET", "/inboxes").get("payload") or []:
        if inbox.get("channel_type") != "Channel::Whatsapp":
            continue
        for plantilla in inbox.get("message_templates") or []:
            if plantilla.get("name") == nombre and str(plantilla.get("status") or "").upper() == "APPROVED":
                return {"inbox_id": int(inbox["id"]), "idioma": plantilla.get("language") or "es"}
    return None


def puede_responder(conversation_id: str) -> bool:
    """¿La ventana de 24 h está abierta? Chatwoot lo dice en `can_reply`."""
    return bool(_pedir("GET", f"/conversations/{conversation_id}").get("can_reply"))


def _plantilla(texto: str, nombre: str, idioma: str, valores: list[str]) -> dict:
    # Meta rechaza un parámetro vacío: lo que falte va como «-».
    cuerpo = {str(i): (str(v).strip() or "-") for i, v in enumerate(valores, start=1)}
    return {"content": texto, "message_type": "outgoing", "private": False,
            "template_params": {"name": nombre, "category": "UTILITY", "language": idioma,
                                "processed_params": {"body": cuerpo}}}


def enviar(conversation_id: str, texto: str, nombre: str, idioma: str, valores: list[str]) -> None:
    _pedir("POST", f"/conversations/{conversation_id}/messages", _plantilla(texto, nombre, idioma, valores))


def _contacto(telefono: str, nombre: str, inbox: int) -> tuple[int, str]:
    """(id del contacto, source_id en el canal de WhatsApp). Lo busca por teléfono o lo crea."""
    digitos = telefono.lstrip("+")
    for c in _pedir("GET", f"/contacts/search?q={urllib.parse.quote(telefono)}").get("payload") or []:
        if "".join(ch for ch in str(c.get("phone_number") or "") if ch.isdigit()) != digitos:
            continue
        for ci in c.get("contact_inboxes") or []:
            if int((ci.get("inbox") or {}).get("id") or 0) == inbox and ci.get("source_id"):
                return int(c["id"]), str(ci["source_id"])
        ci = _pedir("POST", f"/contacts/{c['id']}/contact_inboxes", {"inbox_id": inbox, "source_id": digitos})
        return int(c["id"]), str(ci.get("source_id") or digitos)
    creado = _pedir("POST", "/contacts", {"inbox_id": inbox, "name": nombre, "phone_number": telefono})
    datos = creado.get("payload") or creado
    contacto = datos.get("contact") or datos
    source = (datos.get("contact_inbox") or {}).get("source_id") or digitos
    return int(contacto["id"]), str(source)


def abrir_conversacion(telefono: str, nombre: str, texto: str, plantilla: str, idioma: str,
                       valores: list[str], inbox: int) -> str:
    """Abre una conversación de WhatsApp con alguien que nunca escribió, empezando por la
    plantilla. Devuelve el id de la conversación. `telefono` en formato +57XXXXXXXXXX."""
    contacto_id, source_id = _contacto(telefono, nombre, inbox)
    conversacion = _pedir("POST", "/conversations", {
        "source_id": source_id, "inbox_id": inbox, "contact_id": contacto_id,
        "status": "pending", "message": _plantilla(texto, plantilla, idioma, valores)})  # pending: lo atiende el bot
    return str(conversacion["id"])
