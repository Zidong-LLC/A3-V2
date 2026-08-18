"""TAT y tendencias del Panel Ejecutivo (Fase 4 plataforma) — módulo puro."""
from datetime import datetime, timezone

from app.dashboard_metrics import build_tat_and_trends

NOW = datetime(2026, 8, 18, 12, 0, tzinfo=timezone.utc)


def _req(rid, requested_at):
    return {"id": rid, "requested_at": requested_at, "status": "processed"}


def _ev(rid, created_at, status, event_type="dashboard_status_update"):
    return {"request_id": rid, "event_type": event_type,
            "event_payload": {"status": status}, "created_at": created_at}


def test_tat_from_creation_to_first_processed_event():
    result = build_tat_and_trends(
        [_req("r1", "2026-08-17T10:00:00+00:00")],
        [_ev("r1", "2026-08-18T10:00:00+00:00", "processed")],
        now=NOW,
    )
    assert result["exec_tat_avg_hours"] == 24.0
    assert result["exec_tat_count"] == 1


def test_sent_also_closes_the_cycle_via_status_updated():
    result = build_tat_and_trends(
        [_req("r1", "2026-08-18T00:00:00+00:00")],
        [_ev("r1", "2026-08-18T06:00:00+00:00", "sent", event_type="status_updated")],
        now=NOW,
    )
    assert result["exec_tat_avg_hours"] == 6.0


def test_request_without_terminal_event_is_excluded():
    result = build_tat_and_trends(
        [_req("r1", "2026-08-18T00:00:00+00:00")],
        [_ev("r1", "2026-08-18T01:00:00+00:00", "in_lab")],
        now=NOW,
    )
    assert result["exec_tat_avg_hours"] is None
    assert result["exec_tat_count"] == 0
    # Pero la etapa intermedia sí se mide.
    assert result["exec_tat_stages"][0]["status"] == "in_lab"
    assert result["exec_tat_stages"][0]["avg_hours"] == 1.0


def test_unordered_events_use_the_first_terminal():
    result = build_tat_and_trends(
        [_req("r1", "2026-08-18T00:00:00+00:00")],
        [
            _ev("r1", "2026-08-18T08:00:00+00:00", "sent"),
            _ev("r1", "2026-08-18T04:00:00+00:00", "processed"),
        ],
        now=NOW,
    )
    assert result["exec_tat_avg_hours"] == 4.0


def test_other_event_types_are_ignored():
    result = build_tat_and_trends(
        [_req("r1", "2026-08-18T00:00:00+00:00")],
        [_ev("r1", "2026-08-18T02:00:00+00:00", "processed", event_type="alegra_invoiced")],
        now=NOW,
    )
    assert result["exec_tat_count"] == 0


def test_daily_series_fills_30_days_with_zeros():
    result = build_tat_and_trends(
        [_req("r1", "2026-08-18T01:00:00+00:00"), _req("r2", "2026-08-18T02:00:00+00:00")],
        [],
        now=NOW,
    )
    daily = result["exec_requests_daily"]
    assert len(daily) == 30
    assert daily[-1] == {"date": "2026-08-18", "count": 2}
    assert all(d["count"] == 0 for d in daily[:-1])


def test_weekly_tat_averages_by_iso_week():
    result = build_tat_and_trends(
        [_req("r1", "2026-08-17T00:00:00+00:00"), _req("r2", "2026-08-17T00:00:00+00:00")],
        [
            _ev("r1", "2026-08-17T10:00:00+00:00", "processed"),
            _ev("r2", "2026-08-17T20:00:00+00:00", "processed"),
        ],
        now=NOW,
    )
    assert result["exec_tat_weekly"] == [{"week": "2026-W34", "avg_hours": 15.0}]


def test_empty_rows_return_defaults_without_division_by_zero():
    result = build_tat_and_trends([], [], now=NOW)
    assert result["exec_tat_avg_hours"] is None
    assert result["exec_tat_count"] == 0
    assert result["exec_tat_stages"] == []
    assert len(result["exec_requests_daily"]) == 30
    assert result["exec_tat_weekly"] == []


def test_column_prefs_accepts_visible_and_order():
    """Server-side del bugfix de savePrefs: visible + order → 200."""
    import app.dashboard as dash
    from app.main import app

    app.config["TESTING"] = True
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["dashboard_authenticated"] = True
        sess["dashboard_username"] = "tester"
    saved = {}

    def fake_upsert(user_key, table_id, prefs):
        saved[table_id] = prefs

    import pytest as _pytest

    mp = _pytest.MonkeyPatch()
    mp.setattr(dash.db, "upsert_column_prefs", fake_upsert)
    try:
        response = client.post(
            "/api/dashboard/column-prefs",
            json={"table_id": "exec_widgets", "prefs": {"visible": ["tat"], "order": ["tat"]}},
        )
        assert response.status_code == 200
        assert saved["exec_widgets"]["visible"] == ["tat"]
    finally:
        mp.undo()
