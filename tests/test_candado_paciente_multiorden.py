"""Orden siguiente: los datos del animal anterior no se cuelan al nuevo (ERR-187).

Estrés del 28/10 (persona confirmo_y_sigo): el modelo leía en el historial el resumen de la
orden anterior y le ponía al paciente nuevo raza, sexo, edad y dueño del viejo; y ante «ya
está, no tengo más órdenes» re-emitía la orden entera y se registraba dos veces.
"""
from app import agent

SNAP = {"patient_name": "C2", "species": "Felino", "breed": "Criolla", "sex": "Hembra",
        "patient_age": "3 años", "owner_name": "Dueño A", "exam_type": "1101 Cuadro Hemático Completo"}
PREV = {"_prev_order_snapshot": SNAP, "clinic_name": "Animal Pets"}


def _modelo(**campos):
    return {"clinic_name": "Animal Pets", **campos}


def test_paciente_nuevo_no_hereda_los_datos_del_animal_anterior():
    fields = _modelo(patient_name="C3", species="Canino", breed="Criolla", sex="Hembra",
                     patient_age="3 años", owner_name="Dueño A")
    agent._candado_provenancia_paciente(fields, dict(PREV), "C3, es un canino")
    assert fields["patient_name"] == "C3" and fields["species"] == "Canino"
    for copiado in ("breed", "sex", "patient_age", "owner_name"):
        assert copiado not in fields


def test_si_el_cliente_repite_el_dato_a_proposito_se_respeta():
    fields = _modelo(patient_name="C3", owner_name="Dueño A")
    agent._candado_provenancia_paciente(fields, dict(PREV), "C3, el dueño es Dueño A también")
    assert fields["owner_name"] == "Dueño A"


def test_el_mismo_animal_nombrado_por_el_cliente_conserva_sus_datos():
    fields = _modelo(patient_name="C2", breed="Criolla", sex="Hembra", owner_name="Dueño A")
    agent._candado_provenancia_paciente(fields, dict(PREV), "otra orden para C2 con el perfil 152")
    assert fields["breed"] == "Criolla" and fields["owner_name"] == "Dueño A"


def test_ya_esta_no_tengo_mas_no_resucita_la_orden_anterior():
    fields = _modelo(**SNAP)
    agent._candado_provenancia_paciente(fields, dict(PREV), "Ya está, no tengo más órdenes.")
    for copiado in ("patient_name", "breed", "sex", "patient_age", "owner_name", "exam_type"):
        assert copiado not in fields


def test_el_de_siempre_hereda_todo():
    fields = _modelo(**SNAP)
    agent._candado_provenancia_paciente(fields, dict(PREV), "lo mismo que la anterior, el de siempre")
    assert fields["patient_name"] == "C2" and fields["breed"] == "Criolla"


def test_sin_orden_anterior_no_toca_nada():
    fields = _modelo(patient_name="Luna", breed="Criolla")
    agent._candado_provenancia_paciente(fields, {}, "Luna")
    assert fields["breed"] == "Criolla"
