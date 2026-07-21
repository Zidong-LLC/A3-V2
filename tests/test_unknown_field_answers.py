"""ERR-074 y ERR-075: un campo obligatorio que el modelo no llena dejaba la orden en bucle.

Los dos bugs son la misma falla: `missing_route_field` solo comprueba truthiness, así que si
el modelo deja el campo vacío a propósito, `_enforce_first_missing_after_progress` lo re-pide
en cada turno y la orden nunca cierra. Detectados por QA adversarial con el modelo real.
"""
import pytest

from app import agent, flow

SESSION = {"client_id": "cli-1"}


def _history(bot_question: str) -> list[dict]:
    return [{"role": "user", "content": "hola"}, {"role": "bot", "content": bot_question}]


def _response(**fields) -> dict:
    base = {"patient_name": "Rocky", "species": "Canino", "breed": None, "sex": None}
    base.update(fields)
    return {"intent": "route_scheduling", "requires_handoff": False,
            "reply": "¿Cuál es la raza del paciente?", "captured_fields": base}


def _order(**fields) -> dict:
    base = {"pickup_address": "Cra 15 #80-20", "requesting_doctor": "Dra Ana", "patient_name": "Rocky",
            "species": "Canino", "breed": None, "sex": "Macho", "patient_age": "4 años",
            "owner_name": "Luis", "observations": "ninguna", "exam_type": "Cuadro Hemático",
            "payment_method": "contraentrega"}
    base.update(fields)
    return base


# ── ERR-074: "no sé la raza" ──────────────────────────────────────────────────

@pytest.mark.parametrize("answer", [
    "no sé", "no se", "no lo sé", "ni idea", "no tengo idea", "desconozco",
    "no sabría decirte", "la verdad no sé la raza", "no sabemos",
    # Negar que TENGA raza es tan común como no saberla (QA real del usuario).
    "Ni tiene raza", "no tiene raza", "ninguna", "sin determinar",
])
def test_unknown_breed_unblocks_the_order(answer):
    response = _recover = agent._recover_unknown_breed(
        _response(), answer, _history("¿Cuál es la raza del paciente?"))
    assert response["captured_fields"]["breed"] == agent.BREED_UNKNOWN


def test_unknown_breed_lets_the_flow_reach_the_end():
    """El bug real: con la raza vacía, missing_route_field devolvía 'breed' para siempre."""
    fields = _order(breed=None)
    assert flow.missing_route_field(SESSION, fields) == "breed"
    response = agent._recover_unknown_breed(
        {"intent": "route_scheduling", "requires_handoff": False, "reply": "x", "captured_fields": fields},
        "no sé la raza", _history("¿Cuál es la raza del paciente?"))
    assert flow.missing_route_field(SESSION, response["captured_fields"]) is None


@pytest.mark.parametrize("answer", [
    "pastor alemán", "criollo", "mestizo", "Golden Retriever", "angora", "holstein", "boer",
])
def test_a_real_breed_is_never_replaced(answer):
    response = agent._recover_unknown_breed(
        _response(breed=answer), answer, _history("¿Cuál es la raza del paciente?"))
    assert response["captured_fields"]["breed"] == answer


def test_only_applies_when_the_bot_asked_for_the_breed():
    """'no sé' contestando otra pregunta no debe escribir la raza."""
    response = agent._recover_unknown_breed(
        _response(), "no sé", _history("¿Qué edad tiene el paciente?"))
    assert response["captured_fields"]["breed"] is None


# ── ERR-075: paciente llamado "Toro" ──────────────────────────────────────────

@pytest.mark.parametrize("name,expected", [
    ("Toro", "Toro"), ("gato", "Gato"), ("conejo", "Conejo"),
    ("Michi", None), ("Canela", None),  # no están en el dominio: los captura el modelo
])
def test_animal_word_as_patient_name_is_captured(name, expected):
    if expected is None:
        pytest.skip("no pertenece al dominio animal: nunca tuvo el bug")
    response = agent._recover_patient_name_answer(
        _response(patient_name=None, species=None), {}, name,
        _history("¿Cuál es el nombre del paciente?"))
    assert response["captured_fields"]["patient_name"] == expected


def test_animal_name_does_not_fill_the_species():
    """Responder 'Toro' al nombre no significa que la especie sea Bovino: se sigue preguntando."""
    response = agent._recover_patient_name_answer(
        _response(patient_name=None, species=None), {}, "Toro",
        _history("¿Cuál es el nombre del paciente?"))
    assert not response["captured_fields"]["species"]


def test_does_not_overwrite_a_name_the_model_captured():
    response = agent._recover_patient_name_answer(
        _response(patient_name="Firulais"), {}, "Toro",
        _history("¿Cuál es el nombre del paciente?"))
    assert response["captured_fields"]["patient_name"] == "Firulais"


def test_only_single_word_answers_are_treated_as_a_name():
    """'es un toro de 3 años' sigue siendo especie, no un paciente llamado Toro."""
    response = agent._recover_patient_name_answer(
        _response(patient_name=None, species=None), {}, "es un toro de 3 años",
        _history("¿Cuál es el nombre del paciente?"))
    assert not response["captured_fields"]["patient_name"]


def test_ordinary_names_are_left_to_the_model():
    """Solo actúa sobre palabras del dominio animal; 'Firulais' lo captura el modelo."""
    response = agent._recover_patient_name_answer(
        _response(patient_name=None), {}, "Firulais",
        _history("¿Cuál es el nombre del paciente?"))
    assert not response["captured_fields"]["patient_name"]


@pytest.mark.parametrize("override", [{"requires_handoff": True}, {"intent": "billing"}])
def test_both_guards_only_run_on_route_scheduling(override):
    base = _response(patient_name=None) | override
    assert agent._recover_patient_name_answer(base, {}, "Toro", _history("¿Cuál es el nombre del paciente?")) is base
    assert agent._recover_unknown_breed(base, "no sé", _history("¿Cuál es la raza del paciente?")) is base
