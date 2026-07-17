import json
from openai import OpenAI
from app.config import OPENAI_API_KEY, OPENAI_MODEL
from app.prompt import SYSTEM_PROMPT
from app.schema import RESPONSE_SCHEMA

_client = OpenAI(api_key=OPENAI_API_KEY)

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
    response = _client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=messages,
        response_format={"type": "json_object"},
        temperature=0.3,
    )
    return json.loads(response.choices[0].message.content)



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
    response = _client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=messages,
        response_format={"type": "json_object"},
        temperature=0,
    )
    return json.loads(response.choices[0].message.content)


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
        addr = private.get("_client_address") or "sin dirección registrada"
        state_parts.append(f"CLIENTE ENCONTRADO: {name} — Dirección registrada: {addr}")
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

    response = _client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=messages,
        response_format={"type": "json_schema", "json_schema": RESPONSE_SCHEMA},
        temperature=0.3,
    )

    return json.loads(response.choices[0].message.content)
