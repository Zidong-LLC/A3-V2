"""Ítem 6 pre-lanzamiento (2026-08-24, guion U): pedir una CATEGORÍA de perfiles con el
menú genérico en pantalla refresca _profile_menu_options con los armados de la categoría
— así "el 1" del turno siguiente elige del menú nuevo (antes quedaba 401 en vez de 701)."""
from contextlib import ExitStack
from unittest.mock import MagicMock, patch
import sys

from app import agent


def test_categoria_pisa_menu_generico_activo():
    generico = [{"code": "401", "name": "Perfil Canino I", "price": 40000},
                {"code": "701", "name": "Perfil Prequirúrgico I", "price": 24000}]
    captured = {
        "_client_found": True, "clinic_name": "Animal Pets", "tax_id": "900123",
        "pickup_address": "DG 51A SUR 60", "_address_confirmed": True,
        "requesting_doctor": "Dra Ana", "patient_name": "Anahi", "species": "Canino",
        "breed": "Pitbull", "sex": "Hembra", "patient_age": "2 años",
        "owner_name": "Luciano", "observations": "sin observaciones",
        "_profile_menu_options": generico,
    }
    prequir = [{"code": "701", "name": "Perfil Prequirúrgico I", "price": 24000,
                "category": "prequirúrgico"},
               {"code": "702", "name": "Perfil Prequirúrgico II", "price": 36000,
                "category": "prequirúrgico"}]
    session = {"external_chat_id": "c1", "client_id": "cli-A", "channel": "telegram",
               "phase_current": "fase_2_recogida_datos", "intent_current": "route_scheduling",
               "captured_fields": dict(captured), "status": "in_progress"}
    fake_db = MagicMock()
    fake_db.get_or_create_session.return_value = session
    fake_db.get_recent_messages.return_value = [
        {"role": "user", "content": "sin observaciones"},
        {"role": "bot", "content": "Para canino te puedo recomendar estos perfiles: 1. 401..."}]
    fake_db.get_client_memory.return_value = None
    fake_db.list_catalog_profiles_matching_category.return_value = prequir
    fake_db.find_tests_by_area.return_value = (None, [])
    fake_db.get_tests_by_codes_or_names.return_value = []
    fake_db.list_catalog_tests.return_value = []
    fake_db.get_catalog_profiles_by_codes.return_value = []
    fake_db.list_diagnostic_labels.return_value = []
    ai = {"reply": "ok", "phase": "fase_2_recogida_datos", "intent": "route_scheduling",
          "service_area": "route_scheduling", "requires_handoff": False, "handoff_area": None,
          "captured_fields": {}, "confidence": 0.9, "message_mode": "flow_progress",
          "pending_intents": [], "user_intent_signal": "unclear", "resume_prompt": ""}
    with ExitStack() as st:
        seen = set()
        for name, mod in list(sys.modules.items()):
            if name.startswith("app") and hasattr(mod, "db") and id(mod) not in seen:
                seen.add(id(mod))
                st.enter_context(patch.object(mod, "db", fake_db))
        st.enter_context(patch.object(agent.ai, "generate_turn", return_value=ai))
        reply = agent.process_turn("c1", "cuál me recomiendas pre quirúrgico? qué perfil tienen?")
    persisted = (fake_db.update_session.call_args[0][1]
                 if fake_db.update_session.call_args else {})
    assert "701" in reply and "702" in reply
    menu = persisted.get("captured_fields", {}).get("_profile_menu_options") or []
    codes = [str(m.get("code")) for m in menu]
    assert codes and "401" not in codes and "701" in codes, f"menú activo: {codes}"
