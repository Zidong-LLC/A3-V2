"""Aviso al motorizado cuando se le asigna o reasigna una recogida.

Decisión del usuario (2026-08-31), pedida por A3 en las llamadas 1, 2 y 4: el aviso va por
Chatwoot, a la conversación vinculada en la tarjeta del motorizado (columna
`couriers.chatwoot_conversation_id`, migración 032). El fallo del aviso NUNCA frena la
asignación: se loggea.

Informe de A3 del 25/11 (punto 6, brecha B1): el aviso solo llegaba si el motorizado había
escrito en las últimas 24 h (regla de WhatsApp), así que en la práctica no le llegaba a nadie.
Ahora, si el canal de WhatsApp tiene la plantilla `recogida_asignada` APROBADA por Meta:
- ventana abierta → mensaje normal (sin costo de plantilla);
- ventana cerrada → la plantilla, a su conversación;
- sin conversación → se abre una con su celular y queda vinculada en la tarjeta.
Sin la plantilla aprobada, todo sigue como antes.
"""
import logging
import re

logger = logging.getLogger(__name__)
PLANTILLA = "recogida_asignada"


def _texto(order_number: str, clinic: str, address: str, fecha: str, reasignada: bool) -> str:
    encabezado = "Recogida reasignada a vos" if reasignada else "Nueva recogida asignada"
    lineas = [f"🛵 {encabezado}", f"Orden: {order_number or 's/n'}"]
    if clinic:
        lineas.append(f"Veterinaria: {clinic}")
    if address:
        lineas.append(f"Dirección: {address}")
    if fecha:
        lineas.append(f"Fecha de recogida: {fecha}")
    return "\n".join(lineas)


def _celular(telefono) -> str | None:
    """+57 y los 10 dígitos del celular colombiano; None si no lo parece."""
    digitos = re.sub(r"\D", "", str(telefono or ""))
    if len(digitos) == 12 and digitos.startswith("57"):
        digitos = digitos[2:]
    return f"+57{digitos}" if len(digitos) == 10 and digitos.startswith("3") else None


def notify_assignment(courier_id: str | None, order_number: str = "", clinic: str = "",
                      address: str = "", fecha: str = "", reasignada: bool = False) -> bool:
    """Manda el aviso. Devuelve si salió. Imports diferidos para no crear ciclos con la capa db."""
    if not courier_id:
        return False
    try:
        from app.services import chatwoot, chatwoot_plantillas, db

        courier = db.get_courier(courier_id) or {}
        conversation = str(courier.get("chatwoot_conversation_id") or "").strip()
        texto = _texto(order_number, clinic, address, fecha, reasignada)
        try:  # si no se puede consultar, se sigue como antes (sin plantilla)
            plantilla = chatwoot_plantillas.plantilla_aprobada(PLANTILLA)
        except Exception:  # noqa: BLE001
            logger.warning("aviso motorizado: no se pudo consultar la plantilla en Chatwoot")
            plantilla = None
        if conversation and (not plantilla or chatwoot_plantillas.puede_responder(conversation)):
            chatwoot.send_message(conversation, texto)  # como siempre: dentro de la ventana
            return True
        if not plantilla:
            return False  # sin vínculo ni plantilla: como antes, alguien le avisa a mano
        valores = [order_number or "s/n", clinic, address, fecha]
        if conversation:
            chatwoot_plantillas.enviar(conversation, texto, PLANTILLA, plantilla["idioma"], valores)
            return True
        celular = _celular(courier.get("phone"))
        if not celular:
            logger.warning("aviso motorizado: %s no tiene un celular válido", courier.get("name"))
            return False
        nueva = chatwoot_plantillas.abrir_conversacion(celular, courier.get("name") or "Motorizado", texto,
                                                       PLANTILLA, plantilla["idioma"], valores,
                                                       plantilla["inbox_id"])
        db.update_courier(courier_id, {"chatwoot_conversation_id": nueva})  # queda vinculado
        return True
    except Exception:  # noqa: BLE001 — el aviso jamás frena la asignación
        logger.exception("No se pudo avisar al motorizado %s", courier_id)
        return False
