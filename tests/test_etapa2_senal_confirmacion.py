"""Etapa 2 del refactor de comprensión (2026-08-21, ficha ABIERTO-003):

Los atajos pre-LLM de la reoferta de estables, las correcciones en CONFIRMACIÓN y la
oferta de análisis extra se degradaron a handlers post-modelo señal-primero. Estos tests
prueban la MECÁNICA (guards, acción, red de tokens) con la señal fingida — la emisión
real de la señal la validan validate_flows.py (modelo real) y la prueba en vivo (L51).

La ganancia que se verifica acá: fraseos que NINGUNA lista de tokens conoce ahora se
entienden porque la señal del modelo manda ("uy creo que ese dato quedó distinto",
"nop, hasta ahí llegamos nomás", "obvio, metele").
"""
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

from app import agent
from app import orders as _orders, menus as _menus, laterales as _laterales
from app.enforcers import orden as _orden


def _neutral_ai_response(signal="unclear", reply="ok, sigo con la orden"):
    return {
        "reply": reply, "phase": "fase_2_recogida_datos", "intent": "route_scheduling",
        "service_area": "route_scheduling", "requires_handoff": False, "handoff_area": None,
        "captured_fields": {}, "confidence": 0.9, "message_mode": "flow_progress",
        "pending_intents": [], "user_intent_signal": signal, "resume_prompt": "",
    }


# Orden COMPLETA (todos los campos requeridos de la ruta) — base para confirmación/oferta.
ORDEN_COMPLETA = {
    "_client_found": True, "clinic_name": "Animal Pets", "tax_id": "900123",
    "pickup_address": "DG 51A SUR 60", "_address_confirmed": True,
    "requesting_doctor": "Dra Ana", "patient_name": "Pepe", "species": "Canino",
    "breed": "Beagle", "sex": "Macho", "patient_age": "3 años", "owner_name": "Juan",
    "sample_taken_date": "hoy",
    "observations": "ninguna", "exam_type": "Sodio", "selected_tests": ["1405"],
}


def _run_turn(msg, signal, captured, phase="fase_2_recogida_datos", history=None,
              client_id="cli-A", return_db=False, ai_fields=None):
    session = {
        "external_chat_id": "c1", "client_id": client_id, "channel": "telegram",
        "phase_current": phase, "intent_current": "route_scheduling",
        "captured_fields": dict(captured), "status": "in_progress",
    }
    fake_db = MagicMock()
    fake_db.get_or_create_session.return_value = session
    fake_db.get_recent_messages.return_value = history or [
        {"role": "user", "content": "hola"}, {"role": "bot", "content": "¿confirmas?"},
    ]
    fake_db.get_client_memory.return_value = None
    fake_db.list_catalog_tests.return_value = []
    fake_db.find_tests_by_area.return_value = (None, [])
    fake_db.get_tests_by_codes_or_names.return_value = []
    fake_db.get_catalog_profiles_by_codes.return_value = []
    fake_db.list_catalog_profiles_for_species.return_value = []
    fake_db.list_catalog_profiles_matching_category.return_value = []
    fake_db.get_tests_by_codes.return_value = []
    fake_db.find_catalog_profile.return_value = None
    fake_db.list_diagnostic_labels.return_value = []
    # El carril de la oferta cruza a enforcers/orden.py, orders.py, menus.py y
    # laterales.py, que importan su PROPIO `db`: sin estos parches el test golpea
    # la red real (ConnectError con la BD fuera de alcance).
    with ExitStack() as stack:
        # TODOS los módulos de app cargados que importan su propio `db` (ERR del harness:
        # enforcers/confirmacion.py llamaba a la red real por no estar en la lista fija).
        import sys as _sys
        seen = set()
        for name, mod in list(_sys.modules.items()):
            if name.startswith("app") and hasattr(mod, "db") and id(mod) not in seen:
                seen.add(id(mod))
                stack.enter_context(patch.object(mod, "db", fake_db))
        _ai = _neutral_ai_response(signal)
        if ai_fields:
            _ai["captured_fields"] = dict(ai_fields)
        stack.enter_context(patch.object(agent.ai, "generate_turn", return_value=_ai))
        reply = agent.process_turn("c1", msg)
    persisted = (fake_db.update_session.call_args[0][1]
                 if fake_db.update_session.call_args else {})
    if return_db:
        return reply, persisted, fake_db
    return reply, persisted


# ── Correcciones en CONFIRMACIÓN ─────────────────────────────────────────────


def test_correccion_en_confirmacion_por_senal_fuera_de_toda_lista():
    """El fraseo no está en ninguna lista; la señal `correction` del modelo basta."""
    msg = "uy creo que ese dato quedo distinto a como es"
    assert not agent._is_correction_request(msg), "el fraseo NO debe estar en la red"
    reply, persisted = _run_turn(msg, "correction", ORDEN_COMPLETA,
                                 phase=agent.CONFIRMATION_PHASE)
    fields = persisted.get("captured_fields", {})
    assert fields.get("_correction_pending") is True
    assert "cambiar" in reply.lower() or "corregir" in reply.lower() or "dato" in reply.lower()


def test_correccion_en_confirmacion_red_de_tokens_sigue_viva():
    """Sin señal (unclear), el fraseo conocido sigue funcionando por la red."""
    reply, persisted = _run_turn("quiero cambiar el médico", "unclear", ORDEN_COMPLETA,
                                 phase=agent.CONFIRMATION_PHASE)
    assert "médico" in reply.lower() or "medico" in reply.lower()
    assert persisted.get("captured_fields", {}).get("_correction_pending") is True


def test_cambio_de_cliente_en_confirmacion_por_senal():
    """`change_client` en el resumen re-abre la identificación (ERR-099)."""
    msg = "esa cuenta pertenece a otra sede del grupo"
    reply, persisted = _run_turn(msg, "change_client", ORDEN_COMPLETA,
                                 phase=agent.CONFIRMATION_PHASE)
    assert "nit" in reply.lower() or "nombre" in reply.lower() or "veterinaria" in reply.lower()


# ── Reoferta de estables (_stable_confirm_pending) ───────────────────────────


def test_stable_confirm_negativa_por_senal_fuera_de_lista():
    """'mmm eso quedo raro' + negate → pregunta qué dato cambiar (antes: pasaba de largo)."""
    captured = dict(ORDEN_COMPLETA, _stable_confirm_pending=True)
    msg = "mmm eso quedo raro"
    assert not agent._is_correction_request(msg) and not agent._is_negative_text(msg)
    reply, persisted = _run_turn(msg, "negate", captured)
    assert "qué dato" in reply.lower() or "que dato" in reply.lower()
    assert not persisted.get("captured_fields", {}).get("_stable_confirm_pending")


def test_stable_confirm_bare_si_mantiene_plantilla():
    """El 'sí' pelado conserva la respuesta determinística de siempre (L65)."""
    captured = dict(ORDEN_COMPLETA, _stable_confirm_pending=True)
    captured.pop("patient_name")  # la orden nueva pide su paciente
    reply, persisted = _run_turn("sí", "affirm", captured)
    assert "cambia normalmente" in reply.lower()
    assert not persisted.get("captured_fields", {}).get("_stable_confirm_pending")


# ── La oferta de análisis extra ──────────────────────────────────────────────


def test_oferta_cierra_por_senal_negate_con_fraseo_desconocido():
    """'nop, hasta ahí llegamos nomás' no está en ninguna lista: la señal cierra la
    oferta y muestra la confirmación de la orden."""
    from app.detectors.analisis import _wants_to_proceed_to_payment

    msg = "nop, hasta ahi llegamos nomas"
    assert not _wants_to_proceed_to_payment(msg), "el fraseo NO debe estar en la red"
    captured = dict(ORDEN_COMPLETA, _offering_extra_analysis=True)
    reply, persisted = _run_turn(msg, "negate", captured)
    assert "resumo la orden" in reply.lower() or "confirmas" in reply.lower()
    assert not persisted.get("captured_fields", {}).get("_offering_extra_analysis")


def test_oferta_affirm_pregunta_cual():
    """'obvio, metele' + affirm → pregunta cuál análisis (antes caía en la re-pregunta)."""
    captured = dict(ORDEN_COMPLETA, _offering_extra_analysis=True)
    reply, persisted = _run_turn("obvio, metele", "affirm", captured)
    assert "qué análisis" in reply.lower() or "que analisis" in reply.lower()
    assert persisted.get("captured_fields", {}).get("_awaiting_additional_test") == "add"


def test_oferta_correction_cede_el_turno_completo():
    """Una corrección leída por el modelo no es de este carril: el pipeline la captura."""
    captured = dict(ORDEN_COMPLETA, _offering_extra_analysis=True)
    reply, persisted = _run_turn("ehh el nombre del dueño esta mal escrito",
                                 "correction", captured)
    # No debe responder con la re-pregunta de la oferta ni cerrar la orden a ciegas.
    assert "agregamos otro análisis" not in reply.lower()


def test_agregar_analisis_en_confirmacion_no_lo_secuestra_la_correccion():
    """Guion X (2026-08-24): 'quiero agregarle un analisis de orina al perfil' llega con
    señal `correction` y NINGUNA red de corrección la reconoce — el handler 2a la
    secuestraba, borraba el análisis de la orden y respondía la plantilla del dato
    faltante. Debe ceder al carril del catálogo (L66) sin tocar el análisis."""
    captured = dict(ORDEN_COMPLETA, _selected_profile_code="701",
                    exam_type="701 Perfil Prequirúrgico I")
    reply, persisted = _run_turn("quiero agregarle un analisis de orina al perfil",
                                 "correction", captured, phase=agent.CONFIRMATION_PHASE)
    fields = persisted.get("captured_fields", {})
    assert fields.get("exam_type"), "el análisis de la orden no debe borrarse"
    assert not reply.strip().lower().startswith("¿qué análisis o perfil desean?")
