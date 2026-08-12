import hmac
from collections import Counter
from functools import wraps

from flask import Blueprint, jsonify, request

from app.config import PLATFORM_API_TOKEN
from app.services import db

platform_api = Blueprint("platform_api", __name__)

VALID_REQUEST_STATUSES = {
    "received", "assigned", "on_route", "picked_up", "in_lab",
    "processed", "sent", "error_pending_assignment", "cancelled",
}

FLOW_STAGE_ORDER = {
    "fase_0_bienvenida": 0, "fase_1_clasificacion": 1, "fase_2_recogida_datos": 2,
    "fase_3_validacion": 3, "fase_4_confirmacion": 4, "fase_5_ejecucion": 5,
    "fase_6_cierre": 6, "fase_7_escalado": 7,
}


def _auth_required(route_fn):
    """Exige X-Platform-Token en todas las rutas de la API interna.

    Fail-closed: sin PLATFORM_API_TOKEN configurado la API queda CERRADA. Antes
    dejaba pasar cuando la variable estaba vacía, y como no estaba definida en el
    entorno la API quedó sirviendo NIT, teléfono y dirección de los clientes sin
    credenciales (hallazgo H1 de tasks/qa-e2e-2026-07-28.md).
    """
    @wraps(route_fn)
    def wrapped(*args, **kwargs):
        if not PLATFORM_API_TOKEN:
            return jsonify({"error": "platform_api_not_configured"}), 503
        token = request.headers.get("X-Platform-Token", "")
        if not hmac.compare_digest(token, PLATFORM_API_TOKEN):
            return jsonify({"error": "unauthorized"}), 401
        return route_fn(*args, **kwargs)

    return wrapped


def _parse_limit(param_name: str, default: int) -> int:
    raw = request.args.get(param_name, str(default))
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(1, min(value, 2000))


def _assignment_from_client(client: dict) -> dict | None:
    assignment = client.get("client_courier_assignment")
    if isinstance(assignment, list):
        return assignment[0] if assignment else None
    if isinstance(assignment, dict):
        return assignment
    return None


def _request_is_unassigned(row: dict) -> bool:
    if row.get("status") == "error_pending_assignment":
        return True
    if row.get("status") != "received":
        return False
    if row.get("service_area") != "route_scheduling":
        return False
    return not row.get("assigned_courier_id")


@platform_api.route("/api/platform/overview", methods=["GET"])
@_auth_required
def platform_overview():
    clients = db.list_clients_with_assignment(limit=_parse_limit("clients_limit", 500))
    requests_rows = db.list_requests(limit=_parse_limit("requests_limit", 500))
    sessions = db.list_sessions(limit=_parse_limit("sessions_limit", 500))

    with_courier = 0
    for client in clients:
        assignment = _assignment_from_client(client)
        if assignment and assignment.get("courier_id"):
            with_courier += 1

    status_counter = Counter((row.get("status") or "unknown") for row in requests_rows)
    area_counter = Counter((row.get("service_area") or "unknown") for row in requests_rows)
    phase_counter = Counter((row.get("phase_current") or "sin_etapa") for row in sessions)

    active_statuses = {
        "received", "assigned", "on_route", "picked_up", "in_lab", "processed", "error_pending_assignment",
    }
    active_requests = sum(1 for row in requests_rows if (row.get("status") or "") in active_statuses)
    unassigned_rows = [row for row in requests_rows if _request_is_unassigned(row)]

    flow_stage_counts = []
    for stage_key, count in phase_counter.items():
        flow_stage_counts.append(
            {
                "stage_key": stage_key,
                "count": count,
                "order": FLOW_STAGE_ORDER.get(stage_key, 999),
            }
        )
    flow_stage_counts.sort(key=lambda row: (row["order"], row["stage_key"]))

    return jsonify({
        "summary": {
            "total_clients": len(clients),
            "clients_with_courier": with_courier,
            "clients_without_courier": max(len(clients) - with_courier, 0),
            "active_requests": active_requests,
            "unassigned_requests": len(unassigned_rows),
            "sessions_tracked": len(sessions),
        },
        "requests_by_status": dict(status_counter),
        "service_area_counts": dict(area_counter),
        "flow_stage_counts": flow_stage_counts,
        "unassigned_request_rows": [
            {
                "id": row.get("id"),
                "clinic_name": (row.get("clients") or {}).get("clinic_name"),
                "status": row.get("status"),
                "fallback_reason": row.get("fallback_reason"),
                "scheduled_pickup_date": row.get("scheduled_pickup_date"),
            }
            for row in unassigned_rows[:50]
        ],
    })


@platform_api.route("/api/platform/clients", methods=["GET"])
@_auth_required
def platform_clients():
    only_without_courier = request.args.get("only_without_courier", "false").lower() == "true"
    rows = db.list_clients_with_assignment(limit=_parse_limit("limit", 500))

    clients = []
    for row in rows:
        assignment = _assignment_from_client(row)
        courier = (assignment or {}).get("couriers") or {}
        has_courier = bool((assignment or {}).get("courier_id"))
        if only_without_courier and has_courier:
            continue

        clients.append({
            "id": row.get("id"),
            "clinic_name": row.get("clinic_name"),
            "tax_id": row.get("tax_id"),
            "phone": row.get("phone"),
            "address": row.get("address"),
            "zone": row.get("zone"),
            "billing_type": row.get("billing_type"),
            "is_active": row.get("is_active"),
            "has_assigned_courier": has_courier,
            "courier": {
                "id": courier.get("id"),
                "name": courier.get("name"),
                "phone": courier.get("phone"),
                "availability": courier.get("availability"),
            } if has_courier else None,
        })

    return jsonify({"count": len(clients), "rows": clients})


@platform_api.route("/api/platform/requests", methods=["GET"])
@_auth_required
def platform_requests():
    status = (request.args.get("status") or "").strip()
    if status and status not in VALID_REQUEST_STATUSES:
        return jsonify({"error": "invalid_status"}), 400

    rows = db.list_requests(limit=_parse_limit("limit", 500), status=status or None)
    return jsonify({"count": len(rows), "rows": rows})


@platform_api.route("/api/platform/requests/unassigned", methods=["GET"])
@_auth_required
def platform_unassigned_requests():
    rows = db.list_requests(limit=_parse_limit("limit", 500))
    unassigned = [row for row in rows if _request_is_unassigned(row)]
    return jsonify({"count": len(unassigned), "rows": unassigned})


@platform_api.route("/api/platform/requests/<request_id>/events", methods=["GET"])
@_auth_required
def platform_request_events(request_id: str):
    rows = db.list_request_events(request_id, limit=_parse_limit("limit", 50))
    return jsonify({"count": len(rows), "rows": rows})


@platform_api.route("/api/platform/requests/<uuid:request_id>/status", methods=["PATCH"])
@_auth_required
def platform_update_request_status(request_id: str):
    payload = request.get_json(force=True, silent=True) or {}
    status = (payload.get("status") or "").strip()
    if status not in VALID_REQUEST_STATUSES:
        return jsonify({"error": "invalid_status"}), 400

    updated = db.update_request_status(
        request_id=str(request_id),
        status=status,
        assigned_courier_id=payload.get("assigned_courier_id"),
        fallback_reason=payload.get("fallback_reason"),
    )
    if not updated:
        return jsonify({"error": "request_not_found"}), 404
    return jsonify({"ok": True, "request": updated})
