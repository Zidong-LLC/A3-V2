"""
ERR-060b (prueba real del usuario, 2026-07-16): con la especie/sexo ya resueltos por
implicación ("es un toro" -> Bovino/Macho) y la RAZA pendiente, el cliente respondió
"macho" (no es una raza). El reply del modelo repitió la pregunta de raza pero, al
re-confirmar el sexo ya capturado, mencionaba la palabra "macho" -> el reescritor de
preguntas repetidas la confundía con una pregunta de SEXO (adivinando el campo por
palabras sueltas del TEXTO) y sustituía la pregunta por "¿es macho o hembra?", tapando
la raza real pendiente. Bucle infinito: 3 turnos idénticos re-preguntando el sexo ya
resuelto, sin volver a preguntar la raza.

Fix de raíz: usar el campo REALMENTE pendiente (`_missing_route_field`, fuente de verdad
determinística) en vez de adivinar por palabras del reply. Lógica pura, sin fingir el
modelo (L51): se construye el estado exacto del bug y se llama la función directo.
"""
from app import agent

SESSION = {"client_id": "c1"}

# Estado real tras "es un toro": sexo YA capturado, raza pendiente.
FIELDS_MID_ROUTE = {
    "_client_found": True,
    "clinic_name": "Clinica Veterinaria Colombia",
    "pickup_address": "DG 40 SUR 34A-09",
    "requesting_doctor": "Dr. Araujo",
    "patient_name": "Gretta",
    "species": "Bovino",
    "sex": "Macho",
    "breed": None,
}

HISTORY = [
    {"role": "user", "content": "es un toro"},
    {"role": "bot", "content": "Perfecto, registro Bovino como especie y Macho como sexo. ¿Cuál es la raza del paciente?"},
]


def test_reply_mentioning_sex_word_does_not_hijack_pending_breed_question():
    """El reply del modelo re-confirma 'Macho' (sexo ya sabido) mientras repite la
    pregunta de raza -> el reescritor NO debe sustituirla por la pregunta de sexo."""
    ai_response = {
        "reply": "Ya tengo registrado Macho como sexo. ¿Cuál es la raza del paciente?",
        "phase": "fase_2_recogida_datos",
        "requires_handoff": False,
        "captured_fields": dict(FIELDS_MID_ROUTE),
    }
    out = agent._avoid_repeated_question(SESSION, ai_response, HISTORY, FIELDS_MID_ROUTE)
    assert out["reply"] == agent._missing_route_field_question("breed")
    assert "macho o hembra" not in out["reply"].lower()


def test_genuinely_repeated_breed_question_gets_the_breed_rephrase():
    """Caso base: repetir la MISMA pregunta de raza también se resuelve al campo real (raza),
    no al canned genérico de _rephrased_repeated_question."""
    ai_response = {
        "reply": "¿Cuál es la raza del paciente?",
        "phase": "fase_2_recogida_datos",
        "requires_handoff": False,
        "captured_fields": dict(FIELDS_MID_ROUTE),
    }
    out = agent._avoid_repeated_question(SESSION, ai_response, HISTORY, FIELDS_MID_ROUTE)
    assert out["reply"] == agent._missing_route_field_question("breed")


def test_no_repetition_leaves_reply_untouched():
    ai_response = {
        "reply": "¿Qué edad tiene el paciente?",
        "phase": "fase_2_recogida_datos",
        "requires_handoff": False,
        "captured_fields": dict(FIELDS_MID_ROUTE, breed="Cebú"),
    }
    out = agent._avoid_repeated_question(SESSION, ai_response, HISTORY, FIELDS_MID_ROUTE)
    assert out["reply"] == "¿Qué edad tiene el paciente?"
