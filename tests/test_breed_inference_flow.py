"""La raza reconocida llena la especie sin romper el flujo de la orden.

El riesgo real de este feature no es el catálogo sino el pipeline: al llenar `species` sola,
cambia cuál es el "primer campo faltante" y por ahí pasan los guardrails que deciden la
siguiente pregunta. Estos tests fijan que el flujo avanza a `sex` cuando la raza aporta la
especie, y que sigue preguntando la especie cuando no la aporta.
"""
import pytest

from app import agent, breeds, flow
from tests.test_breeds_catalog import CATALOG_ROWS


@pytest.fixture(autouse=True)
def catalog(monkeypatch):
    monkeypatch.setattr(breeds, "_fetch_rows", lambda: list(CATALOG_ROWS))
    breeds._load.cache_clear()
    yield
    breeds._load.cache_clear()


SESSION = {"client_id": "cli-1"}  # cliente ya identificado: el flujo está en la orden


def _response(**fields) -> dict:
    base = {"patient_name": "Rocky", "species": None, "breed": None, "sex": None}
    base.update(fields)
    return {
        "intent": "route_scheduling",
        "requires_handoff": False,
        "reply": "¿Cuál es el sexo del paciente?",
        "captured_fields": base,
    }


def _order(**fields) -> dict:
    """Orden con todo resuelto salvo lo que el caso quiera dejar pendiente."""
    base = {
        "pickup_address": "Cra 15 #80-20", "requesting_doctor": "Dra Ana", "patient_name": "Rocky",
        "species": None, "breed": None, "sex": None, "patient_age": "4 años",
        "owner_name": "Luis", "observations": "ninguna", "exam_type": "Cuadro Hemático",
    }
    base.update(fields)
    return base


def test_known_breed_fills_species_and_leaves_reply_untouched():
    response = _response(breed="pastor aleman")
    result = agent._recover_breed_and_species(response, {})
    assert result["captured_fields"]["breed"] == "Pastor Alemán"
    assert result["captured_fields"]["species"] == "Canino"
    assert result["reply"] == "¿Cuál es el sexo del paciente?"


def test_inferred_species_makes_the_flow_skip_to_sex():
    """R1: el objetivo del feature. Con la especie inferida, el siguiente faltante es el sexo."""
    fields = _order(breed="holstein")
    assert flow.missing_route_field(SESSION, fields) == "species"
    agent._recover_breed_and_species(_response(**fields) | {"captured_fields": fields}, {})
    assert fields["species"] == "Bovino"
    assert flow.missing_route_field(SESSION, fields) == "sex"


def test_ambiguous_breed_still_asks_the_species():
    """Protección contra sobre-inferencia: 'mestizo' no adivina Canino."""
    fields = _order(breed="mestizo")
    agent._recover_breed_and_species(_response(**fields) | {"captured_fields": fields}, {})
    assert fields["breed"] == "Mestizo"
    assert fields["species"] is None
    assert flow.missing_route_field(SESSION, fields) == "species"


def test_unknown_breed_does_not_block_the_flow():
    """'Tobiano' (ERR-069) no está en el catálogo: el valor del modelo queda y se avanza."""
    fields = _order(breed="Tobiano", species="Equino")
    agent._recover_breed_and_species(_response(**fields) | {"captured_fields": fields}, {})
    assert fields["breed"] == "Tobiano"
    assert flow.missing_route_field(SESSION, fields) == "sex"


@pytest.mark.parametrize("breed", ["no sé", "mestizo de la calle", "criollo raro"])
def test_non_breed_answers_are_never_emptied(breed):
    fields = _order(breed=breed, species="Canino")
    agent._recover_breed_and_species(_response(**fields) | {"captured_fields": fields}, {})
    assert fields["breed"] == breed


def test_never_overwrites_a_species_the_client_gave():
    """'es una gata criolla': la palabra explícita del cliente gana sobre el catálogo."""
    response = _response(species="Felino", breed="criollo")
    result = agent._recover_breed_and_species(response, {})
    assert result["captured_fields"]["species"] == "Felino"


def test_never_contradicts_a_species_captured_in_a_previous_turn():
    response = _response(species=None, breed="holstein")
    result = agent._recover_breed_and_species(response, {"species": "Equino"})
    assert result["captured_fields"]["species"] is None


def test_breed_of_another_species_does_not_rewrite_the_declared_one():
    """Incoherencia rara (species=Felino + breed=Holstein): se normaliza la raza, no la especie."""
    response = _response(species="Felino", breed="holstein")
    result = agent._recover_breed_and_species(response, {})
    assert result["captured_fields"]["species"] == "Felino"
    assert result["captured_fields"]["breed"] == "Holstein"


@pytest.mark.parametrize("override", [
    {"requires_handoff": True},
    {"intent": "billing"},
    {"intent": "results_query"},
])
def test_only_runs_on_route_scheduling(override):
    response = _response(breed="pastor aleman") | override
    result = agent._recover_breed_and_species(response, {})
    assert result["captured_fields"]["breed"] == "pastor aleman"
    assert result["captured_fields"]["species"] is None


def test_is_idempotent():
    """El resolutor de 'el mismo/el de siempre' copia la raza de la orden previa: re-normalizarla
    no debe cambiarla una segunda vez."""
    response = _response(breed="pastor aleman")
    once = agent._recover_breed_and_species(response, {})
    twice = agent._recover_breed_and_species(once, {})
    assert twice["captured_fields"]["breed"] == "Pastor Alemán"
    assert twice["captured_fields"]["species"] == "Canino"
