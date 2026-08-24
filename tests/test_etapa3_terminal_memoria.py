"""Etapa 3 del refactor de comprensión (2026-08-21): fase TERMINAL y memoria.

Los carriles pre-LLM del post-cierre (despedida/saludo/lateral/cierre/negativa) y los de
"el de siempre" se degradaron a handlers post-modelo señal-primero. Mecánica con señal
fingida (L51); la emisión real la valida validate_flows.py y la prueba en vivo.
"""
from tests.test_etapa2_senal_confirmacion import ORDEN_COMPLETA, _run_turn

from app import agent


TERMINAL = dict(
    ORDEN_COMPLETA,
    _order_registered=True,
    _prev_order_snapshot={"requesting_doctor": "Dra Ana", "pickup_address": "DG 51A SUR 60"},
)


# ── Fase terminal ────────────────────────────────────────────────────────────


def test_despedida_terminal_por_senal_con_fraseo_desconocido():
    """'dale mil gracias por la gestion' no está en la lista de despedidas: la señal
    farewell del modelo despide igual."""
    msg = "dale mil gracias por la gestion"
    assert not agent._is_farewell(msg), "el fraseo NO debe estar en la red"
    reply, _ = _run_turn(msg, "farewell", TERMINAL, phase="fase_6_cierre")
    assert reply == agent.FAREWELL_REPLY


def test_cierre_terminal_affirm_pelado_queda_atentos():
    """Nota: "dale" pelado es DESPEDIDA desde siempre (el carril de farewell corre
    primero); el cierre "quedamos atentos" responde a una confirmación explícita."""
    reply, _ = _run_turn("confirmo", "affirm", TERMINAL, phase="fase_6_cierre")
    assert "quedamos atentos" in reply.lower()


def test_negativa_terminal_por_senal_despide():
    """'ya con eso estamos completos' + negate → despedida (antes: solo la lista)."""
    reply, _ = _run_turn("ya con eso estamos completos", "negate", TERMINAL,
                         phase="fase_6_cierre")
    assert reply == agent.FAREWELL_REPLY


def test_otra_orden_en_terminal_la_toma_c1():
    """'otra orden para otro paciente' en fase terminal arranca el followup (C1 con la
    red ampliada) — el carril pre-LLM removido no deja hueco."""
    reply, persisted = _run_turn("necesito otra orden para otro paciente", "unclear",
                                 TERMINAL, phase="fase_6_cierre")
    fields = persisted.get("captured_fields", {})
    assert fields.get("_prev_order_snapshot"), "no arrancó la orden de seguimiento"
    assert not fields.get("patient_name")


# ── "El de siempre" (same_as_previous revivida) ──────────────────────────────


def test_el_de_siempre_por_senal_sin_tope_de_longitud():
    """Frase de 10 palabras: la red la descartaba por el tope de 6 tokens; la señal
    same_as_previous resuelve del snapshot igual (la ganancia de revivirla)."""
    captured = dict(
        ORDEN_COMPLETA,
        _prev_order_snapshot={"requesting_doctor": "Dra Ana"},
    )
    captured.pop("requesting_doctor")
    msg = "para el mismo doctor de siempre que ya conocen ustedes alla"
    reply, persisted = _run_turn(msg, "same_as_previous", captured)
    fields = persisted.get("captured_fields", {})
    assert fields.get("requesting_doctor") == "Dra Ana"


def test_el_de_siempre_red_de_tokens_sigue_viva():
    """Sin señal (unclear), 'el de siempre' corto resuelve por la red."""
    captured = dict(
        ORDEN_COMPLETA,
        _prev_order_snapshot={"requesting_doctor": "Dra Ana"},
    )
    captured.pop("requesting_doctor")
    historia = [{"role": "user", "content": "otra orden"},
                {"role": "bot", "content": "¿Cuál es el médico solicitante?"}]
    reply, persisted = _run_turn("el de siempre", "unclear", captured, history=historia)
    fields = persisted.get("captured_fields", {})
    assert fields.get("requesting_doctor") == "Dra Ana"
