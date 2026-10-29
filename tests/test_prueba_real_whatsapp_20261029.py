"""Primera prueba humana por WhatsApp en producción (2026-10-29): dos bucles reales.

Los estados de abajo son los de las SESIONES REALES (telegram_sessions.captured_fields)
con los datos personales reemplazados; se conservan todas las marcas internas, que es lo
que los arneses con estados inventados no replicaban (ERR-195). El catálogo simulado
devuelve filas reales por código, como la base.

Chat 1 — orden recién registrada, oferta "¿otra orden… o cerramos el pedido?" pendiente:
"No" caía en la corrección post-cierre ("¿qué dato quieres corregir?").
Chat 3 — segunda orden con datos heredados y "en otra dirección": el modelo devolvió los
tres códigos sin el rótulo del paquete y "no más análisis" borraba la selección.
"""
import sys
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

import pytest

from app import agent
from tests.test_etapa2_senal_confirmacion import _neutral_ai_response

CATALOGO = {
    "1701": {"code": "1701", "name": "Coprológico", "price": 12000, "category": "Parasitología"},
    "1702": {"code": "1702", "name": "Coproscópico", "price": 15000, "category": "Parasitología"},
    "2057": {"code": "2057", "name": "Panleucopenia Felina (Antígeno)", "price": 55000, "category": "Inmunológico"},
}

# Chat 1 tras "Sin" (observaciones): orden A3-2026-003 registrada, pedido abierto.
CHAT1_TRAS_REGISTRAR = {
    "tax_id": "800000001", "clinic_name": "Veterinaria Prueba Uno", "_client_found": True,
    "_client_display_name": "Veterinaria Prueba Uno", "_client_phone": "3000000000", "_client_email": "",
    "_client_address": "Calle 1 # 2-3", "pickup_address": "Calle 1 # 2-3", "_address_confirmed": True,
    "_address_confirmation_pending": False, "_client_not_found": False,
    "requesting_doctor": "Dra Prueba", "_client_memory": {"pickup_address": "Calle 1 # 2-3", "requesting_doctor": "Dra Prueba"},
    "sex": None, "breed": None, "species": None, "exam_type": None, "owner_name": None, "patient_age": None,
    "patient_name": None, "selected_tests": [], "removed_tests": [], "sample_taken_date": None,
    "observations": "sin observaciones", "payment_method": None,
    "_pedido_id": "ped-1", "_last_request_id": "req-3", "_last_order_number": "A3-2026-003",
    "_order_registered": True, "_pedido_offer_pending": True, "_pending_intents": [],
    "_pedido_ordenes": [{"total": 23760, "species": "Felino", "exam_type": None, "order_number": "A3-2026-003",
                         "patient_name": "Roku", "requesting_doctor": "Dra Prueba"}],
    "_pedido_profiles": [{"added_tests": [CATALOGO["1701"], CATALOGO["1702"]], "base_profile": {"code": None, "name": "Perfil personalizado (2 análisis)", "price": 0},
                          "removed_tests": [], "extra_profiles": [], "included_tests": [], "total_estimated": 23760,
                          "price_adjustment": {"base": 0, "added": 27000, "total": 23760, "removed": 0, "subtotal": 27000, "volume_discount": 3240}}],
    "_prev_order_snapshot": {"sex": "Hembra", "breed": "Ragdoll", "species": "Felino", "owner_name": "Propietario Prueba",
                             "patient_age": "5 años", "observations": "sin observaciones", "patient_name": "Roku",
                             "pickup_address": "Calle 1 # 2-3", "requesting_doctor": "Dra Prueba", "sample_taken_date": "Hoy"},
    "_test_menu_options": [CATALOGO["1701"], CATALOGO["1702"]],
}
HIST1 = [{"role": "user", "content": "Sin"},
         {"role": "bot", "content": "Perfecto, registro la orden sin observaciones.\n\nNúmero de orden: A3-2026-003\n\n"
                                    "¿Necesitas cargar otra orden para otro paciente? Escríbeme: otra orden. "
                                    "Si eso es todo, seguimos con la forma de pago y cerramos el pedido."}]

# Chat 3 — segunda orden (Mickey) con datos heredados, justo antes de "1701, 2057 y 1702".
CHAT3_ANTES_DE_CODIGOS = {
    "tax_id": "800000002", "clinic_name": "Clínica Prueba Dos", "_client_found": True, "_client_display_name": "Clínica Prueba Dos",
    "_client_phone": "3000000002", "_client_email": "", "_client_not_found": False,
    "_client_address": "Calle 10 # 20-30", "pickup_address": "Carrera 5 # 6-7 Sur", "_address_confirmed": False,
    "_address_confirmation_pending": False, "requesting_doctor": "Dra Prueba",
    "_client_memory": {"pickup_address": "Carrera 5 # 6-7 Sur", "requesting_doctor": "Dra Prueba"},
    "patient_name": "Mickey", "species": "Felino", "breed": "Himalayo De Pelo Corto", "sex": "Macho",
    "patient_age": "3 años", "owner_name": "Propietario Prueba", "sample_taken_date": "Hoy",
    "observations": "sin observaciones", "exam_type": None, "selected_tests": None, "removed_tests": None,
    "payment_method": None, "_pedido_id": "ped-2", "_last_request_id": "req-4", "_last_order_number": "A3-2026-004",
    "_correction_pending": True, "_prev_order_snapshot": {"pickup_address": "Calle 10 # 20-30"}, "_pending_intents": [],
    "_pedido_ordenes": [{"total": 66000, "species": "Felino", "exam_type": "Perfil personalizado (2 análisis)",
                         "order_number": "A3-2026-004", "patient_name": "Coko", "requesting_doctor": "Dra Prueba"}],
    "_pedido_profiles": [{"added_tests": [CATALOGO["1701"]], "base_profile": {"code": None, "name": "Perfil personalizado (2 análisis)", "price": 0},
                          "removed_tests": [], "extra_profiles": [], "included_tests": [], "total_estimated": 66000,
                          "price_adjustment": {"base": 0, "added": 75000, "total": 66000, "removed": 0, "subtotal": 75000, "volume_discount": 9000}}],
}
HIST3 = [{"role": "user", "content": "Hoy"}, {"role": "bot", "content": "Perfecto, lo anoto. ¿Qué análisis o perfil desean?"}]


def _por_codigo(items):
    return [CATALOGO[str(i)] for i in (items or []) if str(i) in CATALOGO]


def turno(msg, signal, captured, phase, history, ai_fields=None, reply=None, channel="whatsapp"):
    """Un turno con la base simulada fiel: catálogo por código real, escrituras capturadas."""
    session = {"external_chat_id": "w1", "client_id": "cli-A", "channel": channel,
               "phase_current": phase, "intent_current": "route_scheduling",
               "captured_fields": dict(captured), "status": "in_progress"}
    fdb = MagicMock()
    fdb.get_or_create_session.return_value = session
    fdb.get_recent_messages.return_value = list(history)
    fdb.get_client_memory.return_value = None
    fdb.list_catalog_tests.return_value = list(CATALOGO.values())
    fdb.find_tests_by_area.return_value = (None, [])
    fdb.get_tests_by_codes_or_names.side_effect = _por_codigo
    fdb.get_tests_by_codes.side_effect = _por_codigo
    fdb.get_catalog_profiles_by_codes.return_value = []
    fdb.list_catalog_profiles_for_species.return_value = []
    fdb.list_catalog_profiles_matching_category.return_value = []
    fdb.find_catalog_profile.return_value = None
    fdb.list_diagnostic_labels.return_value = []
    ai = _neutral_ai_response(signal)
    if ai_fields is not None:
        ai["captured_fields"] = dict(captured, **ai_fields)
    if reply:
        ai["reply"] = reply
    with ExitStack() as stack:
        seen = set()
        for name, mod in list(sys.modules.items()):
            if name.startswith("app") and hasattr(mod, "db") and id(mod) not in seen:
                seen.add(id(mod))
                stack.enter_context(patch.object(mod, "db", fdb))
        stack.enter_context(patch.object(agent.ai, "generate_turn", return_value=ai))
        out = agent.process_turn("w1", msg, channel=channel)
    persisted = fdb.update_session.call_args[0][1] if fdb.update_session.call_args else {}
    return out, (persisted.get("captured_fields") or {}), persisted.get("phase")


# ── Chat 1: "No" a la oferta del pedido ──────────────────────────────────────────────


@pytest.mark.parametrize("msg,signal", [("No", "negate"), ("No", "farewell"), ("no, eso es todo", "negate"),
                                        ("No gracias", "negate"), ("no mas analisis", "negate")])
def test_no_con_senal_clara_pasa_al_pago(msg, signal):
    reply, f, _ = turno(msg, signal, CHAT1_TRAS_REGISTRAR, "fase_6_cierre", HIST1)
    assert reply == agent.PEDIDO_CLOSING_QUESTION
    assert f.get("_pedido_awaiting_payment") and not f.get("_pedido_offer_pending")


@pytest.mark.parametrize("signal", ["unclear", "correction", "affirm"])
def test_no_pelado_sin_senal_clara_repregunta_una_vez(signal):
    reply, f, _ = turno("No", signal, CHAT1_TRAS_REGISTRAR, "fase_6_cierre", HIST1)
    assert reply == agent.PEDIDO_OFFER_REASK
    assert f.get("_pedido_offer_reasked") and f.get("_pedido_offer_pending")


def test_segundo_no_pelado_cierra_y_pide_el_pago():
    reply, f, _ = turno("No", "unclear", dict(CHAT1_TRAS_REGISTRAR, _pedido_offer_reasked=True), "fase_6_cierre", HIST1)
    assert reply == agent.PEDIDO_CLOSING_QUESTION
    assert f.get("_pedido_awaiting_payment")


def test_una_correccion_de_verdad_sigue_corrigiendo():
    reply, _, _ = turno("no, está mal la raza", "correction", CHAT1_TRAS_REGISTRAR, "fase_6_cierre", HIST1)
    assert "raza" in reply.lower() and reply != agent.PEDIDO_OFFER_REASK


# ── Chat 3: códigos del modelo sin rótulo y "no más análisis" ───────────────────────


RESPUESTA_MODELO_CODIGOS = ("Perfecto. Registro estos análisis para Mickey:\n- 1701 Coprológico $12.000\n"
                            "- 2057 Panleucopenia Felina (Antígeno) $55.000\n- 1702 Coproscópico $15.000\n\n"
                            "¿Desean agregar otro análisis o lo dejamos así?")


def test_codigos_capturados_por_el_modelo_completan_la_orden():
    """Forma REAL de la respuesta del modelo (replay 29/10): selected_tests con los tres
    códigos, exam_type vacío, señal provides_requested_data, fase 4."""
    reply, f, phase = turno("1701, 2057 y 1702", "provides_requested_data", CHAT3_ANTES_DE_CODIGOS, "fase_2_recogida_datos",
                            HIST3, ai_fields={"selected_tests": ["1701", "2057", "1702"], "exam_type": None},
                            reply=RESPUESTA_MODELO_CODIGOS)
    assert sorted(f.get("selected_tests")) == ["1701", "1702", "2057"]
    assert f.get("exam_type") == "Perfil personalizado (3 análisis)"
    assert "¿Confirmas estos datos?" in reply and "2057" in reply
    assert phase == agent.CONFIRMATION_PHASE


def test_no_mas_analisis_frente_al_resumen_no_borra_los_codigos():
    estado = dict(CHAT3_ANTES_DE_CODIGOS, selected_tests=["1701", "2057", "1702"], exam_type="Perfil personalizado (3 análisis)",
                  removed_tests=[])
    estado.pop("_correction_pending")
    hist = HIST3 + [{"role": "user", "content": "1701, 2057 y 1702"}, {"role": "bot", "content": "Antes de registrar, te resumo la orden… ¿Confirmas estos datos?"}]
    reply, f, phase = turno("no mas analisis", "negate", estado, agent.CONFIRMATION_PHASE, hist,
                            ai_fields={}, reply="Perfecto, dejamos la orden así.")
    assert sorted(f.get("selected_tests") or []) == ["1701", "1702", "2057"], "el paquete se borraba"
    assert f.get("exam_type") == "Perfil personalizado (3 análisis)"
    assert "¿Confirmas estos datos?" in reply
    assert phase == agent.CONFIRMATION_PHASE


def test_corregir_la_direccion_heredada_de_una_orden_nueva_no_deja_marca():
    """'otra orden' (datos heredados, sin paciente, fase confirmación) → 'en otra dirección':
    pide la dirección y NO prende _correction_pending — no hay resumen que re-mostrar, y
    viva se arrastraba por toda la orden nueva. Con paciente (orden existente) sí la prende."""
    heredado = dict(CHAT3_ANTES_DE_CODIGOS, patient_name=None, species=None, breed=None, sex=None, patient_age=None,
                    owner_name=None, sample_taken_date=None, pickup_address="Calle 10 # 20-30", _address_confirmed=True)
    heredado.pop("_correction_pending")
    hist = [{"role": "user", "content": "otra orden"},
            {"role": "bot", "content": "Perfecto, creamos otra orden de servicio. Mantengo estos datos de la orden anterior:\n"
                                       "- Dirección de retiro: Calle 10 # 20-30\n¿Confirmas o quieres cambiar alguno (dirección, médico o análisis)?"}]
    reply, f, _ = turno("en otra direccion recoger", "correction", heredado, agent.CONFIRMATION_PHASE, hist, ai_fields={}, reply="ok")
    assert "dirección" in reply.lower()
    assert not f.get("_correction_pending")
    # Orden existente con paciente: la marca sigue cumpliendo su función.
    con_paciente = dict(heredado, patient_name="Mickey", species="Felino", breed="Himalayo", sex="Macho", patient_age="3 años",
                        owner_name="Propietario Prueba", sample_taken_date="Hoy", exam_type="1701 Coprológico", selected_tests=["1701"])
    _, f2, _ = turno("en otra direccion recoger", "correction", con_paciente, agent.CONFIRMATION_PHASE, hist, ai_fields={}, reply="ok")
    assert f2.get("_correction_pending")


# ── Detectores ──────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("msg,pelada,sin_correccion", [
    ("No", True, True), ("no gracias", True, True), ("nop", True, True), ("no señor", True, True),
    ("no, eso es todo", False, True), ("no quiero otra", False, True),
    ("no, está mal la raza", False, False), ("no, la raza es tobiano", False, False), ("otra", False, True),
])
def test_detectores_de_negativa(msg, pelada, sin_correccion):
    assert agent._es_negacion_pelada(msg) is pelada
    assert agent._sin_pedido_de_correccion(msg) is sin_correccion


@pytest.mark.parametrize("msg,reemplaza", [
    ("no mas analisis", False), ("no, ninguno mas", False), ("el mismo pero sin la glucosa", False),
    ("analisis quiero el 653", True), ("quiero otro analisis", True), ("cambia el analisis", True),
])
def test_no_mas_analisis_no_es_reemplazo(msg, reemplaza):
    from app.detectors.analisis import _replaces_offered_analysis
    assert _replaces_offered_analysis(msg, "652") is reemplaza
