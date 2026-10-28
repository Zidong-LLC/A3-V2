"""Enforcer de la consulta de RESULTADOS (Paso 3.4a).

El agente busca en los resultados publicados de la plataforma los del cliente que está
escribiendo y le manda el PDF por el mismo chat (decisión del usuario, 2026-08-28). Si no
sabe quién es, pide el nombre de la clínica o el NIT: sin cliente no se busca nada.

Si la búsqueda falla se cae al mensaje fijo de antes, para que un problema de base nunca
deje al cliente sin respuesta. Si el turno además dejó pendiente una recogida, se retoma
la ruta en el mismo turno."""
import logging
from app.flow import (
    base_route_response as _base_route_response,
    missing_route_field as _missing_route_field,
    missing_route_field_question as _missing_route_field_question,
)
from app.laterales import (
    _has_active_route_context,
    _operational_side_question_answer,
    _results_pending_response,
    _resume_route_after_lateral_turn,
)
from app.messages import RESULTS_NEED_CLIENT_MESSAGE, RESULTS_PENDING_MESSAGE
from app.results_lookup import build_response, order_number_in
from app.services import db
from app.verificacion_cliente import dato_faltante, trae_el_dato

logger = logging.getLogger(__name__)

# Clave interna: los ids de resultado que main.py tiene que mandar como PDF después
# de responder el texto. El envío no vive acá porque el enforcer no conoce el canal.
DELIVER_KEY = "_deliver_results"

# Verificación antes de entregar (ERR-187): `client_id` del cliente que demostró nombre +
# NIT en este chat, el dato que se le pidió y cuántas veces respondió mal.
VERIFICADO_KEY = "_resultados_verificado"
PIDE_KEY = "_resultados_pide"
INTENTOS_KEY = "_resultados_intentos"
MAX_INTENTOS = 3
_DATO = {"nit": "el NIT", "nombre": "el nombre de la veterinaria"}


def _verificar(session: dict, fields: dict, user_message: str) -> str | None:
    """None si este chat ya demostró nombre Y NIT del cliente; si no, qué contestarle.

    Regla del usuario (2026-10-28): los PDF solo salen si el nombre de la clínica y el NIT
    concuerdan; si dio uno solo, se le pide el otro y tiene que ser el correcto. Antes
    alcanzaba con decir el nombre de una clínica para recibir sus resultados. Se mira lo
    que ESCRIBIÓ el usuario: el NIT que la base completa sola al identificar por nombre
    no cuenta."""
    client_id = session.get("client_id")
    if fields.get(VERIFICADO_KEY) == client_id:
        return None
    cliente = db.get_client_by_id(client_id) or {}
    chat_id = session.get("external_chat_id") or ""
    textos = [m.get("content") or "" for m in db.get_recent_messages(chat_id, limit=30)
              if m.get("role") == "user"] + [user_message]
    falta = dato_faltante(textos, cliente)
    if not falta:
        fields[VERIFICADO_KEY] = client_id
        fields.pop(PIDE_KEY, None)
        fields.pop(INTENTOS_KEY, None)
        return None
    if fields.get(PIDE_KEY):  # ya se lo pedimos y lo que respondió no concuerda
        intentos = int(fields.get(INTENTOS_KEY) or 0) + 1
        fields[INTENTOS_KEY] = intentos
        if intentos >= MAX_INTENTOS:
            fields.pop(PIDE_KEY, None)
            return ("Esos datos no coinciden con el registro de la veterinaria, así que por "
                    "seguridad no puedo enviarte resultados por este medio. Si es un error, el "
                    "equipo de A3 te ayuda con gusto.")
        return (f"Ese dato no coincide con el registro de la veterinaria. ¿Me confirmas "
                f"{_DATO[fields[PIDE_KEY]]}?")
    fields[PIDE_KEY] = falta
    return (f"Con gusto te paso el resultado 🙌. Por seguridad, antes necesito confirmar los "
            f"datos de la veterinaria: ¿me confirmas {_DATO[falta]}?")


def _results_answer(session: dict, fields: dict, user_message: str) -> tuple[str, list[str]]:
    """Texto de la respuesta y resultados a enviar. Nunca levanta: ante cualquier
    fallo devuelve el mensaje fijo de siempre."""
    client_id = session.get("client_id")
    if not client_id:
        return RESULTS_NEED_CLIENT_MESSAGE, []
    try:
        pregunta = _verificar(session, fields, user_message)
        if pregunta:
            return pregunta, []
        return build_response(
            client_id,
            patient=fields.get("patient_name"),
            order_number=order_number_in(user_message),
        )
    except Exception:
        logger.exception("Consulta de resultados por chat falló para %s", client_id)
        return RESULTS_PENDING_MESSAGE, []


def _enforce_results_message(session: dict, ai_response: dict, user_message: str) -> dict:
    """Si el turno se clasificó como consulta de resultados, busca el resultado del
    cliente y responde con él. Si junto con los resultados quedó pendiente programar
    una recogida, entrega la respuesta Y retoma la ruta en el mismo turno, para no
    perder la intención de recogida (resume determinístico)."""
    fields = ai_response.get("captured_fields") or {}
    if ai_response.get("intent") != "results":
        # Si le pedimos el NIT o el nombre, la respuesta ('900123456') el modelo la suele
        # leer como un identificador y no como resultados: el dato pendiente manda.
        if not fields.get(PIDE_KEY):
            return ai_response
        if not trae_el_dato(user_message, db.get_client_by_id(session.get("client_id")) or {}, fields[PIDE_KEY]):
            fields.pop(PIDE_KEY, None)  # no contestó lo pedido: cambió de tema, se suelta
            return ai_response
    pending = ai_response.get("pending_intents") or []

    operational_answer = _operational_side_question_answer(user_message)
    if operational_answer:
        response = _base_route_response(operational_answer, fields)
        response["message_mode"] = "side_question"
        return _resume_route_after_lateral_turn(session, response) if _has_active_route_context(session, fields) else response

    answer, deliver = _results_answer(session, fields, user_message)

    if "route_scheduling" in pending:
        missing = _missing_route_field(session, fields)
        question = _missing_route_field_question(missing) if missing else "¿Confirmas que programamos la recogida?"
        resumed = _base_route_response(
            f"{answer}\n\nMientras tanto, sigamos con la recogida que me pedías. {question}",
            fields,
        )
        resumed["message_mode"] = "side_question"
        resumed["captured_fields"]["_pending_intents"] = []
        if deliver:
            resumed["captured_fields"][DELIVER_KEY] = deliver
        return resumed

    response = _results_pending_response(fields, pending)
    response["reply"] = answer
    if deliver:
        response["captured_fields"][DELIVER_KEY] = deliver
    return response
