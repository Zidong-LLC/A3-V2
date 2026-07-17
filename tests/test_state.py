"""Fase 3.1 — Estado explícito de la conversación (`app/state.py`).

Verifica que `ConversationState` formaliza el estado SIN cambiar el comportamiento: el
arrastre entre turnos replica el merge histórico, el catálogo de flags cubre lo que el
código usa, y las invariantes detectan estados incoherentes.
"""
from app import state
from app.state import ConversationState


def test_carry_over_replicates_historic_merge():
    """Arrastra toda flag _* del turno anterior salvo _pending_intents, sin pisar lo nuevo."""
    prev = {"_client_found": True, "_selected_profile_code": "153", "_pending_intents": ["x"],
            "clinic_name": "Vet Vieja", "patient_name": "Firu"}
    cur = {"clinic_name": "Vet Nueva"}          # este turno redefinió la clínica
    ConversationState(cur).carry_over(prev)
    assert cur["_client_found"] is True              # flag arrastrada
    assert cur["_selected_profile_code"] == "153"    # flag arrastrada
    assert "_pending_intents" not in cur             # NO se arrastra (se recomputa)
    assert cur["clinic_name"] == "Vet Nueva"         # no pisa lo del turno actual
    assert "patient_name" not in cur                 # negocio no se arrastra por este merge


def test_carry_over_matches_old_inline_logic():
    """Equivalencia exacta con el bucle inline que reemplazó (agent.py)."""
    prev = {"_a": 1, "_b": 2, "_pending_intents": 9, "x": "biz", "_c": 3}
    cur = {"_b": 20}
    old = dict(cur)
    for k, v in prev.items():
        if k.startswith("_") and k != "_pending_intents" and k not in old:
            old[k] = v
    new = dict(cur)
    ConversationState(new).carry_over(prev)
    assert new == old


def test_catalog_covers_flags_used_in_agent():
    """Toda flag _* que agent.py referencia en captured_fields está catalogada (o es _nc_)."""
    import re
    from pathlib import Path
    src = Path(__file__).resolve().parents[1] / "app" / "agent.py"
    used = set(re.findall(r'"(_[a-z_]+)"', src.read_text(encoding="utf-8")))
    uncatalogued = {f for f in used
                    if f not in state.KNOWN_FLAGS and not f.startswith("_nc_")}
    assert not uncatalogued, f"flags sin catalogar en state.py: {sorted(uncatalogued)}"


def test_assert_valid_flags_incoherent_states():
    import pytest
    ConversationState({"_address_confirmed": True}).assert_valid()          # ok
    with pytest.raises(AssertionError):
        ConversationState({"_address_confirmed": True,
                           "_address_confirmation_pending": True}).assert_valid()
    with pytest.raises(AssertionError):
        ConversationState({"_client_found": True, "_client_not_found": True}).assert_valid()


def test_unknown_flags_detection():
    st = ConversationState({"_client_found": True, "_typo_flag": 1, "_nc_capturing": True})
    assert st.unknown_flags() == {"_typo_flag"}     # _nc_ y catalogadas no cuentan


def test_phase_enum_matches_existing_constants():
    """El enum Phase refleja EXACTAMENTE las constantes de fase ya usadas (una sola verdad)."""
    from app import agent, rules
    assert state.Phase.CONFIRMACION == agent.CONFIRMATION_PHASE == "fase_4_confirmacion"
    assert {p.value for p in state.TERMINAL_PHASES} == set(rules.TERMINAL_PHASES)
    assert {p.value for p in state.DONE_PHASES} == set(rules.DONE_PHASES)
    assert {p.value for p in state.ESCALATED_PHASES} == set(rules.ESCALATED_PHASES)


def test_is_terminal():
    assert state.is_terminal("fase_6_cierre") and state.is_terminal("fase_7_escalado")
    assert not state.is_terminal("fase_2_recogida_datos")


def test_legal_transitions_of_the_flow():
    T = state.is_legal_transition
    # Transiciones reales del flujo (documentadas en LEGAL_TRANSITIONS).
    assert T("fase_0_bienvenida", "fase_2_recogida_datos")   # bienvenida → recogida
    assert T("fase_2_recogida_datos", "fase_4_confirmacion")  # datos completos → resumen
    assert T("fase_4_confirmacion", "fase_6_cierre")          # confirma → cierra
    assert T("fase_4_confirmacion", "fase_7_escalado")        # pago en línea → contabilidad
    assert T("fase_6_cierre", "fase_2_recogida_datos")        # otra orden
    assert T("fase_2_recogida_datos", "fase_2_recogida_datos")  # misma fase (permitida)
    # Salto claramente incoherente: no está en el grafo.
    assert not T("fase_0_bienvenida", "fase_4_confirmacion")   # bienvenida no salta a confirmar


def test_observer_logs_incoherent_state_without_breaking(caplog):
    """Fase 3.2 modo detección: el observador de `agent` loggea el estado pegado y NO rompe."""
    import logging
    from app import agent
    fields = {"_address_confirmed": True, "_address_confirmation_pending": True}
    with caplog.at_level(logging.WARNING, logger="app.agent"):
        agent._observe_state_health(fields)          # no lanza
    assert any("incoherente" in r.message for r in caplog.records)


def test_observer_logs_unknown_flags(caplog):
    import logging
    from app import agent
    with caplog.at_level(logging.WARNING, logger="app.agent"):
        agent._observe_state_health({"_client_found": True, "_flag_fantasma": 1})
    assert any("desconocidas" in r.message for r in caplog.records)


def test_observer_silent_on_healthy_state(caplog):
    """Un estado sano no genera ruido (no cambia el comportamiento del caso común)."""
    import logging
    from app import agent
    with caplog.at_level(logging.WARNING, logger="app.agent"):
        agent._observe_state_health({"_client_found": True, "selected_tests": ["1101"]})
    assert not caplog.records


def test_observer_logs_illegal_phase_transition(caplog):
    """El observador loggea un salto de fase fuera del grafo (bienvenida -> confirmación)."""
    import logging
    from app import agent
    token = agent._turn_prev_phase.set("fase_0_bienvenida")
    try:
        with caplog.at_level(logging.WARNING, logger="app.agent"):
            agent._observe_state_health({"_client_found": True}, "fase_4_confirmacion")
        assert any("transición" in r.message for r in caplog.records)
    finally:
        agent._turn_prev_phase.reset(token)


def test_observer_silent_on_legal_transition(caplog):
    import logging
    from app import agent
    token = agent._turn_prev_phase.set("fase_2_recogida_datos")
    try:
        with caplog.at_level(logging.WARNING, logger="app.agent"):
            agent._observe_state_health({"_client_found": True}, "fase_4_confirmacion")
        assert not caplog.records
    finally:
        agent._turn_prev_phase.reset(token)


def test_clear_menus_and_has_analysis():
    st = ConversationState({"_test_menu_options": [1], "_profile_menu_options": [2],
                            "_test_menu_adds_to_profile": True})
    st.clear_menus()
    assert not st.get("_test_menu_options") and not st.get("_profile_menu_options")
    assert not st.get("_test_menu_adds_to_profile")
    assert ConversationState({"selected_tests": ["1101"]}).has_analysis
    assert ConversationState({"_selected_profile_code": "153"}).has_analysis
    assert not ConversationState({}).has_analysis


def test_heal_resolves_known_incoherences():
    """3.2 modo bloqueo: heal() repara los pares incoherentes con las reglas documentadas."""
    st = ConversationState({"_address_confirmed": True, "_address_confirmation_pending": True,
                            "_client_found": True, "_client_not_found": True})
    healed = st.heal()
    assert set(healed) == {"_address_confirmation_pending", "_client_not_found"}
    st.assert_valid()                                   # tras reparar, el estado es coherente
    assert st.get("_address_confirmed") is True         # gana la confirmación
    assert ConversationState({"_client_found": True}).heal() == []   # sano: no toca nada
