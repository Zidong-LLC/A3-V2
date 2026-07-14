"""
Fase 0 — Red de seguridad: INVARIANTES DE DINERO end-to-end sobre process_turn.

A diferencia de test_qa_realista_guardrails.py (que prueba cada enforcer aislado),
esto corre un turno COMPLETO y aplica invariantes reutilizables sobre el resultado,
dejando correr la resolución REAL de catálogo dentro del turno (el catálogo se
inyecta en db._client; solo se mockean sesión, cliente y orden). Cada escenario
nuevo hereda automáticamente los cuatro chequeos:

  I1  todo selected_tests es un código que existe en el catálogo (nunca texto suelto).
  I2  el exam_type resuelto no contiene un precio inventado por el modelo.
  I4  el total mostrado = cálculo desde los códigos (calculate_custom_profile_total).

Es la red contra la que se refactoriza la Fase 1: si un cambio deja pasar un precio
del texto o un código inválido, estos tests se ponen en rojo.
"""
import re
from types import SimpleNamespace
from unittest.mock import patch

from app import agent
from app.services import db

from tests.test_catalog_resolution import CATALOG, _FakeClient


CATALOG_BY_CODE = {r["code"]: r for r in CATALOG}


# ── Invariantes reutilizables ───────────────────────────────────────────────────

def assert_selected_tests_valid(fields):
    """I1 — cada selected_test es un código real del catálogo."""
    for code in agent._as_text_items(fields.get("selected_tests")):
        assert code in CATALOG_BY_CODE, f"I1 violada: '{code}' no es código de catálogo"


def assert_no_invented_price_in_exam(fields):
    """I2 — el exam_type no arrastra un precio escrito por el modelo."""
    exam = fields.get("exam_type") or ""
    assert not re.search(r"\$\s*\d", exam), f"I2 violada: precio en exam_type: {exam!r}"
    assert not re.search(r"\d\s*k\b", exam.lower()), f"I2 violada: precio 'k' en exam_type: {exam!r}"


def assert_total_matches_catalog(reply, fields):
    """I4 — si el reply muestra un valor estimado, coincide con el cálculo por códigos."""
    if not reply or "Valor estimado" not in reply:
        return
    codes = agent._as_text_items(fields.get("selected_tests"))
    if not codes:
        return
    rows = [CATALOG_BY_CODE[c] for c in codes if c in CATALOG_BY_CODE]
    expected = agent.calculate_custom_profile_total(rows)["total"]
    shown = {int(n.replace(",", "")) for n in re.findall(r"\$([\d,]+)", reply)}
    assert expected in shown, f"I4 violada: total {expected} no está en el reply (mostró {shown})"


def assert_money_invariants(reply, fields):
    assert_selected_tests_valid(fields)
    assert_no_invented_price_in_exam(fields)
    assert_total_matches_catalog(reply, fields)


# ── Harness: un turno completo con resolución de catálogo REAL ───────────────────

def _full_ai_response(reply, captured):
    return {"reply": reply, "intent": "route_scheduling", "phase": "fase_2_recogida_datos",
            "service_area": "route_scheduling", "captured_fields": captured,
            "message_mode": "flow_progress", "user_intent_signal": "provides_requested_data",
            "requires_handoff": False, "handoff_area": None, "resume_prompt": "",
            "confidence": 1.0, "pending_intents": []}


def run_turn(user_message, ai_captured, prev_fields, reply="Perfecto, lo anoto.", history=None):
    """Corre process_turn con toda la BD mockeada salvo la resolución de catálogo,
    que corre real contra CATALOG inyectado en db._client. Devuelve (reply, fields)."""
    REG = "CL 27 SUR 12-22"
    session = {"chat_id": "t", "channel": "telegram", "client_id": "client-A",
               "phase_current": "fase_2_recogida_datos", "intent_current": "route_scheduling",
               "captured_fields": dict(prev_fields)}
    hist = list(history or [
        {"role": "user", "content": "1"},
        {"role": "bot", "content": f"Encontramos Animal Club. Domicilio: {REG}. ¿Es correcta?"},
    ])
    # Funciones de db de alto nivel: mockeadas. Las de catálogo (get_tests_*,
    # find_tests_by_area) se dejan REALES y usan db._client inyectado.
    high_level = {
        "get_or_create_session": dict(side_effect=lambda c, channel="telegram": session),
        "get_recent_messages": dict(side_effect=lambda c, limit=8: hist[-limit:]),
        "save_message": dict(side_effect=lambda c, t, r: hist.append({"role": r, "content": t})),
        "update_session": dict(side_effect=lambda c, ai: session.update(
            phase_current=ai["phase"], intent_current=ai["intent"], captured_fields=ai["captured_fields"])),
        "get_client_by_id": dict(return_value={"id": "client-A", "clinic_name": "Animal Club",
                                               "tax_id": "35529523-1", "phone": "300", "address": REG}),
        "get_courier_for_client": dict(return_value=None),
        "get_catalog_context": dict(return_value=""),
        "get_individual_tests_context": dict(return_value=""),
        "get_last_order_for_client": dict(return_value=None),
        "list_diagnostic_labels": dict(return_value=[]),
        "find_diagnostic_label": dict(return_value=None),
        "get_tests_for_label": dict(return_value=[]),
        "find_catalog_profiles": dict(return_value=[]),
        "find_catalog_profile": dict(return_value=None),
        "get_catalog_profiles_by_codes": dict(return_value=[]),
        "list_catalog_profiles_for_species": dict(return_value=[]),
        "list_catalog_profiles_matching_category": dict(return_value=[]),
        "create_request": dict(return_value={"request_id": "r1", "order_number": "A3-2026-901"}),
    }
    patchers = [patch(f"app.services.db.{n}", **kw) for n, kw in high_level.items()]
    patchers.append(patch.object(db, "_client", _FakeClient({"catalog_tests": CATALOG})))
    patchers.append(patch.object(agent.ai, "generate_turn",
                                 return_value=_full_ai_response(reply, dict(ai_captured))))
    for p in patchers:
        p.start()
    try:
        out = agent.process_turn("t", user_message)
    finally:
        for p in patchers:
            p.stop()
    return out, session["captured_fields"]


# ── Escenarios adversariales ─────────────────────────────────────────────────────

def _client_ready_fields():
    REG = "CL 27 SUR 12-22"
    return {"_client_found": True, "clinic_name": "Animal Club", "tax_id": "35529523-1",
            "pickup_address": REG, "_client_address": REG, "_address_confirmed": True,
            "requesting_doctor": "Dra. Sofia", "patient_name": "Luna", "species": "Felino",
            "breed": "Siames", "sex": "Hembra", "patient_age": "2 años", "owner_name": "Carolina",
            "observations": "sin observaciones"}


def test_invented_price_is_dropped_and_test_structured():
    """QA-1: el modelo escribe 'Coprológico $23k'; la orden debe quedar con el código
    1701 y SIN el precio inventado. El precio real ($12.000) sale del catálogo."""
    ai_captured = {**_client_ready_fields(), "exam_type": "Coprológico $23k",
                   "payment_method": "contraentrega"}
    reply, fields = run_turn(
        "necesito un coprologico para luna y contraentrega", ai_captured,
        _client_ready_fields(),
    )
    assert agent._as_text_items(fields.get("selected_tests")) == ["1701"]
    assert_money_invariants(reply, fields)


def test_invalid_code_from_model_is_dropped_before_registering():
    """I1 (red dura): si un código inventado se cuela en selected_tests, se descarta antes
    de registrar — nunca se crea una orden con un análisis fantasma / payload en $0."""
    ai_captured = {**_client_ready_fields(),
                   "exam_type": "1101 Cuadro Hemático Completo",
                   "selected_tests": ["1101", "9999"], "removed_tests": [],
                   "payment_method": "contraentrega"}
    reply, fields = run_turn(
        "quiero cuadro hematico, contraentrega", ai_captured, _client_ready_fields(),
    )
    assert agent._as_text_items(fields.get("selected_tests")) == ["1101"]
    assert_money_invariants(reply, fields)


def test_total_from_catalog_on_two_tests():
    """I4 end-to-end: dos análisis → el total mostrado = cálculo por códigos."""
    ai_captured = {**_client_ready_fields(),
                   "exam_type": "Cuadro Hemático Completo, Creatinina",
                   "payment_method": "contraentrega"}
    reply, fields = run_turn(
        "quiero cuadro hematico y creatinina para luna, contraentrega", ai_captured,
        _client_ready_fields(),
    )
    assert set(agent._as_text_items(fields.get("selected_tests"))) == {"1101", "1309"}
    assert_money_invariants(reply, fields)
