"""Detalle de la orden en el portal: avance por estados e historial.

Cubre las dos reglas que no pueden romperse:
  1. Una veterinaria nunca ve la orden de otra.
  2. El cliente nunca ve eventos internos (facturación, revisiones de alta).
"""
from app.portal.client_requests import (
    CLIENT_VISIBLE_EVENTS,
    REQUEST_STATUS_FLOW,
    build_status_progress,
    build_timeline,
)


# ── Avance por estados (ítem 23, reemplazo del GPS) ───────────────────────────

def test_progress_marks_previous_steps_as_done_and_current_as_current():
    progress = build_status_progress("picked_up")

    done = [s["key"] for s in progress if s["done"]]
    current = [s["key"] for s in progress if s["current"]]
    assert done == ["received", "assigned", "on_route"]
    assert current == ["picked_up"]
    # Lo que viene después no se marca todavía.
    assert all(not s["done"] and not s["current"] for s in progress if s["key"] == "sent")


def test_progress_on_first_and_last_step():
    first = build_status_progress("received")
    assert first[0]["current"] is True
    assert not any(s["done"] for s in first)

    last = build_status_progress("sent")
    assert last[-1]["current"] is True
    assert all(s["done"] for s in last[:-1])


def test_cancelled_and_error_states_have_no_progress_track():
    """No son un paso del recorrido: la vista los explica con un mensaje aparte."""
    assert build_status_progress("cancelled") == []
    assert build_status_progress("error_pending_assignment") == []


def test_unknown_status_shows_the_track_without_marking_anything():
    progress = build_status_progress("estado-que-no-existe")

    assert len(progress) == len(REQUEST_STATUS_FLOW)
    assert not any(s["done"] or s["current"] for s in progress)


# ── Historial (ítem 19) ───────────────────────────────────────────────────────

def test_timeline_hides_internal_events():
    """Facturación y revisiones de alta son internas: el cliente no las ve."""
    events = [
        {"event_type": "status_updated", "created_at": "2026-08-01T10:00:00",
         "event_payload": {"status": "in_lab"}},
        {"event_type": "alegra_failed", "created_at": "2026-08-01T09:00:00",
         "event_payload": {"reason": "cliente_sin_nit"}},
        {"event_type": "alegra_invoiced", "created_at": "2026-08-01T09:00:00",
         "event_payload": {"invoice_id": 42, "total": 90000}},
        {"event_type": "client_review_submitted", "created_at": "2026-08-01T08:00:00",
         "event_payload": {}},
        {"event_type": "created", "created_at": "2026-08-01T07:00:00", "event_payload": {}},
    ]

    timeline = build_timeline(events)

    assert [e["label"] for e in timeline] == ["Actualización de estado", "Solicitud registrada"]
    serialized = str(timeline)
    assert "alegra" not in serialized.lower()
    assert "42" not in serialized


def test_timeline_translates_status_to_client_language():
    timeline = build_timeline([
        {"event_type": "status_updated", "created_at": "2026-08-01T10:00:00",
         "event_payload": {"status": "in_lab"}},
    ])

    assert timeline[0]["status_label"] == "En laboratorio"


def test_timeline_tolerates_malformed_payloads():
    timeline = build_timeline([
        {"event_type": "status_updated", "created_at": "2026-08-01T10:00:00",
         "event_payload": None},
        {"event_type": "status_updated", "created_at": "2026-08-01T09:00:00",
         "event_payload": "texto suelto"},
        {"event_type": None, "created_at": "2026-08-01T08:00:00", "event_payload": {}},
    ])

    assert len(timeline) == 2
    assert all(e["status_label"] == "" for e in timeline)


def test_visible_events_is_an_allow_list():
    """Un evento nuevo debe ser invisible hasta que se decida mostrarlo."""
    assert build_timeline([
        {"event_type": "un_evento_nuevo", "created_at": "2026-08-01T10:00:00",
         "event_payload": {"dato": "interno"}},
    ]) == []
    assert set(CLIENT_VISIBLE_EVENTS) == {"created", "status_updated"}
