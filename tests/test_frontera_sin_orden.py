"""Ítem 3 pre-lanzamiento (2026-08-24, guion G): la frontera multiorden no dispara
sin una orden en curso con contenido — "necesito un perfil renal para un paciente"
recién identificado es la PRIMERA orden, no una frontera."""
from tests.test_etapa2_senal_confirmacion import ORDEN_COMPLETA, _run_turn


SOLO_CLIENTE = {
    "_client_found": True, "clinic_name": "Animal Pets", "tax_id": "900123",
    "pickup_address": "DG 51A SUR 60", "_address_confirmed": True,
}


def test_pedir_perfil_sin_orden_previa_no_dispara_frontera():
    """Guion G: aunque el modelo emita another_order, sin nada cargado el turno sigue
    el pipeline normal (antes: '¡Con gusto cargamos otra! ... ¿Cuál es la dirección?')."""
    reply, _ = _run_turn("necesito un perfil renal para un paciente", "another_order",
                         SOLO_CLIENTE)
    assert "con gusto cargamos otra" not in reply.lower()


def test_frontera_con_orden_cargada_sigue_viva():
    """Con paciente + análisis cargados, 'otra orden para otro paciente' sigue
    marcando la frontera (ERR-117 intacto)."""
    captured = dict(ORDEN_COMPLETA)
    reply, _ = _run_turn("necesito otra orden para otro paciente", "another_order",
                         captured)
    assert "otra" in reply.lower() or "orden" in reply.lower()


def test_correccion_de_dato_resetea_el_anti_bucle():
    """Ítem 7 (guion QA1): corregir un dato ("me equivoqué, es un Holstein") es
    progreso — el anti-bucle no debe escalar a un asesor al tercer turno."""
    captured = dict(SOLO_CLIENTE, patient_name="Toro", species="Bovino",
                    breed="Criollo", _offtrack_count=2)
    reply, persisted = _run_turn("me equivoqué, es un Holstein", "unclear", captured,
                                 ai_fields={"breed": "Holstein"})
    assert "asesor" not in (reply or "").lower(), f"escaló: {reply[:80]}"
    fields = persisted.get("captured_fields", {}) if persisted else {}
    assert not fields.get("_offtrack_count"), "el contador no se reseteó"
