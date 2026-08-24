"""Ítem 2 de la tanda pre-lanzamiento (2026-08-24, guiones M/M2): la orden YA
registrada se corrige en dos pasos — resumen corregido + confirmación → UPDATE con
evento de auditoría. Mecánica con señal fingida (L51)."""
from tests.test_etapa2_senal_confirmacion import ORDEN_COMPLETA, _run_turn

from app import agent


POST_CIERRE = dict(
    ORDEN_COMPLETA,
    _order_registered=True,
    _last_request_id="req-1",
    _last_order_number="A3-2026-001",
    _pedido_id="ped-1",
    _prev_order_snapshot={"patient_name": "Firulais", "requesting_doctor": "Dra Ana",
                          "pickup_address": "DG 51A SUR 60"},
)


def test_correccion_con_valor_muestra_resumen_y_pide_confirmar():
    """Guion M: 'espera, corrige el paciente: ahora se llama Rocky' tras el cierre →
    resumen corregido + '¿Confirmas estos datos?' (antes: '¿Qué análisis o perfil
    desean?' y el dato se perdía)."""
    reply, persisted = _run_turn("espera, corrige el paciente: ahora se llama Rocky",
                                 "correction", POST_CIERRE, phase="fase_6_cierre")
    assert "Rocky" in reply and "¿Confirmas" in reply
    fields = persisted.get("captured_fields", {})
    pcc = fields.get("_post_close_correction") or {}
    assert pcc.get("field") == "patient_name" and pcc.get("value") == "Rocky"


def test_confirmacion_aplica_el_update_en_bd():
    """El 'sí, confirmo' con el cambio propuesto llama a db.update_request_order_fields
    y confirma la actualización."""
    captured = dict(POST_CIERRE, _post_close_correction={
        "field": "patient_name", "value": "Rocky", "request_id": "req-1"})
    reply, persisted, fake_db = _run_turn("sí, confirmo", "affirm", captured,
                                          return_db=True)
    fake_db.update_request_order_fields.assert_called_once_with(
        "req-1", {"patient_name": "Rocky"})
    assert "actualizada" in reply.lower()


def test_correccion_sin_valor_pregunta_y_luego_confirma():
    """Guion M2: 'corrige el nombre del paciente' → pregunta el dato; 'Rocky' →
    resumen corregido + confirmación."""
    reply1, persisted1 = _run_turn("corrige el nombre del paciente", "correction",
                                   POST_CIERRE, phase="fase_6_cierre")
    assert "paciente" in reply1.lower() and "?" in reply1
    f1 = persisted1.get("captured_fields", {})
    assert f1.get("_post_close_correction_field") == "patient_name"

    captured2 = dict(POST_CIERRE, _post_close_correction_field="patient_name")
    reply2, persisted2 = _run_turn("Rocky", "unclear", captured2)
    assert "Rocky" in reply2 and "¿Confirmas" in reply2


def test_negativa_descarta_el_cambio_sin_tocar_bd():
    """'no, mejor déjalo así' con el cambio propuesto NO escribe en BD."""
    captured = dict(POST_CIERRE, _post_close_correction={
        "field": "patient_name", "value": "Rocky", "request_id": "req-1"})
    reply, persisted, fake_db = _run_turn("no, mejor déjalo así", "negate", captured,
                                          return_db=True)
    fake_db.update_request_order_fields.assert_not_called()
    assert "como estaba" in reply.lower()


def test_valor_reemitido_del_historial_no_se_propone():
    """M2 con modelo real: tras el reset de B12 el modelo re-emite "Firulais" leyendo el
    historial — NO es una captura nueva; el bot debe PREGUNTAR el dato, no proponer el
    valor viejo."""
    # B12 reconstruye el snapshot desde el estado: el valor "viejo" de la orden acá
    # es el patient_name del estado ("Pepe"), que el modelo re-emite del historial.
    reply, persisted = _run_turn("corrige el nombre del paciente", "correction",
                                 POST_CIERRE, phase="fase_6_cierre",
                                 ai_fields={"patient_name": "Pepe"})
    assert "¿Confirmas" not in reply, f"propuso el valor viejo: {reply[:80]}"
    f = persisted.get("captured_fields", {})
    assert f.get("_post_close_correction_field") == "patient_name"


def test_valor_nuevo_sobre_propuesta_la_reemplaza():
    """"Rocky" respondiendo a una propuesta equivocada re-propone con el valor nuevo."""
    captured = dict(POST_CIERRE, _post_close_correction={
        "field": "patient_name", "value": "Firulais", "request_id": "req-1"})
    reply, persisted = _run_turn("Rocky", "unclear", captured)
    assert "Rocky" in reply and "¿Confirmas" in reply
    pcc = persisted.get("captured_fields", {}).get("_post_close_correction") or {}
    assert pcc.get("value") == "Rocky"
