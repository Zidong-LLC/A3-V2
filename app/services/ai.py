import json
import time
from openai import OpenAI
from app.config import OPENAI_API_KEY, OPENAI_MODEL
from app.prompt import SYSTEM_PROMPT
from app.schema import RESPONSE_SCHEMA
from app.services import system_db

# Sin `timeout`, el SDK espera hasta 600 s por intento (x3 intentos): un cuelgue de OpenAI
# dejaba al cliente mirando el chat media hora. 60 s alcanza de sobra para un turno
# (auditoría de salida a producción, 2026-10-25).
_client = OpenAI(api_key=OPENAI_API_KEY, timeout=60.0, max_retries=2)

def _entero(valor) -> int:
    return valor if isinstance(valor, int) else 0


def _completar(messages: list[dict], response_format: dict, temperature: float, uso: str) -> dict:
    """Una llamada al modelo. Registra tokens y duración para el panel de sistema."""
    inicio = time.monotonic()
    response = _client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=messages,
        response_format=response_format,
        temperature=temperature,
    )
    usage = getattr(response, "usage", None)
    system_db.registrar("llm", "openai", "info", uso, details={
        "model": OPENAI_MODEL, "ms": int((time.monotonic() - inicio) * 1000),
        "prompt_tokens": _entero(getattr(usage, "prompt_tokens", 0)),
        "completion_tokens": _entero(getattr(usage, "completion_tokens", 0)),
    })
    return json.loads(response.choices[0].message.content)


_ROUTE_FIELD_INTERPRET_SYSTEM = (
    "Eres parte del equipo de A3 Laboratorio Veterinario (Bogotá, Colombia), tomando los datos "
    "de una orden de servicio a un cliente veterinario YA identificado. Acabas de pedirle un dato "
    "puntual de la orden y el usuario respondió. Tu única tarea: decidir si la respuesta realmente "
    "contiene el dato que pediste.\n\n"
    "Reglas:\n"
    "• Si la respuesta contiene el dato pedido → action=save, value=dato limpio, reply=null.\n"
    "• Si el usuario saluda, hace una pregunta social ('¿cómo estás?'), cambia de tema o responde "
    "algo que no es el dato pedido → action=clarify, value=null, reply=una frase corta, cálida y "
    "colombiana que reconozca con calidez lo que dijo (sin sonar a robot) y enseguida vuelva a pedir "
    "el dato con naturalidad.\n"
    "• reply: máximo 2 oraciones, cercano y humano, sin asteriscos.\n"
    "Responde SOLO con JSON válido: "
    "{\"action\":\"save\"|\"clarify\", \"value\":\"...\"|null, \"reply\":\"...\"|null}"
)


def interpret_route_field(question: str, user_message: str) -> dict:
    """¿La respuesta del usuario contesta el dato pedido en la orden de servicio?
    Red de seguridad para respuestas off-topic dentro de route_scheduling.
    Returns: {"action": "save"|"clarify", "value": str|None, "reply": str|None}
    """
    messages = [
        {"role": "system", "content": _ROUTE_FIELD_INTERPRET_SYSTEM},
        {"role": "user", "content": f"Pedí: \"{question}\"\nEl usuario respondió: \"{user_message}\""},
    ]
    return _completar(messages, {"type": "json_object"}, 0.3, "dato de la orden")



_CLIENT_ID_EXTRACT_SYSTEM = (
    "Eres un extractor. Del mensaje de un cliente de un laboratorio veterinario, extrae "
    "SOLO el nombre de la veterinaria/clinica o el NIT si los menciona, limpios de "
    "muletillas, saludos y contexto. Responde JSON: {\"name\": str|null, \"tax_id\": str|null}. "
    "Si no menciona ninguno, ambos null. No inventes."
)


def extract_client_identifier(user_message: str) -> dict:
    """Lee TODO el mensaje (frases, ruido, ráfagas) y extrae el identificador limpio.
    Red SEMÁNTICA de la identificación: se usa solo cuando la búsqueda determinística
    falló — el cliente dijo el nombre envuelto en cualquier fraseo (ERR-068 general)."""
    messages = [
        {"role": "system", "content": _CLIENT_ID_EXTRACT_SYSTEM},
        {"role": "user", "content": user_message},
    ]
    return _completar(messages, {"type": "json_object"}, 0, "identificar cliente")


def generate_turn(
    session: dict,
    history: list[dict],
    user_message: str,
    pending_intents: list[str] | None = None,
    catalog_context: str | None = None,
) -> dict:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    state_parts = []

    if session.get("phase_current"):
        state_parts.append(f"Fase actual: {session['phase_current']}")
    if session.get("intent_current") and session["intent_current"] != "unknown":
        state_parts.append(f"Intención activa: {session['intent_current']}")

    captured = {k: v for k, v in (session.get("captured_fields") or {}).items() if not k.startswith("_")}
    if captured:
        state_parts.append(f"Datos ya capturados: {json.dumps(captured, ensure_ascii=False)}")

    # Inyectar estado del cliente (resultado del lookup en Supabase)
    private = {k: v for k, v in (session.get("captured_fields") or {}).items() if k.startswith("_")}
    if private.get("_client_found"):
        name = private.get("_client_display_name", "")
        addr = private.get("_client_address")
        if addr:
            state_parts.append(f"CLIENTE ENCONTRADO: {name} — Dirección registrada: {addr}")
        else:
            # ERR-091: antes acá iba `addr or "sin dirección registrada"`, y el modelo leía ese
            # texto de relleno como si fuera EL VALOR del campo ("Dirección registrada: sin
            # dirección registrada"). Al decir el cliente "déjalo así", lo copiaba a
            # pickup_address y el guardrail lo aceptaba por ser un string no vacío: la orden
            # salía con dirección basura. Un placeholder de presentación nunca debe ocupar la
            # posición de un dato en el prompt.
            state_parts.append(
                f"CLIENTE ENCONTRADO: {name} — NO tiene dirección registrada en la base. "
                "Debes PEDIRLE la dirección de retiro al cliente; no la des por válida ni la "
                "registres vacía."
            )
    elif private.get("_client_not_found"):
        state_parts.append("CLIENTE NO ENCONTRADO en base de datos. Derivar a atención al cliente.")

    if pending_intents:
        state_parts.append(f"Intenciones pendientes: {json.dumps(pending_intents, ensure_ascii=False)}")

    if catalog_context:
        state_parts.append(catalog_context)

    if session.get("_client_memory_hint"):
        state_parts.append(session["_client_memory_hint"])

    if session.get("_custom_profile_summary"):
        state_parts.append(session["_custom_profile_summary"])

    if session.get("_force_close_hint"):
        state_parts.append(session["_force_close_hint"])

    if state_parts:
        messages.append({"role": "system", "content": "\n".join(state_parts)})

    for msg in history:
        role = "user" if msg["role"] == "user" else "assistant"
        messages.append({"role": role, "content": msg["content"]})

    messages.append({"role": "user", "content": user_message})

    return _completar(messages, {"type": "json_schema", "json_schema": RESPONSE_SCHEMA}, 0.3, "turno")
