"""Consulta de resultados por chat (paso 3.4a del contrato).

Busca en los resultados YA CARGADOS Y PUBLICADOS en la plataforma los del cliente
que está escribiendo, y arma dos cosas: qué contesta el agente y qué PDFs hay que
mandarle por el mismo chat.

Regla de privacidad: el `client_id` sale SIEMPRE de la sesión, nunca del mensaje.
El cliente solo puede recibir lo suyo."""
import re

from app.services import portal_db

# Más de esto no se manda solo: se listan y el cliente elige. Evita descargar
# media docena de PDFs porque alguien escribió "mándame los resultados".
MAX_AUTO_SEND = 3
MAX_LISTED = 5

_ORDER_RE = re.compile(r"\bA3[-\s]?(\d{3,6})\b", re.IGNORECASE)


def order_number_in(text: str) -> str | None:
    """Número de orden legible mencionado en el mensaje (A3-00042)."""
    match = _ORDER_RE.search(text or "")
    return f"A3-{match.group(1)}" if match else None


def label(result: dict) -> str:
    """Cómo se nombra un resultado al cliente: paciente, examen y orden."""
    parts = [p for p in (result.get("patient_name"), result.get("exam_name")) if p]
    name = " · ".join(parts) if parts else "Resultado"
    order = result.get("order_number")
    return f"{name} ({order})" if order else name


def pdf_filename(result: dict) -> str:
    """Nombre del archivo que ve el cliente en el chat."""
    base = " - ".join(p for p in ("Resultado", result.get("patient_name"), result.get("exam_name")) if p)
    clean = re.sub(r"[^\w\sáéíóúÁÉÍÓÚñÑ.-]", "", base).strip() or "Resultado"
    return f"{clean[:90]}.pdf"


def find(client_id: str, patient: str | None = None, order_number: str | None = None,
         limit: int = 20) -> list[dict]:
    """Resultados publicados del cliente, del más nuevo al más viejo."""
    filters: dict = {}
    if order_number:
        filters["order_number"] = order_number
    elif patient:
        filters["patient"] = patient
    return portal_db.list_lab_results(filters, client_id=client_id, only_published=True, limit=limit)


def build_response(client_id: str, patient: str | None, order_number: str | None) -> tuple[str, list[str]]:
    """Devuelve (texto de la respuesta, ids de los resultados a enviar)."""
    asked_for = order_number or patient
    found = find(client_id, patient=patient, order_number=order_number)

    if found and len(found) <= MAX_AUTO_SEND:
        if len(found) == 1:
            return (f"Acá tienes el resultado de {label(found[0])} 👇", [found[0]["id"]])
        listed = ", ".join(label(r) for r in found)
        return (f"Tengo {len(found)} resultados: {listed}. Te los mando 👇", [r["id"] for r in found])

    if found:
        listed = "\n".join(f"• {label(r)}" for r in found[:MAX_LISTED])
        return (
            f"Encontré varios resultados. Estos son los más recientes:\n{listed}\n"
            "¿Cuál te mando? Dime el paciente o el número de orden.",
            [],
        )

    # No hay coincidencias para lo que pidió: ver si tiene otros cargados.
    recent = find(client_id, limit=MAX_LISTED) if asked_for else []
    if recent:
        listed = "\n".join(f"• {label(r)}" for r in recent)
        return (
            f"No encuentro un resultado cargado para {asked_for}. Los últimos que tengo de tu "
            f"clínica son:\n{listed}\n¿Es alguno de esos?",
            [],
        )

    if asked_for:
        return (
            f"Todavía no tengo cargado el resultado de {asked_for}. Apenas el laboratorio lo "
            "publique te llega el aviso por aquí. ¿Te ayudo con algo más?",
            [],
        )
    return (
        "Por ahora no tengo resultados publicados para tu clínica. Apenas el laboratorio "
        "publique uno te llega el aviso por aquí. ¿Te ayudo con algo más?",
        [],
    )
