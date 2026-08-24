"""Ronda 3 pre-lanzamiento (2026-08-24, repro del test en vivo): quitar un agregado no
resta del perfil; "saca X y cámbialo por Y" respeta el destino; la remoción no cede
por señal correction."""
from app.orders import _add_tests_to_order
from tests.test_etapa2_senal_confirmacion import _run_turn


def test_quitar_un_agregado_no_lo_resta_del_perfil():
    """DINERO: el 1903 agregado al Toxicológico (base $90.000) se quita de selected;
    meterlo en removed dejaba el total en $38.000."""
    fields = {"_selected_profile_code": "952", "selected_tests": ["1903"],
              "removed_tests": []}
    _add_tests_to_order(fields, [{"code": "1903", "name": "Citología PAF"}], "remove")
    assert fields["selected_tests"] == []
    assert not fields.get("removed_tests"), f"removed: {fields.get('removed_tests')}"


def test_saca_x_por_y_respeta_el_destino():
    """'Saca el análisis 653 y cámbialo por el 1903' con el 653 ausente y el 1903 ya en
    la orden: avisa que el 653 no está y el 1903 QUEDA (antes lo quitaba)."""
    captured = {
        "_client_found": True, "clinic_name": "EVI", "tax_id": "900",
        "pickup_address": "Cr 1", "_address_confirmed": True,
        "requesting_doctor": "Cristian", "patient_name": "Joy", "species": "Canino",
        "breed": "Husky", "sex": "Hembra", "patient_age": "11 años",
        "owner_name": "Camilo", "observations": "sin observaciones",
        "exam_type": "952 Perfil Toxicológico", "_selected_profile_code": "952",
        "_selected_profile_name": "Perfil Toxicológico", "_selected_profile_price": 90000,
        "selected_tests": ["1903"], "_offering_extra_analysis": True,
    }
    reply, persisted = _run_turn("Saca el análisis 653 y cámbialo por el 1903",
                                 "correction", captured)
    fields = persisted.get("captured_fields", {})
    assert "653 no está en esta orden" in reply
    assert "1903" in str(fields.get("selected_tests")), "el destino no debe quitarse"


def test_remocion_anaforica_no_cede_por_correction():
    """'No ese sácalo' con señal correction: la remoción es del carril de la oferta —
    con un solo ítem quitable, lo quita."""
    captured = {
        "_client_found": True, "clinic_name": "EVI", "tax_id": "900",
        "pickup_address": "Cr 1", "_address_confirmed": True,
        "requesting_doctor": "Cristian", "patient_name": "Joy", "species": "Canino",
        "breed": "Husky", "sex": "Hembra", "patient_age": "11 años",
        "owner_name": "Camilo", "observations": "sin observaciones",
        "exam_type": "Citología", "selected_tests": ["1903"],
        "_offering_extra_analysis": True,
    }
    reply, persisted = _run_turn("No ese sácalo", "correction", captured)
    fields = persisted.get("captured_fields", {})
    assert "1903" not in str(fields.get("selected_tests") or ""), f"no lo quitó: {reply[:80]}"
