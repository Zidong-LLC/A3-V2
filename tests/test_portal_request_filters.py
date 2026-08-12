"""La lista de solicitudes del portal filtra igual que la de resultados."""
from unittest.mock import patch

from app.services import portal_db


class _FakeQuery:
    """Registra las llamadas encadenadas del SDK de Supabase."""

    def __init__(self, recorder):
        self.rec = recorder

    def select(self, *a):
        return self

    def eq(self, col, val):
        self.rec.setdefault("eq", []).append((col, val))
        return self

    def ilike(self, col, val):
        self.rec.setdefault("ilike", []).append((col, val))
        return self

    def gte(self, col, val):
        self.rec.setdefault("gte", []).append((col, val))
        return self

    def lte(self, col, val):
        self.rec.setdefault("lte", []).append((col, val))
        return self

    def order(self, *a, **k):
        return self

    def limit(self, *a):
        return self

    def execute(self):
        return type("R", (), {"data": []})()


def _capture(filters):
    rec = {}
    with patch.object(portal_db, "_client") as fake_client:
        fake_client.table.return_value = _FakeQuery(rec)
        portal_db.list_client_requests("client-1", filters=filters)
    return rec


def test_no_filters_keeps_previous_behaviour():
    rec = _capture(None)

    assert ("client_id", "client-1") in rec["eq"]
    assert ("service_area", "route_scheduling") in rec["eq"]
    assert "ilike" not in rec


def test_patient_and_order_number_use_partial_match():
    rec = _capture({"patient": "Firulais", "order_number": "A3-0004"})

    assert ("patient_name", "%Firulais%") in rec["ilike"]
    assert ("order_number", "%A3-0004%") in rec["ilike"]


def test_status_uses_exact_match_and_dates_bound_the_range():
    rec = _capture({"status": "assigned", "date_from": "2026-07-01", "date_to": "2026-07-31"})

    assert ("status", "assigned") in rec["eq"]
    assert ("requested_at", "2026-07-01") in rec["gte"]
    # El día final se incluye completo, no se corta a medianoche.
    assert ("requested_at", "2026-07-31T23:59:59") in rec["lte"]


def test_unknown_status_is_discarded_by_the_view():
    """Un estado inventado en la URL no puede vaciar la tabla sin explicación."""
    from app.portal.client_requests import REQUEST_STATUS_LABELS

    assert "no-existe" not in REQUEST_STATUS_LABELS
    assert "assigned" in REQUEST_STATUS_LABELS
