"""Asignación automática de motorizado por zona (Fase 2 plataforma).

resolve_zone_courier se prueba PURO contra el CSV territorial real; la
persistencia (_auto_assign_courier) y el enganche en create_request se prueban
con monkeypatch sobre db, patrón de tests/test_db_identification.py.
"""
from types import SimpleNamespace

from app import zone_routing
from app.services import db

ZONE_ROWS_ALL = [{"zone_number": n, "courier_id": f"zone-{n}"} for n in range(1, 9)]


# ── resolve_zone_courier (puro) ───────────────────────────────────────────────

def test_locality_text_resolves_via_manual_coverage_first():
    result = zone_routing.resolve_zone_courier(
        address=None,
        zone_text="Suba",
        coverage_rows=[{"locality_code": "suba", "courier_id": "cov-1"}],
        zone_rows=ZONE_ROWS_ALL,
    )
    assert result["courier_id"] == "cov-1"
    assert result["source"] == "coverage"
    assert result["locality_code"] == "suba"


def test_locality_without_coverage_falls_back_to_zone_courier():
    result = zone_routing.resolve_zone_courier(
        address=None, zone_text="Suba", coverage_rows=[], zone_rows=ZONE_ROWS_ALL
    )
    assert result["source"] == "zone"
    assert result["courier_id"] == f"zone-{result['zone_number']}"


def test_neighborhood_inside_address_resolves_zone():
    result = zone_routing.resolve_zone_courier(
        address="Carrera 10, barrio La Academia",
        zone_text=None,
        coverage_rows=[],
        zone_rows=ZONE_ROWS_ALL,
    )
    assert result["zone_number"] == 5
    assert result["courier_id"] == "zone-5"


def test_zone_number_as_text_resolves():
    result = zone_routing.resolve_zone_courier(
        address=None, zone_text="5", coverage_rows=[], zone_rows=ZONE_ROWS_ALL
    )
    assert result["zone_number"] == 5
    assert result["courier_id"] == "zone-5"


def test_unrecognizable_location_returns_none():
    result = zone_routing.resolve_zone_courier(
        address="xyz", zone_text="???", coverage_rows=[], zone_rows=ZONE_ROWS_ALL
    )
    assert result is None


def test_zone_without_courier_in_rows_returns_none():
    result = zone_routing.resolve_zone_courier(
        address=None, zone_text="Suba", coverage_rows=[], zone_rows=[]
    )
    assert result is None


# ── _auto_assign_courier (persistencia) ───────────────────────────────────────

def _patch_common(monkeypatch, client, upserts):
    monkeypatch.setattr(db, "get_client_by_id", lambda client_id: client)
    monkeypatch.setattr(db, "list_courier_locality_coverage", lambda: [])
    monkeypatch.setattr(db, "list_territorial_zones", lambda: ZONE_ROWS_ALL)
    monkeypatch.setattr(
        db, "upsert_client_assignment",
        lambda client_id, courier_id, assigned_by: upserts.append((client_id, courier_id, assigned_by)),
    )
    monkeypatch.setattr(db, "get_courier_for_client", lambda client_id: {"id": upserts[-1][1]} if upserts else None)


def test_auto_assign_resolves_and_persists_auto_zone(monkeypatch):
    upserts = []
    client = {"id": "cl-1", "address": "Carrera 10, barrio La Academia", "zone": None}
    _patch_common(monkeypatch, client, upserts)

    courier = db._auto_assign_courier("cl-1")

    assert upserts == [("cl-1", "zone-5", "auto_zone")]
    assert courier == {"id": "zone-5"}


def test_auto_assign_unresolvable_returns_none_without_upsert(monkeypatch):
    upserts = []
    client = {"id": "cl-1", "address": "xyz", "zone": None}
    _patch_common(monkeypatch, client, upserts)

    assert db._auto_assign_courier("cl-1") is None
    assert upserts == []


def test_auto_assign_missing_client_returns_none(monkeypatch):
    monkeypatch.setattr(db, "get_client_by_id", lambda client_id: None)
    assert db._auto_assign_courier("cl-x") is None


def test_auto_assign_swallows_internal_errors(monkeypatch):
    client = {"id": "cl-1", "address": "Carrera 10, barrio La Academia", "zone": None}
    monkeypatch.setattr(db, "get_client_by_id", lambda client_id: client)

    def boom():
        raise RuntimeError("supabase caído")

    monkeypatch.setattr(db, "list_courier_locality_coverage", boom)
    assert db._auto_assign_courier("cl-1") is None


# ── Enganche en create_request ────────────────────────────────────────────────

def _fake_supabase(monkeypatch, inserted_requests):
    class FakeQuery:
        def __init__(self, table_name):
            self.table_name = table_name

        def insert(self, payload):
            self.payload = payload
            return self

        def execute(self):
            if self.table_name == "requests":
                inserted_requests.append(self.payload)
                return SimpleNamespace(data=[{"id": "req-1"}])
            return SimpleNamespace(data=[self.payload])

    class FakeClient:
        def table(self, table_name):
            return FakeQuery(table_name)

    monkeypatch.setattr(db, "_client", FakeClient())
    monkeypatch.setattr(db, "get_tests_by_codes_or_names", lambda items: [])


def _create_route_request():
    return db.create_request(
        "chat-1",
        {"client_id": "cl-1", "channel": "telegram"},
        {"intent": "route_scheduling", "handoff_area": None,
         "captured_fields": {"exam_type": "Hemograma", "pickup_address": "Calle 1"}},
    )


def test_create_request_uses_auto_assignment_when_no_client_assignment(monkeypatch):
    inserted = []
    _fake_supabase(monkeypatch, inserted)
    monkeypatch.setattr(db, "get_courier_for_client", lambda client_id: None)
    monkeypatch.setattr(db, "_auto_assign_courier", lambda client_id: {"id": "zone-5"})

    assert _create_route_request() is not None
    assert inserted[0]["status"] == "assigned"
    assert inserted[0]["assigned_courier_id"] == "zone-5"


def test_create_request_escalates_when_zone_unresolvable(monkeypatch):
    inserted = []
    _fake_supabase(monkeypatch, inserted)
    monkeypatch.setattr(db, "get_courier_for_client", lambda client_id: None)
    monkeypatch.setattr(db, "_auto_assign_courier", lambda client_id: None)

    assert _create_route_request() is not None
    assert inserted[0]["status"] == "error_pending_assignment"
    assert inserted[0]["fallback_reason"] == "no_courier_assigned"


def test_create_request_skips_auto_assignment_when_client_has_courier(monkeypatch):
    inserted = []
    calls = []
    _fake_supabase(monkeypatch, inserted)
    monkeypatch.setattr(db, "get_courier_for_client", lambda client_id: {"id": "manual-1"})
    monkeypatch.setattr(db, "_auto_assign_courier", lambda client_id: calls.append(client_id))

    assert _create_route_request() is not None
    assert inserted[0]["assigned_courier_id"] == "manual-1"
    assert calls == []
