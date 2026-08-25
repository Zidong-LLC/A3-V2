"""Regresión ERR-123 (Ronda 3 del estrés, nit_con_formatos): al resumen "¿Confirmas estos
datos?" el cliente respondió "Contraentrega." — confirmación implícita con el pago
adelantado, patrón humano frecuente. El carril de agregado se la tragaba ("¿Qué análisis
quieres agregar?"), y el "Ya está, gracias" siguiente tampoco tenía salida: BUCLE, la orden
no se registraba nunca (0 órdenes, 0 facturas en la corrida).

Fixes que este archivo protege:
1. El carril de ajuste CEDE ante un método de pago sin ningún análisis nombrado.
2. El cierre determinístico lee ese pago como confirmación (y lo captura para el pedido).
3. `farewell` con la espera de agregado encendida sale del carril (pregunta cerrada),
   nunca repregunta "¿Qué análisis…?" en bucle.
4. Las señales de veto (negate/correction/…) siguen frenando el cierre aunque haya un
   método de pago en el texto.
"""
from unittest.mock import patch

from app.enforcers import confirmacion
from app.messages import CONFIRMATION_AMBIGUOUS_QUESTION

BASE = {
    "_client_found": True, "clinic_name": "Animal Pets",
    "pickup_address": "DG 51A SUR 61B-03", "requesting_doctor": "Dr. Ruiz",
    "patient_name": "Bobi", "species": "Canino", "breed": "Criollo",
    "sex": "Macho", "patient_age": "3 años", "owner_name": "Pol",
    "sample_taken_date": "hoy",
    "observations": "sin observaciones",
    "exam_type": "Perfil Prequirúrgico I",
    "_selected_profile_code": "152",
    "_selected_profile_name": "Perfil Prequirúrgico I",
    "_selected_profile_price": 24000,
}

SESSION = {"client_id": "c1"}


def _ai(fields, signal=None):
    return {
        "intent": "route_scheduling",
        "captured_fields": fields,
        "reply": "",
        "user_intent_signal": signal,
        "message_mode": "flow_progress",
        "phase": "fase_4_confirmacion",
    }


def _step(fields, mensaje, signal=None):
    with patch.object(confirmacion.db, "get_tests_by_codes_or_names", return_value=[]), \
         patch.object(confirmacion, "_area_options_for_profile_addition", lambda *a, **k: None):
        return confirmacion._enforce_confirmation_step(
            SESSION, _ai(fields, signal), fields, "fase_4_confirmacion", mensaje)


def test_contraentrega_en_el_resumen_confirma_y_captura_el_pago():
    """El caso literal de la Ronda 3: 'Contraentrega.' responde al resumen → la orden
    CIERRA y el pago queda capturado para el pedido."""
    fields = dict(BASE)
    out = _step(fields, "Contraentrega.")
    assert out["phase"] == "fase_6_cierre", out["reply"]
    assert "agregar" not in out["reply"].lower()
    assert fields["payment_method"] == "contraentrega"


def test_farewell_con_la_espera_encendida_sale_del_carril():
    """'Ya está, gracias.' con `_awaiting_additional_test` pegado: pregunta CERRADA
    (¿confirmamos o cambiás algo?), jamás el bucle '¿Qué análisis quieres agregar?'."""
    fields = dict(BASE, _awaiting_additional_test="add")
    out = _step(fields, "Ya está, gracias.", signal="farewell")
    assert out["reply"] == CONFIRMATION_AMBIGUOUS_QUESTION
    assert "_awaiting_additional_test" not in fields


def test_negacion_con_pago_no_cierra_a_ciegas():
    """'no, mejor pago en línea' trae un método de pago PERO la señal es negate: el veto
    manda y la orden NO se cierra en este turno."""
    fields = dict(BASE)
    out = _step(fields, "no, mejor pago en línea", signal="negate")
    assert out["phase"] != "fase_6_cierre"


def test_pago_mas_pedido_de_analisis_no_cede():
    """'contraentrega, y agregale una glucosa' SÍ es del carril de ajuste: el pago no
    puede taparle el agregado (el catálogo decide qué se agrega)."""
    fields = dict(BASE)
    glucosa = [{"code": "0201", "name": "Glucosa", "price": 18000}]
    with patch.object(confirmacion.db, "get_tests_by_codes_or_names", return_value=glucosa), \
         patch.object(confirmacion, "_area_options_for_profile_addition", lambda *a, **k: None):
        out = confirmacion._enforce_confirmation_step(
            SESSION, _ai(fields), fields, "fase_4_confirmacion",
            "contraentrega, y agregale una glucosa")
    assert "0201" in (fields.get("selected_tests") or []) or "glucosa" in out["reply"].lower()


def test_confirmacion_explicita_cierra_aunque_la_senal_sea_farewell():
    """Ronda 5 (cancela_el_pedido): 'Sí, confirmo esos datos.' con señal farewell caía en
    'no me quedó claro' — el cliente terminó cancelando. La confirmación explícita SIEMPRE
    cierra, sin importar cómo etiquete el modelo."""
    fields = dict(BASE, payment_method="contraentrega")
    out = _step(fields, "Sí, confirmo esos datos.", signal="farewell")
    assert out["phase"] == "fase_6_cierre", out["reply"]
    assert CONFIRMATION_AMBIGUOUS_QUESTION not in out["reply"]
