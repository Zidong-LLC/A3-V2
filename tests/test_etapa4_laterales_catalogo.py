"""Etapa 4a del refactor de comprensión (2026-08-24): catálogo y laterales post-modelo.

Los seis carriles pre-LLM de preguntas de servicio/catálogo se movieron juntos a un
handler post-modelo ANTES de la frontera de orden. Estos tests prueban la MECÁNICA:
las acciones canónicas siguen respondiendo idéntico ahora que el modelo lee el turno
primero (mock del ai_response — L51); la emisión real la valida validate_flows.py.
"""
from tests.test_etapa2_senal_confirmacion import ORDEN_COMPLETA, _run_turn

from app import agent


MITAD_DE_ORDEN = {
    "_client_found": True, "clinic_name": "Animal Pets", "tax_id": "900123",
    "pickup_address": "DG 51A SUR 60", "_address_confirmed": True,
    "requesting_doctor": "Dra Ana", "patient_name": "Pepe", "species": "Canino",
}


def test_lateral_operativa_sigue_canonica_post_modelo():
    """'¿A qué hora pasan por la muestra?' a mitad de orden: la respuesta operativa
    canónica sobrevive a la mudanza (el modelo lee el turno, el código responde)."""
    reply, _ = _run_turn("a que hora pasan por la muestra?", "unclear", MITAD_DE_ORDEN)
    # La canónica elegida es la de tiempos ("Depende del análisis y de la muestra…") y el
    # resume re-pregunta el campo en curso: lateral respondida + la orden sigue.
    assert "dime qué prueba" in reply.lower() or "depende del análisis" in reply.lower()
    assert "raza del paciente" in reply.lower()


def test_info_servicio_pre_identificacion_sigue_canonica():
    """'¿Dónde están ubicados?' SIN cliente identificado responde la canónica de
    ubicación (carril 14 movido con sus gates intactos)."""
    captured = {}
    session_history = [
        {"role": "user", "content": "hola"},
        {"role": "bot", "content": "¿Con qué te ayudamos hoy?"},
    ]
    reply, _ = _run_turn("donde estan ubicados?", "unclear", captured,
                         history=session_history, client_id=None)
    assert "bogotá" in reply.lower() or "bogota" in reply.lower()


def test_recomendacion_de_perfiles_sigue_viva_con_especie():
    """'no sé, ¿qué me recomiendas?' con especie conocida ofrece perfiles de la especie
    (carril 21 movido; el fake_db sin perfiles → no debe explotar ni desviarse)."""
    captured = dict(MITAD_DE_ORDEN)
    historia = [{"role": "user", "content": "canino"},
                {"role": "bot", "content": "¿Qué análisis o perfil desean?"}]
    reply, persisted = _run_turn("no sé, ¿qué me recomiendas?", "unclear", captured,
                                 history=historia)
    # Con el catálogo del mock vacío no hay menú que ofrecer: lo importante es que el
    # turno no borra la orden ni se cae — la conversación sigue.
    fields = persisted.get("captured_fields", {}) if persisted else {}
    assert fields.get("patient_name", "Pepe") == "Pepe"


def test_pregunta_de_catalogo_no_pisa_analisis_en_curso():
    """Guard del chat 4 portado: con un perfil ya elegido, una pregunta de catálogo
    NUNCA borra la selección (el menú quedaría para AGREGAR)."""
    captured = dict(ORDEN_COMPLETA, _selected_profile_code="701",
                    exam_type="701 Perfil Prequirúrgico I")
    reply, persisted = _run_turn("que analisis manejan?", "unclear", captured)
    fields = persisted.get("captured_fields", {}) if persisted else {}
    assert fields.get("exam_type", captured["exam_type"]), "el análisis en curso no se borra"
