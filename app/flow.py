"""Capa de respuesta del flujo de recogida (Paso 3.4).

Helpers que construyen la respuesta determinística del flujo (siguiente campo faltante,
su pregunta, la respuesta base) y los cálculos de texto de dinero. Es la capa de la que
dependen los enforcers: al vivir acá, los enforcers pueden migrar a app/enforcers/ sin
imports circulares con agent.py. Los nombres públicos no llevan guion bajo; agent los
re-importa con alias para no tocar los ~200 call sites."""
from app.config import PEDIDOS_ENABLED
from app.text import tokenize as _tokenize, money as _money, as_text_items as _as_text_items
from app.messages import (
    AGE_QUESTION, PAYMENT_METHOD_QUESTION,
    EXTRA_ANALYSIS_OFFER, EXTRA_ANALYSIS_OFFER_PEDIDO,
)



AGE_UNIT_TOKENS = frozenset({"año", "años", "ano", "anos", "mes", "meses", "dia", "dias", "día", "días"})


def age_has_unit(value: str | None) -> bool:
    """La edad solo es válida si trae unidad (años/meses/días)."""
    return bool(set(_tokenize(value or "")) & AGE_UNIT_TOKENS)


# El análisis va ANTES que las observaciones: A3 lo pidió en la reunión del 28/07 porque la
# observación suele referirse al análisis pedido ("el hemograma que sea en ayunas"), y
# preguntarla antes obliga al cliente a anticiparse a algo que todavía no eligió.
ROUTE_ORDER_FIELDS_BEFORE_PAYMENT = (
    "pickup_address", "requesting_doctor",
    "patient_name", "species", "breed", "sex", "patient_age",
    "owner_name", "exam_type", "observations",
)


ROUTE_REQUIRED_FIELDS = ROUTE_ORDER_FIELDS_BEFORE_PAYMENT + ("payment_method",)


def order_required_fields() -> tuple[str, ...]:
    """Campos que exige UNA orden para estar completa.

    Con la jerarquía de pedidos (decisión 011) la forma de pago NO es un dato de la orden
    sino del PEDIDO: se pregunta una sola vez al cerrarlo, no una vez por paciente. Sin el
    flag, todo sigue igual que antes.

    Solo dos sitios deciden la secuencia con esto —`missing_route_field` y el armado del
    resumen—; el resto de los usos de ROUTE_REQUIRED_FIELDS solo recorre campos (snapshots,
    progreso) y no le molesta que `payment_method` esté vacío."""
    return ROUTE_ORDER_FIELDS_BEFORE_PAYMENT if PEDIDOS_ENABLED else ROUTE_REQUIRED_FIELDS


# Etiquetas en español de los campos de la orden (movidas de agent.py, ERR-069: los
# enforcers las necesitan para el acuse de correcciones sin import circular).
FIELD_LABELS = {
    "requesting_doctor": "médico solicitante",
    "patient_name": "nombre del paciente",
    "species": "especie",
    "breed": "raza",
    "sex": "sexo",
    "patient_age": "edad",
    "owner_name": "nombre del propietario",
    "pickup_address": "dirección de retiro",
    "exam_type": "análisis o perfil",
    "observations": "observaciones",
    "payment_method": "forma de pago",
}


def base_route_response(reply: str, fields: dict) -> dict:
    return {
        "reply": reply,
        "phase": "fase_2_recogida_datos",
        "intent": "route_scheduling",
        "service_area": "route_scheduling",
        "requires_handoff": False,
        "handoff_area": None,
        "captured_fields": fields,
        "confidence": 1.0,
        "message_mode": "flow_progress",
        "pending_intents": [],
        "resume_prompt": "",
    }


def format_test_items(rows: list[dict]) -> str:
    if not rows:
        return "ninguno"
    # Precio siempre en formato completo "$12.000" (pedido del usuario 2026-07-22: nada de
    # abreviar "$12k" en lo que ve el cliente). El formato lo decide `money()`.
    return ", ".join(f"{r['code']}-{r['name']} {_money(r.get('price'))}" for r in rows)


def estimated_total_text(totals: dict) -> str:
    """Texto del valor estimado. Si hay descuento por volumen, SIEMPRE se desglosa
    (subtotal → descuento → total): sin el desglose, el total parece un error de
    cálculo ('$14k + $8k = $19,360?' — reporte del usuario, 2026-07-06)."""
    if totals.get("discount"):
        return (f"Subtotal {_money(totals['subtotal'])}, descuento por volumen "
                f"-{_money(totals['discount'])} → valor estimado {_money(totals['total'])}.")
    return f"Valor estimado: {_money(totals['total'])}."


def route_ready_for_payment(session: dict, fields: dict) -> bool:
    has_client = bool(session.get("client_id") or fields.get("_client_found"))
    has_route_data = all(fields.get(k) for k in ROUTE_ORDER_FIELDS_BEFORE_PAYMENT)
    # ERR-091: una dirección de relleno no habilita el paso al pago (ver is_placeholder_address).
    if is_placeholder_address(fields.get("pickup_address")):
        has_route_data = False
    return has_client and has_route_data and not fields.get("_address_confirmation_pending")


def missing_route_field(session: dict, fields: dict) -> str | None:
    if not (session.get("client_id") or fields.get("_client_found")):
        return "client"
    if fields.get("_address_confirmation_pending"):
        return "pickup_address"
    for field in order_required_fields():
        if field == "exam_type":
            # El análisis puede estar como perfil elegido, selección estructurada de tests o
            # texto libre: cualquiera cuenta (tras un reemplazo suelto exam_type queda vacío
            # pero selected_tests tiene el análisis — no re-preguntar el análisis; QA extremo).
            if not (fields.get("exam_type") or _as_text_items(fields.get("selected_tests"))
                    or fields.get("_selected_profile_code")):
                return field
            continue
        if not fields.get(field):
            return field
        if field == "pickup_address" and is_placeholder_address(fields.get(field)):
            return field
        if field == "patient_age" and not age_has_unit(fields.get(field)):
            return field
    return None


def order_data_complete(session: dict, fields: dict) -> bool:
    """¿La orden ya tiene todos sus datos? Es el momento en que se ofrece agregar otro análisis.

    El MISMO momento del flujo se lee distinto según el flag: sin pedidos, el único campo que
    falta es la forma de pago; con pedidos `payment_method` dejó de ser campo de la orden
    (decisión 011), así que se lee como "no falta nada". Vive acá para que no vuelva a quedar
    escrito como `missing == "payment_method"` en cada sitio: escrito así, encender el flag
    hacía desaparecer la oferta de análisis extra de todas las vías de captura a la vez."""
    missing = missing_route_field(session, fields)
    return not missing if PEDIDOS_ENABLED else missing == "payment_method"


def extra_analysis_offer() -> str:
    """Texto de la oferta de agregar otro análisis, con la salida correcta según el flujo:
    sin pedidos lo siguiente es el pago; con pedidos es el cierre de ESTA orden."""
    return EXTRA_ANALYSIS_OFFER_PEDIDO if PEDIDOS_ENABLED else EXTRA_ANALYSIS_OFFER


# ERR-091: textos de presentación que NUNCA son una dirección real. Un campo obligatorio
# validado solo por "no vacío" no está validado: "sin dirección registrada" es un string
# no vacío y pasaba el guardrail, así que la orden se cerraba con dirección basura y el
# motorizado no sabía a dónde ir.
_PLACEHOLDER_ADDRESS_MARKERS = (
    "sin direccion", "sin dirección", "no registrada", "no tiene direccion",
    "no tiene dirección", "sin datos", "no aplica", "por definir", "pendiente",
)


def is_placeholder_address(value) -> bool:
    """¿El valor de la dirección es un texto de relleno en vez de una dirección real?"""
    text = " ".join(str(value or "").lower().split())
    if not text:
        return True
    return any(marker in text for marker in _PLACEHOLDER_ADDRESS_MARKERS)


def missing_route_field_question(field: str) -> str:
    if field == "client":
        return "¿Me compartes el NIT o el nombre de la veterinaria o médico veterinario para ver si está registrado?"
    if field == "pickup_address":
        return "¿Cuál es la dirección de retiro?"
    if field == "requesting_doctor":
        return "¿Cuál es el médico solicitante?"
    if field == "exam_type":
        return "¿Qué análisis o perfil desean?"
    if field == "patient_name":
        return "¿Cuál es el nombre del paciente?"
    if field == "species":
        return "¿Es canino, felino u otra especie?"
    if field == "breed":
        return "¿Cuál es la raza del paciente?"
    if field == "sex":
        return "¿El paciente es macho o hembra?"
    if field == "patient_age":
        return AGE_QUESTION
    if field == "owner_name":
        return "¿Cuál es el nombre del propietario?"
    if field == "observations":
        return "Por último, ¿quieres dejar alguna observación para la orden o la registramos sin observaciones?"
    return PAYMENT_METHOD_QUESTION
