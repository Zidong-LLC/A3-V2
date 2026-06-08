import json
from openai import OpenAI
from app.config import OPENAI_API_KEY, OPENAI_MODEL
from app.prompt import SYSTEM_PROMPT
from app.schema import RESPONSE_SCHEMA

_client = OpenAI(api_key=OPENAI_API_KEY)

_NC_INTERPRET_SYSTEM = (
    "Estás registrando datos de un cliente potencial para A3 Laboratorio Veterinario (Bogotá, Colombia). "
    "Tu única tarea: determinar si la respuesta del usuario contiene el dato solicitado.\n\n"
    "Reglas:\n"
    "• Si el usuario responde con el dato pedido → action=save, value=dato limpio, reply=null.\n"
    "• Si saluda, pregunta algo, dice algo fuera de contexto, o da un dato claramente incorrecto "
    "→ action=clarify, value=null, reply=respuesta corta y amable en español colombiano que "
    "aclare/responda y luego vuelva a pedir el dato.\n"
    "• Sé natural, no robótico. Máximo 2 oraciones en reply.\n"
    "Responde SOLO con JSON válido: "
    "{\"action\":\"save\"|\"clarify\", \"value\":\"...\"|null, \"reply\":\"...\"|null}"
)


def interpret_nc_step(question: str, user_message: str) -> dict:
    """Interpreta si user_message responde la pregunta de captura de nuevo cliente.
    Returns: {"action": "save"|"clarify", "value": str|None, "reply": str|None}
    """
    messages = [
        {"role": "system", "content": _NC_INTERPRET_SYSTEM},
        {"role": "user", "content": f"Pregunté: \"{question}\"\nEl usuario respondió: \"{user_message}\""},
    ]
    response = _client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=messages,
        response_format={"type": "json_object"},
        temperature=0.2,
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
