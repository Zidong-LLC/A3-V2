"""
ERR-061 (prueba real del usuario, 2026-07-16): 'quiero hacer potasio sodio y orina' → el
MODELO estructuró selected_tests él solo y eligió 'Parcial de Orina' (1601) entre las 5
opciones de orina del catálogo, sin mostrar menú ni precios. El resolvedor de texto nunca
corre en esa vía (selected_tests ya viene estructurado) y el I1 solo valida que el código
exista — violación de I3 ('nunca agregar un test que el cliente no eligió explícitamente')
por la puerta lateral.

Fix: `_enforce_selected_tests_grounding` — cada código NUEVO capturado por el modelo debe
estar anclado a un análisis que el cliente nombró; lo anclado se registra MOSTRANDO precios
y la adivinanza se vuelve MENÚ de su área. Tests de lógica pura sobre el estado real, sin
fingir la respuesta del modelo (L51).
"""
from unittest.mock import patch

from app import agent, catalog

POTASIO = {"code": "1404", "name": "Potasio", "price": 12000, "category": "Química"}
SODIO = {"code": "1405", "name": "Sodio", "price": 12000, "category": "Química"}
PARCIAL_ORINA = {"code": "1601", "name": "Parcial de Orina (14 parámetros)", "price": 16000,
                 "category": "Uroanálisis"}
CORTISOL_ORINA = {"code": "1507", "name": "Cortisol en Orina", "price": 33000,
                  "category": "Uroanálisis"}

SESSION = {"client_id": "c1"}
PREV = {"_client_found": True, "clinic_name": "Clinica Veterinaria Colombia",
        "species": "Porcino", "patient_name": "Simón"}


def _ai(fields):
    return {"intent": "route_scheduling", "reply": "Listo, lo anoto.",
            "requires_handoff": False, "captured_fields": fields}


def test_names_test_distinguishes_named_from_area_word():
    """'potasio sodio y orina' NOMBRA Potasio y Sodio, pero NO nombra 'Parcial de Orina'
    ('orina' es palabra de área: no elige un test concreto)."""
    msg = "quiero hacer potasio sodio y orina"
    assert catalog.names_test(msg, POTASIO)
    assert catalog.names_test(msg, SODIO)
    assert not catalog.names_test(msg, PARCIAL_ORINA)
    assert not catalog.names_test(msg, CORTISOL_ORINA)
    assert catalog.names_test("agregale el 1601", PARCIAL_ORINA)   # el código sí ancla


def test_model_guess_becomes_area_menu_and_grounded_stay():
    """El caso real: el modelo capturó [Potasio, Sodio, Parcial de Orina]. El anclado se
    registra con precio; la adivinanza de orina se quita y se ofrece el menú del área."""
    fields = dict(PREV)
    fields["selected_tests"] = ["1404", "1405", "1601"]
    with patch.object(agent.db, "get_tests_by_codes",
                      return_value=[POTASIO, SODIO, PARCIAL_ORINA]), \
         patch.object(agent.db, "find_tests_by_area",
                      return_value=("Uroanálisis", [CORTISOL_ORINA, PARCIAL_ORINA])):
        out = agent._enforce_selected_tests_grounding(
            SESSION, _ai(fields), PREV, "quiero hacer potasio sodio y orina", [])
    f = out["captured_fields"]
    assert agent._as_text_items(f.get("selected_tests")) == ["1404", "1405"]   # 1601 fuera
    assert f.get("_test_menu_options")                                          # menú del área
    assert f.get("_test_menu_adds_to_profile") is True                          # elegir AGREGA
    assert "Potasio $12k" in out["reply"] and "Sodio $12k" in out["reply"]      # con precios
    assert "1601" in out["reply"] and "1507" in out["reply"]                    # opciones visibles


def test_grounded_codes_pass_untouched():
    """Todos los códigos nombrados por el cliente → el guardrail no interviene."""
    fields = dict(PREV)
    fields["selected_tests"] = ["1404", "1405"]
    ai = _ai(fields)
    with patch.object(agent.db, "get_tests_by_codes", return_value=[POTASIO, SODIO]):
        out = agent._enforce_selected_tests_grounding(
            SESSION, ai, PREV, "quiero potasio y sodio", [])
    assert out is ai
    assert agent._as_text_items(fields.get("selected_tests")) == ["1404", "1405"]


def test_affirmation_grounds_against_bot_offer():
    """'sí, agrégalo' tras una oferta del bot que NOMBRA el análisis: anclado por historial."""
    fields = dict(PREV)
    fields["selected_tests"] = ["1601"]
    history = [
        {"role": "user", "content": "y de orina qué tienen"},
        {"role": "bot", "content": "El examen suelto es Parcial de Orina (14 parámetros) $16.000. ¿Lo agrego?"},
    ]
    ai = _ai(fields)
    with patch.object(agent.db, "get_tests_by_codes", return_value=[PARCIAL_ORINA]):
        out = agent._enforce_selected_tests_grounding(SESSION, ai, PREV, "sí, agrégalo", history)
    assert out is ai
    assert agent._as_text_items(fields.get("selected_tests")) == ["1601"]


def test_menu_selection_turns_are_skipped():
    """Con un menú mostrado el turno anterior, 'el 1' no nombra el test: esa vía ya se valida
    por la selección de menú — el grounding no debe intervenir."""
    prev = dict(PREV)
    prev["_test_menu_options"] = [{"code": "1601", "name": "Parcial de Orina", "price": 16000}]
    fields = dict(prev)
    fields["selected_tests"] = ["1601"]
    ai = _ai(fields)
    out = agent._enforce_selected_tests_grounding(SESSION, ai, prev, "el 1", [])
    assert out is ai
    assert agent._as_text_items(fields.get("selected_tests")) == ["1601"]
