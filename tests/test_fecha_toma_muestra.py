"""Fecha de toma de muestra — pedido de A3 en la llamada del 21/08.

*"Ese campo no se lo pregunta al cliente, del resto sí. (…) El que define eso es el cliente."*

Va entre el propietario y el análisis: es el orden de la orden física que A3 imprime, y deja
intacto el par análisis → observaciones aprobado en esa misma llamada. No bloquea: si el
cliente no la sabe, la orden sigue igual (decisión del usuario, 2026-08-25).

Antes de esto, el PDF imprimía `scheduled_pickup_date` —cuándo pasa el motorizado— bajo la
etiqueta "Fecha toma de muestras": un dato equivocado bajo una etiqueta correcta.
"""
from app import flow, orders, state
from app.detectors.orden import _detect_correction_field
from app.schema import RESPONSE_SCHEMA

SESSION = {"client_id": "cli-1"}

ORDEN_SIN_FECHA = {
    "_client_found": True, "clinic_name": "Animal Pets",
    "pickup_address": "DG 51A SUR 61B-03", "_address_confirmed": True,
    "requesting_doctor": "Dr. Cristian Vargas", "patient_name": "Lola",
    "species": "Canino", "breed": "Border Collie", "sex": "Hembra",
    "patient_age": "6 años", "owner_name": "Marcela Osorio",
}


def test_la_fecha_se_pide_despues_del_propietario_y_antes_del_analisis():
    orden = flow.ROUTE_ORDER_FIELDS_BEFORE_PAYMENT
    assert orden.index("owner_name") < orden.index("sample_taken_date")
    assert orden.index("sample_taken_date") < orden.index("exam_type")
    # El par análisis → observaciones que A3 aprobó no se toca.
    assert orden.index("exam_type") < orden.index("observations")


def test_con_el_propietario_cargado_el_siguiente_faltante_es_la_fecha():
    assert flow.missing_route_field(SESSION, dict(ORDEN_SIN_FECHA)) == "sample_taken_date"
    assert flow.missing_route_field_question("sample_taken_date") == "¿Qué día tomaron la muestra?"


def test_con_la_fecha_dada_el_flujo_sigue_al_analisis():
    fields = dict(ORDEN_SIN_FECHA, sample_taken_date="ayer")
    assert flow.missing_route_field(SESSION, fields) == "exam_type"


def test_no_informada_no_traba_la_orden():
    """El cliente que no la sabe no queda atascado: 'no informada' cuenta como respondida."""
    fields = dict(ORDEN_SIN_FECHA, sample_taken_date="no informada")
    assert flow.missing_route_field(SESSION, fields) == "exam_type"


def test_el_campo_esta_declarado_en_el_schema_y_en_el_estado():
    props = RESPONSE_SCHEMA["schema"]["properties"]["captured_fields"]
    assert "sample_taken_date" in props["properties"]
    # El schema es estricto: lo que está en properties debe estar en required.
    assert "sample_taken_date" in props["required"]
    # Y el estado debe conocerlo, o no sobrevive al turno siguiente.
    assert "sample_taken_date" in state.BUSINESS_FIELDS


def test_corregir_la_fecha_apunta_a_su_campo_y_no_al_analisis():
    for frase in ("cambia la fecha de toma, fue ayer",
                  "corrige: la muestra la tomaron el lunes"):
        assert _detect_correction_field(frase) == "sample_taken_date", frase


def test_la_fecha_aparece_en_el_resumen_que_ve_el_cliente():
    fields = dict(ORDEN_SIN_FECHA, sample_taken_date="20/08",
                  exam_type="Cuadro Hemático", observations="sin observaciones")
    resumen = "\n".join(orders._order_summary_lines(fields, "Animal Pets"))
    assert "Fecha de toma de muestra: 20/08" in resumen


def test_el_cliente_que_no_la_sabe_queda_asi_en_el_resumen():
    """No se inventa una fecha: se muestra que no la informó."""
    fields = dict(ORDEN_SIN_FECHA, sample_taken_date="no informada",
                  exam_type="Cuadro Hemático", observations="sin observaciones")
    resumen = "\n".join(orders._order_summary_lines(fields, "Animal Pets"))
    assert "Fecha de toma de muestra: no informada" in resumen


def test_sin_el_campo_no_hay_resumen_todavia():
    """El resumen exige la orden completa, así que el flujo pregunta la fecha antes de
    llegar a él — nunca se muestra un resumen con el dato en blanco."""
    fields = dict(ORDEN_SIN_FECHA, exam_type="Cuadro Hemático",
                  observations="sin observaciones")
    assert orders._order_summary_lines(fields, "Animal Pets") is None


def test_la_fecha_no_se_arrastra_al_paciente_siguiente():
    """Cada orden es un paciente distinto: su muestra pudo tomarse otro día."""
    from app.agent import _ORDER_RESET_FIELDS
    assert "sample_taken_date" in _ORDER_RESET_FIELDS
