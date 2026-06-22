"""Regresión: confirmación de dirección de retiro con variantes coloquiales.

Bug (caso Animal Pets, chat 4): el cliente confirmó la dirección registrada con "sisi";
el LLM avanzó al médico, pero `_confirms_address("sisi")` devolvía False, así que la bandera
`_address_confirmation_pending` quedaba pegada en True y el bot volvía a pedir la dirección
turnos después. Ver ERR en tasks/errores-soluciones.md.
"""
import pytest

from app import agent


@pytest.mark.parametrize("text", ["sisi", "sisisi", "siii", "si", "sí", "sí sí", "dale", "ok", "1"])
def test_confirma_direccion_variantes(text):
    assert agent._confirms_address(text) is True


@pytest.mark.parametrize("text", ["no", "no esa no", "dr araujo", "2", "cambiar"])
def test_no_confirma_direccion(text):
    assert agent._confirms_address(text) is False


# --- "esa misma" confirma la dirección y no la deja pegada (RESUELTO-010, 2º camino) ---

def _prev_with_pending_address():
    return {
        "pickup_address": "DG 51A SUR 61B-03",
        "_client_address": "DG 51A SUR 61B-03",
        "_address_confirmation_pending": True,
        "_address_confirmed": False,
        "_client_found": True,
        "clinic_name": "Animal Pets",
        "_client_memory": {"pickup_address": "DG 51A SUR 61B-03", "requesting_doctor": "Dr. Lopez"},
    }


def test_esa_misma_resuelve_la_direccion():
    """'si esa misma' al preguntar la dirección la resuelve por el camino same_as_previous."""
    history = [{"role": "bot", "content": "Tenemos como domicilio de retiro: DG 51A SUR 61B-03. ¿Es correcta?"}]
    res = agent._resolve_same_as_previous(_prev_with_pending_address(), "si esa misma", history)
    assert res is not None and res["field"] == "pickup_address"


def test_direccion_presente_sin_flag_no_se_pide():
    """Con la bandera bajada y la dirección presente, no se reporta como faltante."""
    session = {"client_id": "x"}
    fields = _prev_with_pending_address()
    fields["_address_confirmation_pending"] = False  # estado tras el fix
    assert agent._missing_route_field(session, fields) == "requesting_doctor"
    fields["requesting_doctor"] = "Dr. Araujo"
    assert agent._missing_route_field(session, fields) != "pickup_address"
