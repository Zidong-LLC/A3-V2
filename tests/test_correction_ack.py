"""ERR-069 (chat real 2026-07-17): el cliente corrigió la raza ('me confundí con la raza
es un tobiano') — el dato SE GUARDÓ bien, pero el bot nunca acusó el cambio y los empujes
determinísticos respondían con la pregunta de su carril. El cliente insistió 3 veces hasta
el bucle '¿qué análisis quieres agregarle?'.
Diseño (pedido del usuario): ante una corrección, (1) el carril de análisis CEDE el turno
al modelo para que capture; (2) el acuse se arma determinístico — 'Listo, corrijo raza:
Tobiano.' — y se retoma el paso pendiente (pregunta del faltante o re-oferta de análisis).
Tests de lógica pura con los mensajes reales del chat, sin fingir el modelo (L51)."""
from unittest.mock import patch

from app.enforcers import orden as eorden, flujo as eflujo
from app.flow import extra_analysis_offer
from tests.helpers_pedidos import assert_advances_after_decline

BASE = {"_client_found": True, "species": "Equino", "breed": "Árabe", "sex": "Macho",
        "patient_age": "4 años", "patient_name": "Lolo", "owner_name": "Pedro",
        "_selected_profile_code": "152", "_selected_profile_name": "Perfil Prequirúrgico I",
        "_selected_profile_price": 24000, "exam_type": "Perfil Prequirúrgico I",
        "_offering_extra_analysis": True}
SESSION = {"client_id": "c1"}


def test_extra_offer_lane_yields_on_stable_field_correction():
    """Los mensajes reales del bucle: el carril devuelve None (cede al modelo) en vez de
    responder '¿qué análisis quieres agregarle?'."""
    for msg in ("quiero cambiar la raza es un tobiano",
                "La raza es tobiano\nEso quiero modificar"):
        out = eorden._handle_extra_analysis_answer(SESSION, dict(BASE), msg)
        assert out is None, f"el carril devoró la corrección: {msg!r}"


def test_extra_offer_lane_still_handles_analysis_and_payment():
    """No-regresión del carril: agregar análisis y seguir al pago no ceden."""
    POTASIO = [{"code": "1404", "name": "Potasio", "price": 12000, "category": "Minerales"}]
    with patch.object(eorden.db, "list_catalog_tests", return_value=POTASIO), \
         patch.object(eorden.db, "find_tests_by_area", return_value=(None, [])), \
         patch.object(eorden.db, "get_tests_by_codes_or_names", return_value=[]):
        out = eorden._handle_extra_analysis_answer(SESSION, dict(BASE), "agregar potasio")
        assert out and "Potasio" in out["reply"]
        out2 = eorden._handle_extra_analysis_answer(SESSION, dict(BASE), "no ya está, seguimos")
        assert_advances_after_decline(out2, "no ya está, seguimos")


def test_correction_ack_in_normal_intake():
    """Recogida normal: la raza cambia de valor → el acuse la nombra con el valor nuevo y
    empuja el siguiente faltante (antes: 'Perfecto, lo anoto.' genérico, invisible)."""
    prev = {"_client_found": True, "species": "Equino", "breed": "Árabe", "sex": "Macho",
            "patient_age": "4 años", "patient_name": "Lolo", "pickup_address": "DG 51",
            "requesting_doctor": "Dr Felipe"}
    fields = dict(prev, breed="Tobiano", owner_name="Pedro")
    ai = {"intent": "route_scheduling", "captured_fields": fields,
          "phase": "fase_2_recogida_datos", "reply": "(reply del modelo)"}
    out = eflujo._enforce_first_missing_after_progress(SESSION, ai, prev)
    assert "corrijo raza: Tobiano" in out["reply"]
    # Empuja el siguiente faltante. Desde 2026-08-12 el análisis va antes que las
    # observaciones (pedido de A3, reunión del 28/07), así que el pendiente es el análisis.
    assert "análisis o perfil" in out["reply"].lower()


def test_correction_ack_in_extra_offer_lane_resumes_offer():
    """El caso del bucle: corrección con la oferta activa → acuse + re-oferta estándar."""
    prev = dict(BASE)
    fields = dict(BASE, breed="Tobiano")
    ai = {"intent": "route_scheduling", "captured_fields": fields,
          "phase": "fase_2_recogida_datos", "reply": "(reply del modelo)"}
    out = eflujo._enforce_first_missing_after_progress(SESSION, ai, prev)
    assert "corrijo raza: Tobiano" in out["reply"]
    assert extra_analysis_offer() in out["reply"]


def test_normal_progress_keeps_generic_ack():
    """No-regresión: un campo NUEVO (progreso, no corrección) mantiene 'Perfecto, lo anoto.'."""
    prev = {"_client_found": True, "species": "Equino", "breed": "Árabe", "sex": "Macho",
            "patient_name": "Lolo", "pickup_address": "DG 51", "requesting_doctor": "Dr Felipe"}
    fields = dict(prev, patient_age="4 años")
    ai = {"intent": "route_scheduling", "captured_fields": fields,
          "phase": "fase_2_recogida_datos", "reply": "(reply del modelo)"}
    out = eflujo._enforce_first_missing_after_progress(SESSION, ai, prev)
    assert out["reply"].startswith("Perfecto, lo anoto.")
    assert "corrijo" not in out["reply"]
