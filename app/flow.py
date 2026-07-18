"""Capa de respuesta del flujo de recogida (Paso 3.4).

Helpers que construyen la respuesta determinística del flujo (siguiente campo faltante,
su pregunta, la respuesta base) y los cálculos de texto de dinero. Es la capa de la que
dependen los enforcers: al vivir acá, los enforcers pueden migrar a app/enforcers/ sin
imports circulares con agent.py. Los nombres públicos no llevan guion bajo; agent los
re-importa con alias para no tocar los ~200 call sites."""
from app.text import tokenize as _tokenize, money as _money, as_text_items as _as_text_items
from app.messages import AGE_QUESTION, PAYMENT_METHOD_QUESTION



AGE_UNIT_TOKENS = frozenset({"año", "años", "ano", "anos", "mes", "meses", "dia", "dias", "día", "días"})


def age_has_unit(value: str | None) -> bool:
    """La edad solo es válida si trae unidad (años/meses/días)."""
    return bool(set(_tokenize(value or "")) & AGE_UNIT_TOKENS)


ROUTE_ORDER_FIELDS_BEFORE_PAYMENT = (
    "pickup_address", "requesting_doctor",
    "patient_name", "species", "breed", "sex", "patient_age",
    "owner_name", "observations", "exam_type",
)


ROUTE_REQUIRED_FIELDS = ROUTE_ORDER_FIELDS_BEFORE_PAYMENT + ("payment_method",)


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
    return ", ".join(f"{r['code']}-{r['name']} ${int(r.get('price') or 0)//1000}k" for r in rows)


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
    return has_client and has_route_data and not fields.get("_address_confirmation_pending")


def missing_route_field(session: dict, fields: dict) -> str | None:
    if not (session.get("client_id") or fields.get("_client_found")):
        return "client"
    if fields.get("_address_confirmation_pending"):
        return "pickup_address"
    for field in ROUTE_REQUIRED_FIELDS:
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
        if field == "patient_age" and not age_has_unit(fields.get(field)):
            return field
    return None


def missing_route_field_question(field: str) -> str:
    if field == "client":
        return "¿Me compartes el NIT o el nombre de la veterinaria o médico veterinario para ver si está registrado?"
    if field == "pickup_address":
        return "¿Cuál es la dirección de retiro?"
    if field == "requesting_doctor":
        return "¿Cuál es el médico solicitante?"
    if field == "exam_type":
        return "Por último, ¿qué análisis o perfil desean?"
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
        return "¿Quieres dejar alguna observación para la orden o la registramos sin observaciones?"
    return PAYMENT_METHOD_QUESTION
