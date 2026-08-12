"""
ERR-094 — corregir un dato en la confirmación debe TOMAR el valor nuevo del mismo mensaje.

QA 2026-07-27: en el resumen final el cliente escribió "cambia el nombre del paciente a
Rocky" y el bot respondió "¿Cuál es el nombre del paciente?" con patient_name=None: borró
el valor viejo y no leyó el nuevo. `_extract_correction_value` solo entendía patient_name
y solo con "se llama / paciente es / ahora es".

ERR-091 — "sin dirección registrada" es un placeholder, no una dirección.
"""
import pytest

from app import agent, flow


# ── ERR-094 ──────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("field,text,expected", [
    ("patient_name", "cambia el nombre del paciente a Rocky", "Rocky"),
    ("patient_name", "el paciente se llama Rocky", "Rocky"),
    ("patient_name", "cambialo por Rocky", "Rocky"),
    ("patient_age", "perdón, la edad es 5 años", "5 años"),
    ("patient_age", "cambia la edad a 3 meses", "3 meses"),
    ("requesting_doctor", "cambia el médico a Dra. Laura Méndez", "Dra. Laura Méndez"),
    ("owner_name", "el propietario ahora es Pedro Gómez", "Pedro Gómez"),
    ("breed", "cambia la raza a un mestizo", "mestizo"),
    ("sex", "el sexo es macho", "macho"),
    ("pickup_address", "cambia la dirección a Calle 100 # 15-20", "Calle 100 # 15-20"),
])
def test_extracts_new_value_for_every_correctable_field(field, text, expected):
    assert agent._extract_correction_value(field, text) == expected


def test_age_without_unit_is_rejected_so_the_flow_asks():
    """'cambiala a 5' no es una edad válida: mejor que la vuelva a pedir."""
    assert agent._extract_correction_value("patient_age", "cambia la edad a 5") is None


@pytest.mark.parametrize("field", ["exam_type", "payment_method", "observations"])
def test_fields_with_their_own_lane_are_not_extracted_inline(field):
    """El análisis pasa por catálogo y el pago es un enum: no se leen de texto libre."""
    assert agent._extract_correction_value(field, "cambialo a otra cosa") is None


def test_returns_none_when_there_is_no_new_value():
    assert agent._extract_correction_value("patient_name", "quiero corregir el paciente") is None


# ── ERR-091 ──────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("value", [
    "sin dirección registrada", "Sin Direccion Registrada", "no registrada",
    "no tiene dirección", "no aplica", "pendiente", "", None,
])
def test_placeholder_addresses_are_not_real_addresses(value):
    assert flow.is_placeholder_address(value) is True


@pytest.mark.parametrize("value", ["CL 52A 85K-38", "Calle 100 # 15-20", "Carrera 7 45-30"])
def test_real_addresses_pass(value):
    assert flow.is_placeholder_address(value) is False


def _complete_fields(address):
    return {
        "_client_found": True, "pickup_address": address, "requesting_doctor": "Dr X",
        "patient_name": "Laila", "species": "Canino", "breed": "Mestiza", "sex": "Hembra",
        "patient_age": "3 años", "owner_name": "Pedro", "observations": "sin observaciones",
        "exam_type": "Cuadro Hemático", "payment_method": "contraentrega",
    }


def test_placeholder_address_blocks_the_closure():
    """El guardrail exigía solo 'no vacío': la orden se cerraba con dirección basura."""
    assert flow.missing_route_field({"client_id": "c1"},
                                    _complete_fields("sin dirección registrada")) == "pickup_address"


def test_real_address_does_not_block_the_closure():
    assert flow.missing_route_field({"client_id": "c1"},
                                    _complete_fields("CL 52A 85K-38")) is None


def test_placeholder_address_blocks_payment_step():
    assert flow.route_ready_for_payment({"client_id": "c1"},
                                        _complete_fields("sin dirección registrada")) is False
    assert flow.route_ready_for_payment({"client_id": "c1"},
                                        _complete_fields("CL 52A 85K-38")) is True
