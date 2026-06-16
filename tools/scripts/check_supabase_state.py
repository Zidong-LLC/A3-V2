"""Auditoria read-only del estado esperado en Supabase.

No aplica migraciones ni modifica datos. Verifica que existan las tablas/columnas
que usa el agente y reporta conteos para detectar cargas pendientes.

Uso: python tools/scripts/check_supabase_state.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services import db  # noqa: E402


CHECKS = [
    ("core", "clients", "id, clinic_name, tax_id, phone, address, zone, billing_type, is_active", True),
    ("core", "couriers", "id, name, phone, availability, is_active", True),
    ("core", "client_courier_assignment", "client_id, courier_id", True),
    (
        "core",
        "requests",
        "id, client_id, entry_channel, service_area, intent, priority, status, exam_type, "
        "patient_name, species, patient_age, owner_name, pickup_address, requested_at, "
        "scheduled_pickup_date, assigned_courier_id, fallback_reason, order_number",
        True,
    ),
    ("core", "request_events", "id, request_id, event_type, event_payload, created_at", True),
    (
        "core",
        "telegram_sessions",
        "channel, external_chat_id, client_id, phase_current, intent_current, captured_fields, "
        "status, service_area, requires_handoff, handoff_area, last_bot_message, ai_confidence",
        True,
    ),
    ("history", "conversation_messages", "id, external_chat_id, role, content, created_at", True),
    ("catalog", "catalog_profiles", "code, name, category, species, description, price, is_active", True),
    ("catalog", "catalog_tests", "code, name, category, species, sample, price, is_active", True),
    ("profiles", "client_custom_profiles", "id, client_id, name, items_json, created_at, created_by", True),
    ("orders", "order_number_counters", "year, last_seq", True),
    ("diagnostics", "diagnostic_label_tests", "id, label, test_code", True),
    ("territory", "territorial_zones", "zone_number, courier_id, courier_name, total_barrios", False),
    ("territory", "territorial_neighborhoods", "id, locality_code, neighborhood_name, zone_number", False),
]


def _check_table(group: str, table: str, columns: str, required: bool) -> tuple[bool, str]:
    try:
        result = db._client.table(table).select(columns, count="exact").limit(1).execute()
    except Exception as exc:  # noqa: BLE001
        level = "ERROR" if required else "WARN"
        return not required, f"{level} {group}.{table}: {type(exc).__name__}: {str(exc)[:180]}"

    count = result.count
    count_text = "?" if count is None else str(count)
    return True, f"OK {group}.{table}: rows={count_text}"


def main() -> int:
    failures = 0
    for group, table, columns, required in CHECKS:
        ok, message = _check_table(group, table, columns, required)
        print(message)
        if not ok:
            failures += 1

    if failures:
        print(f"supabase_state=needs_attention failures={failures}")
        return 1
    print("supabase_state=ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
