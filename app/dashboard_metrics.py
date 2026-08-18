"""TAT y tendencias del Panel Ejecutivo — puro, sin queries.

Recibe las filas que build_dashboard_context YA carga en memoria (requests y
request_events, límite 4000 eventos: la métrica es operativa y reciente; con
historial muy largo las solicitudes viejas pueden quedar sin eventos y se
excluyen del promedio — exec_tat_count lo transparenta).

`requests` no tiene timestamps por transición (solo requested_at): el TAT sale
de request_events.created_at, con los event_types que escriben estado
(status_updated / dashboard_status_update).
"""
from collections import defaultdict
from datetime import datetime, timedelta, timezone

_STATUS_EVENT_TYPES = {"status_updated", "dashboard_status_update"}
_TERMINAL_STATUSES = {"processed", "sent"}
_STAGE_LABELS = {
    "assigned": "Asignada",
    "on_route": "En ruta",
    "picked_up": "Recogida",
    "in_lab": "En laboratorio",
    "processed": "Procesada",
    "sent": "Enviada",
}


def _parse_ts(value) -> datetime | None:
    if not value:
        return None
    try:
        ts = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)


def _status_events_by_request(request_events: list[dict]) -> dict[str, list[tuple[datetime, str]]]:
    by_request: dict[str, list[tuple[datetime, str]]] = defaultdict(list)
    for ev in request_events or []:
        if ev.get("event_type") not in _STATUS_EVENT_TYPES:
            continue
        payload = ev.get("event_payload") if isinstance(ev.get("event_payload"), dict) else {}
        status = str(payload.get("status") or "").strip()
        ts = _parse_ts(ev.get("created_at"))
        if status and ts and ev.get("request_id"):
            by_request[ev["request_id"]].append((ts, status))
    for events in by_request.values():
        events.sort(key=lambda item: item[0])
    return by_request


def build_tat_and_trends(requests_rows: list[dict], request_events: list[dict], now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    events_by_request = _status_events_by_request(request_events)

    tat_hours: list[float] = []
    weekly_acc: dict[str, list[float]] = defaultdict(list)
    stage_acc: dict[str, list[float]] = defaultdict(list)
    daily_counts: dict[str, int] = defaultdict(int)

    for row in requests_rows or []:
        requested_at = _parse_ts(row.get("requested_at"))
        if requested_at:
            daily_counts[requested_at.date().isoformat()] += 1
        events = events_by_request.get(row.get("id"), [])
        if not requested_at or not events:
            continue

        # Etapas: delta entre el evento anterior (o la creación) y cada estado.
        prev_ts = requested_at
        for ts, status in events:
            delta_h = (ts - prev_ts).total_seconds() / 3600
            if status in _STAGE_LABELS and delta_h >= 0:
                stage_acc[status].append(delta_h)
            prev_ts = ts

        # TAT: creación → PRIMER evento terminal (processed o sent).
        terminal = next(((ts, st) for ts, st in events if st in _TERMINAL_STATUSES), None)
        if terminal:
            hours = (terminal[0] - requested_at).total_seconds() / 3600
            if hours >= 0:
                tat_hours.append(hours)
                iso = terminal[0].isocalendar()
                weekly_acc[f"{iso.year}-W{iso.week:02d}"].append(hours)

    stages = [
        {"status": status, "label": _STAGE_LABELS[status],
         "avg_hours": round(sum(vals) / len(vals), 1), "count": len(vals)}
        for status, vals in ((s, stage_acc[s]) for s in _STAGE_LABELS) if vals
    ]
    max_stage = max((st["avg_hours"] for st in stages), default=0) or 1
    for st in stages:
        st["width"] = int(round(st["avg_hours"] / max_stage * 100))

    daily = []
    for offset in range(29, -1, -1):
        day = (now - timedelta(days=offset)).date().isoformat()
        daily.append({"date": day, "count": daily_counts.get(day, 0)})

    weekly = [
        {"week": week, "avg_hours": round(sum(vals) / len(vals), 1)}
        for week, vals in sorted(weekly_acc.items())[-8:]
    ]

    return {
        "exec_tat_avg_hours": round(sum(tat_hours) / len(tat_hours), 1) if tat_hours else None,
        "exec_tat_count": len(tat_hours),
        "exec_tat_stages": stages,
        "exec_requests_daily": daily,
        "exec_tat_weekly": weekly,
    }
