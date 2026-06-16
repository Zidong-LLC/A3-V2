"""
Validación del flujo conversacional contra el modelo REAL (OpenAI).
Mockea solo la base de datos (Supabase) en memoria; `ai.generate_turn` es real.

Sirve para confirmar los caminos del cliente que no sigue los pasos:
- typo/variante de especie ("Kanino", "es un gatito")
- especie ambigua ("Kany") -> el modelo debería confirmar, no repetir
- off-topic ("¿cómo vas?") cuando se pide el médico -> reencauce cálido

Uso:  python tools/scripts/validate_coherence.py
Es temporal: se puede borrar cuando termine la validación.
"""
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# Estado en memoria compartido por las funciones falsas de db.
_state = {"session": None, "history": None}


def _fake_get_session(chat_id, channel="telegram"):
    return _state["session"]


def _fake_get_history(chat_id, limit=8):
    return _state["history"][-limit:]


def _fake_save(chat_id, text, role):
    _state["history"].append({"role": role, "content": text})


def _fake_update(chat_id, ai_response):
    s = _state["session"]
    s["phase_current"] = ai_response["phase"]
    s["intent_current"] = ai_response["intent"]
    s["captured_fields"] = ai_response["captured_fields"]


_DB_PATCHES = {
    "get_or_create_session": dict(side_effect=_fake_get_session),
    "get_recent_messages": dict(side_effect=_fake_get_history),
    "save_message": dict(side_effect=_fake_save),
    "update_session": dict(side_effect=_fake_update),
    "get_catalog_context": dict(return_value=""),
    "get_individual_tests_context": dict(return_value=""),
    "list_diagnostic_labels": dict(return_value=[]),
    "find_diagnostic_label": dict(return_value=None),
    "find_catalog_profiles": dict(return_value=[]),
    "find_catalog_profile": dict(return_value=None),
    "find_tests_by_area": dict(return_value=(None, [])),
    "get_courier_for_client": dict(return_value=None),
    "create_request": dict(return_value={"request_id": "r", "order_number": "A3-2026-001"}),
}


def _base_session(asked_field_question, **field_overrides):
    captured = {
        "_client_found": True,
        "_client_display_name": "Veterinaria Test",
        "_client_address": "Calle 1 # 2-3",
        "clinic_name": "Veterinaria Test",
        "pickup_address": "Calle 1 # 2-3",
        "requesting_doctor": "Dra. Ana",
        "patient_name": "Toby",
        "species": None, "breed": None, "sex": None, "patient_age": None,
        "owner_name": None, "observations": None, "exam_type": None,
        "payment_method": None, "selected_tests": None, "removed_tests": None,
    }
    captured.update(field_overrides)
    return {
        "external_chat_id": "validate-1",
        "client_id": "client-x",
        "phase_current": "fase_2_recogida_datos",
        "intent_current": "route_scheduling",
        "captured_fields": captured,
    }, [
        {"role": "user", "content": "quiero programar una recogida"},
        {"role": "bot", "content": asked_field_question},
    ]


CASES = [
    ("Typo de especie", "¿Es canino, felino u otra especie?",
     {"species": None}, "Kanino", "species"),
    ("Especie en frase", "¿Es canino, felino u otra especie?",
     {"species": None}, "es un gatito", "species"),
    ("Especie ambigua", "¿Es canino, felino u otra especie?",
     {"species": None}, "Kany", "species"),
    ("Off-topic en médico", "Perfecto. ¿Cuál es el médico solicitante?",
     {"requesting_doctor": None}, "jaja, ¿y cómo vas?", "requesting_doctor"),
    ("Typo de sexo", "¿El paciente es macho o hembra?",
     {"species": "Canino", "breed": "Criollo", "sex": None}, "masho", "sex"),
]


def main():
    from app.agent import process_turn

    patchers = [patch(f"app.services.db.{name}", **kw) for name, kw in _DB_PATCHES.items()]
    for p in patchers:
        p.start()
    try:
        for title, bot_q, overrides, user_msg, watch_field in CASES:
            session, history = _base_session(bot_q, **overrides)
            _state["session"] = session
            _state["history"] = history
            print("=" * 70)
            print(f"CASO: {title}")
            print(f"  bot pidió : {bot_q}")
            print(f"  usuario   : {user_msg}")
            try:
                reply = process_turn("validate-1", user_msg)
            except Exception as exc:  # noqa: BLE001
                print(f"  ERROR llamando al modelo: {type(exc).__name__}: {exc}")
                continue
            captured = _state["session"]["captured_fields"]
            print(f"  BOT       : {reply}")
            print(f"  {watch_field} capturado -> {captured.get(watch_field)!r}")
    finally:
        for p in patchers:
            p.stop()


if __name__ == "__main__":
    main()
