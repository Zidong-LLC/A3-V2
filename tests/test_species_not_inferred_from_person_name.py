"""
ERR-084 — un apellido que además es palabra de animal no puede definir la especie.

La inferencia implícita de especie/sexo (`apply_implied_animal_fields`) corría en TODOS los
turnos, sin mirar qué había preguntado el bot. Dos casos reales del corpus:

- Conv 4 (orden A3-2026-169, cerrada): al pedir el médico, el cliente escribió "José toro" y
  el bot saltó las preguntas de especie y sexo. El resumen mostró
  "Pipo (Bovino, Sin Determinar, Macho, 5 años)" — nadie declaró nada de eso.
- Conv 10: el cliente declaró "Equino" y raza "Cuarto de Milla"; al pedir el propietario
  escribió "Jorge Toro" y el resumen salió "Fifi (Bovino, Cuarto de Milla, Macho)".

Impacto clínico: los rangos de referencia del laboratorio dependen de la especie, así que la
muestra se informa contra los valores normales de otro animal.
"""
from app import agent


def _history(bot_msg: str) -> list[dict]:
    return [{"role": "bot", "content": bot_msg}]


def _response(**fields) -> dict:
    return {"intent": "route_scheduling", "captured_fields": dict(fields)}


PREGUNTA_MEDICO = "Para dejar la orden completa, empecemos con el médico solicitante. ¿Cuál es el nombre?"
PREGUNTA_PROPIETARIO = "¿Cuál es el nombre del propietario?"
PREGUNTA_PACIENTE = "¿Cuál es el nombre del paciente?"
PREGUNTA_ESPECIE = "¿Es canino, felino u otra especie?"


def test_apellido_animal_como_medico_no_inventa_especie_ni_sexo():
    """El caso de la orden real A3-2026-169."""
    resp = agent._recover_implied_animal_fields(
        _response(requesting_doctor="José Toro"), {}, "José toro", _history(PREGUNTA_MEDICO))
    fields = resp["captured_fields"]
    assert not fields.get("species")
    assert not fields.get("sex")


def test_apellido_animal_como_propietario_no_pisa_la_especie_declarada():
    """Conv 10: un Cuarto de Milla equino no puede volverse bovino por el dueño."""
    prev = {"species": "Equino", "breed": "Cuarto de Milla"}
    resp = agent._recover_implied_animal_fields(
        _response(owner_name="Jorge Toro"), prev, "Jorge Toro", _history(PREGUNTA_PROPIETARIO))
    assert resp["captured_fields"].get("species") != "Bovino"


def test_apellido_animal_como_nombre_del_paciente_tampoco_infiere():
    """Familia ERR-075: 'Toro' como nombre de la mascota es un nombre, no una especie."""
    resp = agent._recover_implied_animal_fields(
        _response(patient_name="Toro"), {}, "Toro", _history(PREGUNTA_PACIENTE))
    assert not resp["captured_fields"].get("species")


def test_el_camino_legitimo_sigue_funcionando():
    """Si el bot pregunta la ESPECIE, la palabra de animal sí debe resolverla."""
    resp = agent._recover_implied_animal_fields(
        _response(), {}, "es un toro", _history(PREGUNTA_ESPECIE))
    fields = resp["captured_fields"]
    assert fields.get("species") == "Bovino"
    assert fields.get("sex") == "Macho"


def test_inferencia_fuera_de_una_pregunta_de_nombre_no_se_bloquea():
    """El guard es acotado: solo cede cuando lo preguntado era un nombre propio."""
    resp = agent._recover_implied_animal_fields(
        _response(), {}, "es una perra", _history("¿Qué edad tiene el paciente?"))
    assert resp["captured_fields"].get("species") == "Canino"
