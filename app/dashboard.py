import hashlib
import json as _json
import math
import re
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from functools import wraps

from flask import Blueprint, abort, jsonify, redirect, render_template, request, session, url_for

from app.config import DASHBOARD_ADMIN_PASSWORD, DASHBOARD_ADMIN_USER
from app.services import db
from app import territory

dashboard = Blueprint("dashboard", __name__)

FLOW_STAGES = [
    ("fase_0_bienvenida", "Bienvenida"),
    ("fase_1_clasificacion", "Clasificacion"),
    ("fase_2_recogida_datos", "Recogida de datos"),
    ("fase_3_validacion", "Validacion"),
    ("fase_4_confirmacion", "Confirmacion"),
    ("fase_5_ejecucion", "Ejecucion"),
    ("fase_6_cierre", "Cierre"),
    ("fase_7_escalado", "Escalado humano"),
]

BOGOTA_LOCALITIES = [
    {"code": "usaquen", "name": "Usaquen"},
    {"code": "chapinero", "name": "Chapinero"},
    {"code": "santa_fe", "name": "Santa Fe"},
    {"code": "san_cristobal", "name": "San Cristobal"},
    {"code": "usme", "name": "Usme"},
    {"code": "tunjuelito", "name": "Tunjuelito"},
    {"code": "bosa", "name": "Bosa"},
    {"code": "kennedy", "name": "Kennedy"},
    {"code": "fontibon", "name": "Fontibon"},
    {"code": "engativa", "name": "Engativa"},
    {"code": "suba", "name": "Suba"},
    {"code": "barrios_unidos", "name": "Barrios Unidos"},
    {"code": "teusaquillo", "name": "Teusaquillo"},
    {"code": "los_martires", "name": "Los Martires"},
    {"code": "antonio_narino", "name": "Antonio Narino"},
    {"code": "puente_aranda", "name": "Puente Aranda"},
    {"code": "la_candelaria", "name": "La Candelaria"},
    {"code": "rafael_uribe_uribe", "name": "Rafael Uribe Uribe"},
    {"code": "ciudad_bolivar", "name": "Ciudad Bolivar"},
    {"code": "sumapaz", "name": "Sumapaz"},
]
BOGOTA_LOCALITIES_BY_CODE = {row["code"]: row for row in BOGOTA_LOCALITIES}
BOGOTA_LOCALITY_COORDS = {
    "usaquen": (4.7059, -74.0308), "chapinero": (4.6486, -74.0628), "santa_fe": (4.6036, -74.0724),
    "san_cristobal": (4.5685, -74.0831), "usme": (4.4774, -74.1178), "tunjuelito": (4.5804, -74.1305),
    "bosa": (4.6158, -74.1946), "kennedy": (4.6267, -74.1512), "fontibon": (4.6784, -74.1425),
    "engativa": (4.6953, -74.1129), "suba": (4.7473, -74.0842), "barrios_unidos": (4.6694, -74.0742),
    "teusaquillo": (4.6387, -74.0918), "los_martires": (4.6038, -74.0911), "antonio_narino": (4.5894, -74.1019),
    "puente_aranda": (4.6169, -74.1083), "la_candelaria": (4.5962, -74.0733), "rafael_uribe_uribe": (4.5653, -74.1065),
    "ciudad_bolivar": (4.5307, -74.1525), "sumapaz": (4.2503, -74.2834),
}
LOCALITIES_GEOJSON_URL = "https://raw.githubusercontent.com/codeforgermany/click_that_hood/main/public/data/bogota-localidades.geojson"
COURIER_COLOR_PALETTE = ["#f97316", "#0ea5e9", "#22c55e", "#eab308", "#ec4899", "#a855f7", "#14b8a6", "#f43f5e"]
COURIER_DEFAULT_COLORS = {
    "Javier": "#f97316",
    "Jeeferson": "#0ea5e9",
    "Diego": "#22c55e",
    "Luis": "#eab308",
    "Gerardo": "#ec4899",
    "Alexander": "#a855f7",
    "Marlon": "#14b8a6",
    "Cesar": "#f43f5e",
}
CLIENT_TYPE_OPTIONS = {"es_persona": "Es Persona", "empresa": "Empresa", "otro": "Otro"}
VAT_REGIME_OPTIONS = {"no_responsable_iva": "No responsable de IVA", "responsable_iva": "Responsable de IVA"}
REQUEST_PRIORITY_LABELS = {"normal": "Normal", "high": "Alta", "urgent": "Urgente"}
REQUEST_PRIORITY_DB_MAP = {"normal": "normal", "high": "urgent", "urgent": "urgent"}
REQUEST_STATUS_LABELS = {
    "received": "Recibida",
    "assigned": "Asignada",
    "on_route": "En ruta",
    "picked_up": "Retirada",
    "in_lab": "En laboratorio",
    "processed": "Procesada",
    "sent": "Enviada",
    "cancelled": "Cancelada",
    "error_pending_assignment": "Sin motorizado",
}
PAYMENT_METHOD_LABELS = {
    "contraentrega": "Contra entrega",
    "pago_linea": "Pago en línea",
}
SAMPLE_STATUS_LABELS = {
    "pending_pickup": "A retirar",
    "picked_up": "Recogida y en camino",
    "on_route": "Recogida y en camino",
    "received_lab": "Recibida laboratorio",
    "in_lab": "En analisis",
    "processed": "Analizados resultados listos",
    "ready_results": "Analizados resultados listos",
    "sent": "Enviada",
}
SAMPLE_STATUS_DB_OPTIONS = {"pending_pickup", "picked_up", "on_route", "received_lab", "in_lab"}
SAMPLE_STATUS_DB_FALLBACK = {"processed": "in_lab", "ready_results": "in_lab", "sent": "in_lab"}
SAMPLE_STATUS_DROPDOWN = [
    {"value": "pending_pickup", "label": "A retirar"},
    {"value": "picked_up", "label": "Recogida y en camino"},
    {"value": "received_lab", "label": "Recibida laboratorio"},
    {"value": "in_lab", "label": "En analisis"},
    {"value": "processed", "label": "Analizados resultados listos"},
    {"value": "sent", "label": "Enviada"},
]
_DROPDOWN_STATUS_MAP = {"on_route": "picked_up", "ready_results": "processed"}
SAMPLE_PROCESS_STAGES = [
    ("pending_pickup", "A retirar"),
    ("picked_up", "Recogida y en camino"),
    ("received_lab", "Recibida laboratorio"),
    ("in_lab", "En analisis"),
    ("processed", "Analizados resultados listos"),
    ("sent", "Enviada"),
]


def _login_required(view_func):
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if not session.get("dashboard_authenticated"):
            return redirect(url_for("dashboard.login"))
        return view_func(*args, **kwargs)

    return wrapped


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
    return (
        row.get("status") == "received"
        and row.get("service_area") == "route_scheduling"
        and not row.get("assigned_courier_id")
    )


def _empty_context(error: str | None = None) -> dict:
    return {
        "summary": {
            "total_clients": 0,
            "clients_with_courier": 0,
            "clients_without_courier": 0,
            "active_requests": 0,
            "unassigned_requests": 0,
            "sessions_tracked": 0,
            "pending_pickup": 0,
            "total_samples": 0,
            "catalog_tests": 0,
            "pending_manual_approvals": 0,
        },
        "request_status": {},
        "sample_status": {},
        "requests_by_status": {},
        "service_area_counts": {},
        "flow_stage_counts": [],
        "flow_kanban_lanes": [],
        "unassigned_request_rows": [],
        "clients": [],
        "requests": [],
        "sessions": [],
        "messages": [],
        "samples": [],
        "sample_process_lanes": [],
        "service_order_rows": [],
        "demo_mode": False,
        "sample_demo_total": 0,
        "clients_rows": [],
        "catalog_rows": [],
        "profile_catalog_rows": [],
        "profile_analysis_rows": [],
        "profile_builder_items": [],
        "custom_profiles": [],
        "profile_categories": [],
        "profile_species": [],
        "sample_requirements": [],
        "approval_rows": [],
        "reviewed_approval_rows": [],
        "affiliation_rows": [],
        "client_type_options": CLIENT_TYPE_OPTIONS,
        "vat_regime_options": VAT_REGIME_OPTIONS,
        "request_priority_options": [{"value": key, "label": value} for key, value in REQUEST_PRIORITY_LABELS.items()],
        "request_status_options": [{"value": key, "label": value} for key, value in REQUEST_STATUS_LABELS.items()],
        "sample_status_options": list(SAMPLE_STATUS_DROPDOWN),
        "sample_type_options": [],
        "sample_placeholder_rows": [],
        "sample_placeholder_status": {},
        "knowledge_profile_compat_mode": False,
        "couriers_options": [],
        "couriers_rows": [],
        "localities_rows": [],
        "motorizados_summary": {
            "coverage_rate": 0,
            "assigned_localities": 0,
            "total_localities": len(BOGOTA_LOCALITIES),
            "clients_in_assigned_localities": 0,
            "clients_in_catalog_localities": 0,
            "clients_in_unassigned_localities": 0,
            "localities_with_clients_without_coverage": 0,
            "busiest_courier_name": "Sin datos",
            "busiest_courier_clients": 0,
        },
        "motorizados_alerts": [],
        "coverage_map_points": [],
        "territorial_zone_rows": [],
        "territorial_locality_rows": [],
        "localities_geojson_url": LOCALITIES_GEOJSON_URL,
        "error": error,
    }


def _safe_fetch(fetcher, default):
    try:
        return fetcher()
    except Exception:
        return default


def _normalize_lookup_key(value: str | None) -> str:
    text = (value or "").strip().lower()
    text = text.translate(str.maketrans("áéíóúüñ", "aeiouun"))
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


def _normalize_phone(value: str | None) -> str:
    return re.sub(r"\D+", "", value or "")


def _normalize_locality_code(value: str | None) -> str:
    return _normalize_lookup_key(value)


def _normalize_status(value) -> str:
    return str(value or "").strip().lower()


def _normalize_priority(value) -> str:
    normalized = _normalize_lookup_key(str(value or ""))
    if normalized in {"normal", "estandar", "media", "baja"}:
        return "normal"
    if normalized in {"alta", "high"}:
        return "high"
    if normalized in {"urgente", "urgent", "critica"}:
        return "urgent"
    return normalized if normalized in REQUEST_PRIORITY_LABELS else ""


def _normalize_priority_db(priority: str) -> str:
    return REQUEST_PRIORITY_DB_MAP.get(priority, "normal")


def _normalize_sample_count(value) -> int | None:
    text = str(value or "").strip()
    if not re.fullmatch(r"\d{1,3}", text):
        return None
    return int(text)


def _sanitize_text(value, max_length: int = 180) -> str:
    text = " ".join(str(value or "").strip().split())
    return text[:max_length].strip()


def _normalize_sample_types(value) -> list[str]:
    raw_items = value if isinstance(value, list) else re.split(r"[;,]", str(value or ""))
    seen = set()
    cleaned = []
    for item in raw_items:
        text = _sanitize_text(item, 80)
        key = _normalize_lookup_key(text)
        if text and key not in seen:
            cleaned.append(text)
            seen.add(key)
    return cleaned[:12]


def _normalize_uuid(value) -> str:
    text = str(value or "").strip().lower()
    if re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}", text):
        return text
    return ""


def _sample_status_db_value(status: str) -> str:
    return status if status in SAMPLE_STATUS_DB_OPTIONS else SAMPLE_STATUS_DB_FALLBACK.get(status, "pending_pickup")


def _courier_color(courier_id: str, courier_name: str | None = None) -> str:
    if courier_name and courier_name in COURIER_DEFAULT_COLORS:
        return COURIER_DEFAULT_COLORS[courier_name]
    if not courier_id:
        return "#475569"
    index = int(hashlib.sha1(courier_id.encode("utf-8")).hexdigest()[:4], 16) % len(COURIER_COLOR_PALETTE)
    return COURIER_COLOR_PALETTE[index]


def _resolve_locality(zone: str | None) -> dict | None:
    zone_key = _normalize_lookup_key(zone)
    for locality in BOGOTA_LOCALITIES:
        if zone_key == locality["code"] or zone_key == _normalize_lookup_key(locality["name"]):
            return locality
    zone_str = str(zone or "").strip()
    zone_num = re.sub(r"\.\d+$", "", zone_str)
    if zone_num.isdigit():
        zone_number = int(zone_num)
        for locality_tuple in territory.ZONE_LOCALITIES.get(zone_number, []):
            return {"code": locality_tuple[0], "name": locality_tuple[1]}
    return None


def _resolve_zone_display(zone: str | None) -> str:
    raw = str(zone or "").strip()
    if not raw or raw.lower() == "no aplica":
        return "Sin zona"
    zone_num = re.sub(r"\.\d+$", "", raw)
    if zone_num.isdigit():
        return f"Zona {int(zone_num)}"
    locality = _resolve_locality(raw)
    if locality:
        return locality["name"]
    return raw


def _format_turnaround_label(_: dict) -> str:
    return "Por definir"


def _bool_option(value) -> str:
    if value is True:
        return "si"
    if value is False:
        return "no"
    text = _normalize_lookup_key(str(value or ""))
    if text in {"si", "yes", "true", "1"}:
        return "si"
    if text in {"no", "false", "0"}:
        return "no"
    return "sin_dato"


def _build_client_rows(clients: list[dict], requests_rows: list[dict], samples: list[dict], knowledge_rows: list[dict] | None = None) -> list[dict]:
    request_count = Counter(str(row.get("client_id")) for row in requests_rows if row.get("client_id"))
    sample_count = Counter(str(row.get("client_id")) for row in samples if row.get("client_id"))
    latest_request = {}
    latest_sample = {}
    for row in requests_rows:
        client_id = str(row.get("client_id") or "")
        if client_id and client_id not in latest_request:
            latest_request[client_id] = row.get("status") or "-"
    for row in samples:
        client_id = str(row.get("client_id") or "")
        if client_id and client_id not in latest_sample:
            latest_sample[client_id] = row.get("status") or "-"

    knowledge_by_name = {}
    knowledge_by_phone = {}
    for item in knowledge_rows or []:
        name_key = _normalize_lookup_key(item.get("clinic_name"))
        phone_key = _normalize_phone(item.get("phone"))
        clinic_key = str(item.get("clinic_key") or "").strip()
        if clinic_key:
            knowledge_by_name.setdefault(clinic_key, item)
        if name_key:
            knowledge_by_name.setdefault(name_key, item)
        if phone_key:
            knowledge_by_phone.setdefault(phone_key, item)

    rows = []
    for client in clients:
        assignment = _assignment_from_client(client)
        courier = (assignment or {}).get("couriers") or {}
        client_id = str(client.get("id") or "")
        clinic_name = client.get("clinic_name") or "-"
        knowledge = knowledge_by_name.get(_normalize_lookup_key(clinic_name)) or knowledge_by_phone.get(_normalize_phone(client.get("phone"))) or {}
        commercial_name = knowledge.get("commercial_name") or ""
        display_name = commercial_name or clinic_name
        secondary_name = clinic_name if commercial_name and commercial_name != clinic_name else "-"
        assigned_courier_id = str((assignment or {}).get("courier_id") or courier.get("id") or "").strip()
        electronic_option = _bool_option(knowledge.get("electronic_invoicing"))
        entered_option = _bool_option(knowledge.get("entered_flag"))
        raw_zone = client.get("zone") or ""
        zone_display = _resolve_zone_display(raw_zone)
        rows.append({
            "client_id": client_id,
            "clinic_key": knowledge.get("clinic_key") or _normalize_lookup_key(clinic_name),
            "clinic_name": clinic_name,
            "display_name": display_name,
            "secondary_name": secondary_name,
            "commercial_name": commercial_name or "-",
            "client_code": knowledge.get("client_code") or client.get("external_code") or "-",
            "client_type": knowledge.get("client_type") or "",
            "tax_id": client.get("tax_id") or "-",
            "phone": client.get("phone") or "-",
            "email": knowledge.get("email") or knowledge.get("contact_email") or "-",
            "billing_email": knowledge.get("billing_email") or "-",
            "vat_regime": knowledge.get("vat_regime") or "",
            "electronic_invoicing_option": electronic_option,
            "invoicing_rut_url": knowledge.get("invoicing_rut_url") or "-",
            "registration_timestamp": knowledge.get("registration_timestamp") or knowledge.get("source_updated_at") or "-",
            "registration_date": knowledge.get("registration_date") or "-",
            "registration_time": knowledge.get("registration_time") or "-",
            "observations": knowledge.get("observations") or "-",
            "entered_flag_option": entered_option,
            "assigned_courier_id": assigned_courier_id,
            "client_status": "Activo" if client.get("is_active") else "Inactivo",
            "address": client.get("address") or "-",
            "zone": zone_display,
            "courier_name": courier.get("name") or "Sin mensajero",
            "requests_count": request_count.get(client_id, 0),
            "samples_count": sample_count.get(client_id, 0),
            "latest_request_status": latest_request.get(client_id, "-"),
            "latest_sample_status": latest_sample.get(client_id, "-"),
        })
    return rows


def _build_catalog_rows(catalog: list[dict]) -> list[dict]:
    rows = []
    for test in catalog:
        rows.append({
            "analysis_code": test.get("code") or test.get("test_code") or "-",
            "test_type": test.get("category") or "Sin categoria",
            "test_name": test.get("name") or test.get("test_name") or "Sin nombre",
            "turnaround": test.get("sample") or test.get("subcategory") or _format_turnaround_label(test),
            "price_cop": test.get("price") or test.get("price_cop"),
        })
    return sorted(rows, key=lambda row: str(row["analysis_code"]))


def _price_value(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _build_profile_catalog_rows(profiles: list[dict], tests: list[dict] | None = None) -> list[dict]:
    test_lookup = {}
    if tests:
        for t in tests:
            test_lookup[str(t.get("code") or "")] = t.get("name") or ""
    rows = []
    for profile in profiles:
        composed = []
        desc = profile.get("description") or ""
        if desc and tests:
            for t in tests:
                t_name = t.get("name") or ""
                t_code = str(t.get("code") or "")
                if t_name and t_name in desc:
                    composed.append({"code": t_code, "name": t_name, "item_type": "analysis"})
        rows.append({
            "item_type": "profile",
            "code": profile.get("code") or "-",
            "name": profile.get("name") or "Sin nombre",
            "category": profile.get("category") or "Sin categoria",
            "species": profile.get("species") or "ambos",
            "sample": "Perfil",
            "description": desc,
            "composed_tests": composed,
            "price": _price_value(profile.get("price")),
        })
    return sorted(rows, key=lambda row: (str(row["category"]), str(row["name"])))


def _build_analysis_catalog_rows(catalog: list[dict]) -> list[dict]:
    rows = []
    for test in catalog:
        rows.append({
            "item_type": "analysis",
            "code": test.get("code") or "-",
            "name": test.get("name") or "Sin nombre",
            "category": test.get("category") or "Sin categoria",
            "species": test.get("species") or "ambos",
            "sample": test.get("sample") or "Sin muestra definida",
            "description": "",
            "price": _price_value(test.get("price")),
        })
    return sorted(rows, key=lambda row: (str(row["category"]), str(row["name"])))


def _build_sample_process_lanes(samples: list[dict], events: list[dict]) -> list[dict]:
    events_by_sample: dict[str, list[dict]] = {}
    for event in events:
        sample_id = str(event.get("sample_id") or "")
        if sample_id:
            events_by_sample.setdefault(sample_id, []).append(event)

    cards_by_status = {status: [] for status, _label in SAMPLE_PROCESS_STAGES}
    for sample in samples:
        sample_id = str(sample.get("id") or "")
        sample_events = events_by_sample.get(sample_id, [])
        assignment_event = next(
            (event for event in sample_events if event.get("event_type") == "profile_assigned_from_dashboard"),
            {},
        )
        payload = assignment_event.get("event_payload") if isinstance(assignment_event.get("event_payload"), dict) else {}
        assigned_item = payload.get("assigned_item") if isinstance(payload.get("assigned_item"), dict) else {}
        selected_items = payload.get("selected_items") if isinstance(payload.get("selected_items"), list) else []
        sample_requirements = payload.get("sample_requirements") if isinstance(payload.get("sample_requirements"), list) else []
        client = sample.get("clients") if isinstance(sample.get("clients"), dict) else {}
        status = str(sample.get("status") or "pending_pickup")
        card = {
            "sample_id": sample_id,
            "status": status,
            "status_label": SAMPLE_STATUS_LABELS.get(status, status),
            "dropdown_status": _DROPDOWN_STATUS_MAP.get(status, status),
            "client_name": client.get("clinic_name") or "Cliente sin nombre",
            "profile_name": assigned_item.get("name") or sample.get("test_name") or "Sin perfil",
            "profile_code": assigned_item.get("code") or sample.get("test_code") or "-",
            "profile_type": assigned_item.get("item_type") or "analysis",
            "selected_items": selected_items,
            "sample_requirements": sample_requirements,
            "sample_type": sample.get("sample_type") or "-",
            "priority": sample.get("priority") or "normal",
            "created_at": sample.get("created_at") or "-",
            "events": sample_events,
        }
        lane_status = status
        if lane_status == "on_route":
            lane_status = "picked_up"
        if lane_status == "ready_results":
            lane_status = "processed"
        cards_by_status.setdefault(lane_status, []).append(card)

    return [
        {"status_key": status, "label": label, "count": len(cards_by_status.get(status, [])), "cards": cards_by_status.get(status, [])}
        for status, label in SAMPLE_PROCESS_STAGES
    ]


def _request_sample_status(request_status: str | None) -> str:
    return {
        "received": "pending_pickup",
        "assigned": "pending_pickup",
        "error_pending_assignment": "pending_pickup",
        "on_route": "on_route",
        "picked_up": "picked_up",
        "in_lab": "in_lab",
        "processed": "processed",
        "sent": "sent",
    }.get(str(request_status or ""), "pending_pickup")


def _build_service_order_rows(requests_rows: list[dict], request_events: list[dict]) -> list[dict]:
    requests_by_id = {str(row.get("id") or ""): row for row in requests_rows if row.get("id")}
    rows_by_request = {}
    for event in request_events:
        payload = event.get("event_payload") if isinstance(event.get("event_payload"), dict) else {}
        service_order = payload.get("service_order") if isinstance(payload.get("service_order"), dict) else None
        request_id = str(event.get("request_id") or "")
        if not service_order or not request_id:
            continue
        request_row = requests_by_id.get(request_id, {})
        client = request_row.get("clients") if isinstance(request_row.get("clients"), dict) else {}
        courier = request_row.get("couriers") if isinstance(request_row.get("couriers"), dict) else {}
        patient = service_order.get("patient") if isinstance(service_order.get("patient"), dict) else {}
        patient_name = patient.get("name") or request_row.get("patient_name") or "-"
        exam_type = service_order.get("exam_type") or request_row.get("exam_type") or "-"
        status = request_row.get("status") or "received"
        rows_by_request[request_id] = {
            "request_id": request_id,
            "order_number": request_row.get("order_number") or f"OS-{request_id[:8]}",
            "event_id": event.get("id") or "-",
            "created_at": event.get("created_at") or request_row.get("requested_at") or "-",
            "requested_at": request_row.get("requested_at") or event.get("created_at") or "-",
            "service_order_date": service_order.get("date") or str(request_row.get("requested_at") or event.get("created_at") or "-")[:10],
            "scheduled_pickup_date": request_row.get("scheduled_pickup_date") or "-",
            "status": status,
            "status_label": REQUEST_STATUS_LABELS.get(status, status),
            "sample_status": _request_sample_status(status),
            "priority": request_row.get("priority") or "normal",
            "courier_name": courier.get("name") or "Sin asignar",
            "requesting_doctor": service_order.get("requesting_doctor") or "-",
            "clinic_name": service_order.get("clinic_name") or client.get("clinic_name") or "Cliente sin nombre",
            "clinic_phone": service_order.get("clinic_phone") or "-",
            "pickup_address": service_order.get("pickup_address") or request_row.get("pickup_address") or "-",
            "patient_name": patient_name,
            "species": patient.get("species") or request_row.get("species") or "-",
            "breed": patient.get("breed") or "-",
            "sex": patient.get("sex") or "-",
            "patient_age": patient.get("age") or request_row.get("patient_age") or "-",
            "owner_name": patient.get("owner_name") or request_row.get("owner_name") or "-",
            "exam_type": exam_type,
            "observations": service_order.get("observations") or "-",
            "payment_method": PAYMENT_METHOD_LABELS.get(
                service_order.get("payment_method"), service_order.get("payment_method") or "-"
            ),
            "order_summary": f"{patient_name} - {exam_type}",
        }
    return sorted(rows_by_request.values(), key=lambda row: str(row.get("requested_at") or ""), reverse=True)


def _build_sample_process_lanes_with_orders(samples: list[dict], events: list[dict], service_orders: list[dict]) -> list[dict]:
    lanes = _build_sample_process_lanes(samples, events)
    cards_by_status = {lane["status_key"]: list(lane["cards"]) for lane in lanes}
    sample_request_ids = {str(sample.get("request_id") or "") for sample in samples if sample.get("request_id")}
    for order in service_orders:
        if order.get("request_id") in sample_request_ids:
            continue
        status = order.get("sample_status") or "pending_pickup"
        if status == "on_route":
            status = "picked_up"
        if status == "ready_results":
            status = "processed"
        order_code = order.get("order_number") or f"OS-{str(order.get('request_id') or '')[:8]}"
        cards_by_status.setdefault(status, []).append({
            "sample_id": f"order:{order.get('request_id')}",
            "request_id": order.get("request_id"),
            "order_number": order_code,
            "status": status,
            "status_label": SAMPLE_STATUS_LABELS.get(status, status),
            "dropdown_status": _DROPDOWN_STATUS_MAP.get(status, status),
            "client_name": order.get("clinic_name") or "Cliente sin nombre",
            "profile_name": order.get("exam_type") or "Orden de servicio",
            "profile_code": order_code,
            "profile_type": "service_order",
            "selected_items": [{"code": order_code, "name": order.get("exam_type") or "Orden de servicio", "item_type": "orden"}],
            "sample_requirements": [value for value in (order.get("species"), order.get("breed")) if value and value != "-"],
            "sample_type": "Orden de servicio",
            "priority": order.get("priority") or "normal",
            "created_at": order.get("requested_at") or "-",
            "events": [],
            "is_service_order": True,
            "service_order": order,
        })
    return [
        {"status_key": status, "label": label, "count": len(cards_by_status.get(status, [])), "cards": cards_by_status.get(status, [])}
        for status, label in SAMPLE_PROCESS_STAGES
    ]


def _demo_sample_process_lanes() -> list[dict]:
    examples = {
        "pending_pickup": ("Clinica Norte", "Demo A retirar", "PREQ-DMO", "Tubo Rojo y Tapa Morada", ["Tubo Rojo", "Tubo Tapa Morada"]),
        "picked_up": ("Vet Chapinero", "Demo Recogida y en camino", "REN-DMO", "Orina Fresca", ["Orina Fresca"]),
        "received_lab": ("Clinica Sur", "Demo Recibida laboratorio", "FEL-DMO", "Perfil personalizado", ["Tubo Rojo", "Materia Fecal"]),
        "in_lab": ("Vet Express", "Demo En analisis", "BIO-DMO", "Tubo Rojo o Amarillo", ["Tubo Rojo o Amarillo"]),
        "processed": ("Mascotas 24h", "Demo Analizados resultados listos", "TIR-DMO", "Tubo Rojo", ["Tubo Rojo"]),
        "sent": ("Caninos Centro", "Demo Enviada", "DER-DMO", "Piel y Pelos", ["Piel y Pelos"]),
    }
    lanes = []
    for status, label in SAMPLE_PROCESS_STAGES:
        client_name, profile_name, profile_code, sample_type, requirements = examples[status]
        card = {
            "sample_id": f"demo-{status}",
            "status": status,
            "status_label": SAMPLE_STATUS_LABELS.get(status, status),
            "dropdown_status": _DROPDOWN_STATUS_MAP.get(status, status),
            "client_name": client_name,
            "profile_name": profile_name,
            "profile_code": profile_code,
            "profile_type": "profile",
            "selected_items": [{"code": profile_code, "name": profile_name, "item_type": "profile"}],
            "sample_requirements": requirements,
            "sample_type": sample_type,
            "priority": "normal",
            "created_at": "2026-05-12T10:00:00",
            "events": [{"event_type": "demo_profile_assigned", "created_at": "2026-05-12T10:00:00"}],
            "is_demo": True,
        }
        lanes.append({"status_key": status, "label": label, "count": 1, "cards": [card]})
    return lanes


def _build_motorizados_context(clients: list[dict]) -> dict:
    couriers = _safe_fetch(lambda: db.list_active_couriers(limit=500), [])
    coverage = _safe_fetch(lambda: db.list_courier_locality_coverage(limit=500), [])
    territorial_zone_rows = _safe_fetch(lambda: db.list_territorial_zones(limit=100), []) or territory.build_zone_rows()
    territorial_locality_rows = _safe_fetch(lambda: db.list_territorial_neighborhoods(limit=3000), []) or territory.build_locality_zone_rows()
    courier_index = {str(row.get("id") or ""): row for row in couriers if row.get("id")}
    couriers_options = [
        {
            "id": str(row.get("id") or ""),
            "name": row.get("name") or "Sin nombre",
            "phone": row.get("phone") or "",
            "availability": row.get("availability") or "available",
            "color": _courier_color(str(row.get("id") or ""), row.get("name")),
            "zone_number": None,
            "source": "db",
        }
        for row in couriers
        if row.get("id")
    ]
    couriers_by_name = {_normalize_lookup_key(row["name"]): row for row in couriers_options}
    zone_courier_ids = {}
    for row in territorial_zone_rows:
        name_key = _normalize_lookup_key(row["courier_name"])
        courier = couriers_by_name.get(name_key)
        if courier is None:
            courier = {
                "id": f"territory-zone-{row['zone_number']}",
                "name": row["courier_name"],
                "phone": row["courier_phone"],
                "availability": "territorial",
                "color": _courier_color(f"territory-zone-{row['zone_number']}", row.get("courier_name")),
                "zone_number": row["zone_number"],
                "source": "territory",
            }
            couriers_options.append(courier)
            couriers_by_name[name_key] = courier
        else:
            courier["zone_number"] = row["zone_number"]
            if not courier.get("phone"):
                courier["phone"] = row.get("courier_phone") or ""
        zone_courier_ids[row["zone_number"]] = courier["id"]

    coverage_by_code = {}
    localities_by_courier: dict[str, list[str]] = {}
    for row in coverage:
        code = _normalize_locality_code(row.get("locality_code") or row.get("locality_name"))
        if not code:
            continue
        coverage_by_code[code] = row
        courier_id = str(row.get("courier_id") or "").strip()
        locality_name = row.get("locality_name") or BOGOTA_LOCALITIES_BY_CODE.get(code, {}).get("name") or code
        if courier_id:
            localities_by_courier.setdefault(courier_id, []).append(locality_name)

    territory_by_locality = {}
    for row in territorial_locality_rows:
        code = row["locality_code"]
        previous = territory_by_locality.get(code)
        barrios_count = row.get("barrios_count", row.get("cantidad_barrios", 0))
        row["barrios_count"] = barrios_count
        if previous is None or barrios_count > previous["barrios_count"]:
            territory_by_locality[code] = row
        courier_id = zone_courier_ids.get(row["zone_number"])
        if courier_id:
            localities_by_courier.setdefault(courier_id, []).append(row["locality_name"])

    clients_by_locality = Counter()
    for client in clients:
        locality = _resolve_locality(client.get("zone"))
        if locality:
            clients_by_locality[locality["code"]] += 1

    localities_rows = []
    coverage_map_points = []
    clients_by_courier = Counter()
    for locality in BOGOTA_LOCALITIES:
        code = locality["code"]
        row = coverage_by_code.get(code) or {}
        courier_payload = row.get("couriers") if isinstance(row.get("couriers"), dict) else {}
        courier_id = str(row.get("courier_id") or courier_payload.get("id") or "").strip()
        courier_name = courier_payload.get("name") or courier_index.get(courier_id, {}).get("name") or "Sin asignar"
        territorial_row = territory_by_locality.get(code) or {}
        if not courier_id and territorial_row:
            courier_id = zone_courier_ids.get(territorial_row["zone_number"], "")
            courier_name = territorial_row["courier_name"]
        clients_count = clients_by_locality.get(code, 0)
        if courier_id:
            clients_by_courier[courier_id] += clients_count
        localities_rows.append({
            "locality_code": code,
            "locality_name": locality["name"],
            "clients_count": clients_count,
            "coverage_state": "assigned" if row else "territorial" if courier_id else "pending",
            "assigned_courier_id": courier_id,
            "assigned_courier_name": courier_name,
            "zone_number": territorial_row.get("zone_number"),
            "barrios_count": territorial_row.get("barrios_count", 0),
            "is_assigned": bool(courier_id),
        })
        lat, lng = BOGOTA_LOCALITY_COORDS.get(code, (4.65, -74.1))
        coverage_map_points.append({
            "locality_code": code,
            "locality_name": locality["name"],
            "lat": lat,
            "lng": lng,
            "courier_id": courier_id,
            "courier_name": courier_name,
            "color": _courier_color(courier_id, courier_name),
            "is_assigned": bool(courier_id),
            "clients_count": clients_count,
        })

    couriers_rows = []
    for courier in couriers_options:
        assigned_localities = sorted(set(localities_by_courier.get(courier["id"], [])), key=_normalize_lookup_key)
        couriers_rows.append({
            "id": courier["id"],
            "name": courier["name"],
            "phone": courier["phone"],
            "availability": courier["availability"],
            "color": courier["color"],
            "zone_number": courier.get("zone_number"),
            "source": courier.get("source", "db"),
            "coverage_count": len(assigned_localities),
            "clients_count_from_coverage": clients_by_courier.get(courier["id"], 0),
            "localities_text": ", ".join(assigned_localities) if assigned_localities else "Sin zonas asignadas",
        })

    assigned_localities = sum(1 for row in localities_rows if row["is_assigned"])
    clients_in_catalog = sum(clients_by_locality.values())
    clients_assigned = sum(row["clients_count"] for row in localities_rows if row["is_assigned"])
    risk_localities = sum(1 for row in localities_rows if row["clients_count"] and not row["is_assigned"])
    busiest = max(couriers_rows, key=lambda row: row["clients_count_from_coverage"], default={})
    alerts = []
    if risk_localities:
        alerts.append({"level": "warning", "title": "Cobertura pendiente", "detail": f"{risk_localities} localidad(es) con clientes sin motorizado."})
    if any(not _normalize_phone(row["phone"]) for row in couriers_rows):
        alerts.append({"level": "warning", "title": "Telefonos incompletos", "detail": "Hay motorizados activos sin telefono operativo."})

    context = {
        "couriers_options": sorted(couriers_options, key=lambda row: (row.get("source") != "db", row["name"])),
        "couriers_rows": sorted(couriers_rows, key=lambda row: (row.get("source") != "db", row["name"])),
        "localities_rows": sorted(localities_rows, key=lambda row: row["locality_name"]),
        "motorizados_summary": {
            "coverage_rate": round((assigned_localities / len(BOGOTA_LOCALITIES)) * 100) if BOGOTA_LOCALITIES else 0,
            "assigned_localities": assigned_localities,
            "total_localities": len(BOGOTA_LOCALITIES),
            "clients_in_assigned_localities": clients_assigned,
            "clients_in_catalog_localities": clients_in_catalog,
            "clients_in_unassigned_localities": max(clients_in_catalog - clients_assigned, 0),
            "localities_with_clients_without_coverage": risk_localities,
            "busiest_courier_name": busiest.get("name") or "Sin datos",
            "busiest_courier_clients": busiest.get("clients_count_from_coverage") or 0,
        },
        "motorizados_alerts": alerts,
        "coverage_map_points": coverage_map_points,
        "territorial_zone_rows": territorial_zone_rows,
        "territorial_locality_rows": territorial_locality_rows,
        "localities_geojson_url": LOCALITIES_GEOJSON_URL,
    }
    return context


def _build_flow_lanes(sessions_rows: list[dict]) -> list[dict]:
    by_stage: dict[str, list[dict]] = {}
    for item in sessions_rows:
        stage = item.get("phase_current") or "sin_etapa"
        client = item.get("clients") if isinstance(item.get("clients"), dict) else {}
        by_stage.setdefault(stage, []).append({
            "external_chat_id": item.get("external_chat_id") or "-",
            "clinic_name": client.get("clinic_name") or "Sin identificar",
            "phone": client.get("phone") or "-",
        })
    return [
        {"stage_key": key, "label": label, "count": len(by_stage.get(key, [])), "cards": by_stage.get(key, [])}
        for key, label in FLOW_STAGES
    ]


def _build_approval_rows(sessions_rows: list[dict]) -> tuple[list[dict], list[dict]]:
    pending = []
    reviewed = []
    for item in sessions_rows:
        fields = item.get("captured_fields") if isinstance(item.get("captured_fields"), dict) else {}
        status = str(fields.get("new_client_review_status") or "").strip()
        if not status:
            continue
        client = item.get("clients") if isinstance(item.get("clients"), dict) else {}
        row = {
            "external_chat_id": item.get("external_chat_id") or "-",
            "clinic_name": fields.get("new_client_legal_name") or client.get("clinic_name") or "Sin nombre",
            "profile_label": "Clinica veterinaria" if fields.get("new_client_profile_type") == "clinica" else "Medico veterinario independiente",
            "document_type": fields.get("new_client_document_type") or "-",
            "document_number": fields.get("new_client_document_number") or "-",
            "contact_phone": fields.get("new_client_contact_phone") or client.get("phone") or "-",
            "updated_at": item.get("updated_at") or "-",
            "review_status_label": status,
            "review_by": fields.get("new_client_review_by") or "-",
            "review_at": fields.get("new_client_review_at") or "-",
            "review_reason": fields.get("new_client_review_reason") or "-",
        }
        if status == "pending_manual_approval":
            pending.append(row)
        else:
            reviewed.append(row)
    return pending, reviewed


def _build_request_approval_rows(review_rows: list[dict]) -> list[dict]:
    rows = []
    for item in review_rows:
        client = item.get("clients") if isinstance(item.get("clients"), dict) else {}
        review = item.get("review_payload") if isinstance(item.get("review_payload"), dict) else {}
        rows.append({
            "request_id": item.get("id") or "-",
            "clinic_name": client.get("clinic_name") or "Sin nombre",
            "profile_label": "Clinica veterinaria",
            "document_type": "NIT",
            "document_number": client.get("tax_id") or "-",
            "contact_phone": client.get("phone") or "-",
            "updated_at": item.get("requested_at") or "-",
            "address": client.get("address") or "-",
            "zone": client.get("zone") or "-",
            "contact_name": review.get("contact_name") or "-",
            "email": review.get("email") or "-",
            "documents": review.get("documents") or {},
            "notes": review.get("notes") or "-",
        })
    return rows


def _build_operation_center(requests_rows: list[dict], samples: list[dict], approval_rows: list[dict], motorizados_context: dict, service_orders: list[dict] | None = None) -> dict:
    active_route_statuses = {"received", "assigned", "on_route", "error_pending_assignment"}
    sample_pending_statuses = {"pending_pickup", "picked_up", "on_route", "received_lab", "in_lab"}
    service_order_by_request = {str(row.get("request_id") or ""): row for row in service_orders or []}
    route_rows = []
    alerts = []

    for row in requests_rows:
        status = row.get("status") or "unknown"
        if row.get("service_area") == "route_scheduling" and status in active_route_statuses:
            client = row.get("clients") if isinstance(row.get("clients"), dict) else {}
            courier = row.get("couriers") if isinstance(row.get("couriers"), dict) else {}
            service_order = service_order_by_request.get(str(row.get("id") or ""))
            route_rows.append({
                "id": row.get("id") or "-",
                "order_number": row.get("order_number") or f"OS-{str(row.get('id') or '')[:8]}",
                "clinic_name": client.get("clinic_name") or "Cliente sin nombre",
                "address": row.get("pickup_address") or "Sin direccion",
                "status": status,
                "status_label": REQUEST_STATUS_LABELS.get(status, status),
                "courier_name": courier.get("name") or "Sin asignar",
                "scheduled_pickup_date": row.get("scheduled_pickup_date") or "-",
                "service_order": service_order,
                "order_summary": (service_order or {}).get("order_summary") or row.get("exam_type") or "Sin orden detallada",
            })
            if _request_is_unassigned(row):
                alerts.append({"level": "warning", "title": "Ruta sin asignar", "detail": f"{client.get('clinic_name') or 'Cliente'} requiere motorizado."})

    for alert in motorizados_context.get("motorizados_alerts", []):
        alerts.append(alert)

    sample_status = Counter((row.get("status") or "unknown") for row in samples)
    sample_lanes = [
        {"status": status, "label": label, "count": sample_status.get(status, 0)}
        for status, label in SAMPLE_PROCESS_STAGES
        if status in sample_pending_statuses
    ]
    routes_by_courier = {}
    for row in route_rows:
        courier_name = row["courier_name"] or "Sin asignar"
        routes_by_courier.setdefault(courier_name, []).append(row)
    courier_agenda = [
        {"courier_name": courier_name, "count": len(rows), "routes": rows[:8]}
        for courier_name, rows in sorted(routes_by_courier.items(), key=lambda item: (item[0] != "Sin asignar", item[0]))
    ]
    return {
        "kpis": {
            "active_routes": len(route_rows),
            "pending_approvals": len(approval_rows),
            "pending_samples": sum(sample_status.get(status, 0) for status in sample_pending_statuses),
            "critical_alerts": len(alerts),
        },
        "alerts": alerts[:8],
        "route_rows": route_rows[:12],
        "courier_agenda": courier_agenda,
        "service_order_rows": (service_orders or [])[:8],
        "approval_rows": approval_rows[:8],
        "sample_lanes": sample_lanes,
    }


def _client_form_payload(form) -> tuple[dict, dict, dict]:
    electronic_invoicing = _bool_option(form.get("electronic_invoicing"))
    electronic_invoicing_value = True if electronic_invoicing == "si" else False if electronic_invoicing == "no" else None
    entered_flag = form.get("entered_flag") == "on"

    client_payload = {
        "clinic_name": (form.get("clinic_name") or "").strip(),
        "tax_id": (form.get("tax_id") or "").strip(),
        "phone": _normalize_phone(form.get("phone")),
        "address": (form.get("address") or "").strip(),
        "zone": (form.get("zone") or "").strip(),
        "billing_type": (form.get("billing_type") or "cash").strip(),
        "is_active": False,
    }
    profile_payload = {
        "clinic_key": _normalize_lookup_key(client_payload["clinic_name"]),
        "clinic_name": client_payload["clinic_name"],
        "commercial_name": _sanitize_text(form.get("commercial_name") or client_payload["clinic_name"], 180),
        "client_code": _sanitize_text(form.get("client_code"), 80),
        "client_type": form.get("client_type") if form.get("client_type") in CLIENT_TYPE_OPTIONS else None,
        "email": _sanitize_text(form.get("email"), 240),
        "billing_email": _sanitize_text(form.get("billing_email"), 240),
        "vat_regime": form.get("vat_regime") if form.get("vat_regime") in VAT_REGIME_OPTIONS else None,
        "electronic_invoicing": electronic_invoicing_value,
        "invoicing_rut_url": _sanitize_text(form.get("invoicing_rut_url"), 500),
        "observations": _sanitize_text(form.get("notes"), 1200),
        "entered_flag": entered_flag,
        "source_updated_at": datetime.now(timezone.utc).isoformat(),
    }
    profile_payload = {
        key: value
        for key, value in profile_payload.items()
        if value is not None and (not isinstance(value, str) or value.strip())
    }
    review_payload = {
        "source": "dashboard",
        "contact_name": (form.get("contact_name") or "").strip(),
        "email": (form.get("email") or "").strip(),
        "billing_email": (form.get("billing_email") or "").strip(),
        "neighborhood": _sanitize_text(form.get("neighborhood"), 180),
        "locality": _sanitize_text(form.get("locality"), 180),
        "profile": profile_payload,
        "notes": (form.get("notes") or "").strip(),
        "courier_id": (form.get("courier_id") or "").strip() or None,
        "documents": {
            "rut_received": form.get("rut_received") == "on",
            "chamber_received": form.get("chamber_received") == "on",
            "representative_id_received": form.get("representative_id_received") == "on",
            "additional_support_received": form.get("additional_support_received") == "on",
        },
    }
    return client_payload, review_payload, profile_payload


def _suggest_courier_for_location(form, couriers: list[dict]) -> dict:
    suggestion = territory.suggest_zone_for_location(
        neighborhood=form.get("neighborhood"),
        locality=form.get("locality"),
        zone=form.get("zone"),
        address=form.get("address"),
    )
    courier_name = suggestion.get("courier_name") or ""
    courier = next((row for row in couriers if _normalize_lookup_key(row.get("name")) == _normalize_lookup_key(courier_name)), None)
    return {
        "matched": bool(courier and suggestion.get("zone_number")),
        "courier_id": str((courier or {}).get("id") or ""),
        "courier_name": courier_name,
        "zone_number": suggestion.get("zone_number"),
        "match_type": suggestion.get("match_type"),
        "confidence": suggestion.get("confidence"),
        "matched_value": suggestion.get("neighborhood_name") or suggestion.get("locality_name") or courier_name,
    }


def build_dashboard_context() -> dict:
    try:
        clients = db.list_clients_with_assignment(limit=500)
        requests_rows = db.list_requests(limit=500)
        sessions_rows = db.list_sessions(limit=500)
    except Exception as exc:
        return _empty_context(str(exc))

    clients_with_courier = sum(
        1 for client in clients if (_assignment_from_client(client) or {}).get("courier_id")
    )
    active_statuses = {
        "received", "assigned", "on_route", "picked_up", "in_lab", "processed", "error_pending_assignment",
    }
    unassigned = [row for row in requests_rows if _request_is_unassigned(row)]
    messages = _safe_fetch(lambda: db.list_conversation_messages(limit=500), [])
    catalog = _safe_fetch(lambda: db.list_catalog_tests(limit=4000), [])
    profiles = _safe_fetch(lambda: db.list_catalog_profiles(limit=4000), [])
    knowledge = _safe_fetch(lambda: db.list_a3_knowledge_index(limit=5000), [])
    samples = _safe_fetch(
        lambda: db.fetch_rows(
            "lab_samples",
            "id, request_id, client_id, status, priority, test_code, test_name, sample_type, created_at, clients(clinic_name), couriers(name)",
            4000,
        ),
        [],
    )
    sample_events = _safe_fetch(lambda: db.fetch_rows("lab_sample_events", "id, sample_id, event_type, event_payload, created_at", 4000), [])
    request_events = _safe_fetch(lambda: db.fetch_rows("request_events", "id, request_id, event_type, event_payload, created_at", 4000), [])
    sample_count_map = {}
    sample_types_map = {}
    for event in request_events:
        payload = event.get("event_payload") if isinstance(event.get("event_payload"), dict) else {}
        request_id = str(event.get("request_id") or "")
        if not request_id:
            continue
        if event.get("event_type") == "dashboard_request_manual_update":
            if "sample_count" in payload:
                sample_count_map[request_id] = payload["sample_count"]
            if "sample_types" in payload:
                sample_types_map[request_id] = ", ".join(payload["sample_types"]) if isinstance(payload["sample_types"], list) else str(payload["sample_types"])
    for row in requests_rows:
        rid = str(row.get("id") or "")
        if rid in sample_count_map:
            row["sample_count"] = sample_count_map[rid]
        if rid in sample_types_map:
            row["sample_types_display"] = sample_types_map[rid]
    phases = Counter((row.get("phase_current") or "sin_etapa") for row in sessions_rows)
    sample_status = Counter((row.get("status") or "unknown") for row in samples)
    approval_rows, reviewed_rows = _build_approval_rows(sessions_rows)
    approval_rows.extend(_build_request_approval_rows(_safe_fetch(lambda: db.list_pending_client_reviews(limit=300), [])))
    motorizados_context = _build_motorizados_context(clients)
    service_order_rows = _build_service_order_rows(requests_rows, request_events)
    operation_center = _build_operation_center(requests_rows, samples, approval_rows, motorizados_context, service_order_rows)
    profile_rows = _build_profile_catalog_rows(profiles, catalog)
    analysis_rows = _build_analysis_catalog_rows(catalog)
    builder_items = profile_rows + analysis_rows

    context = {
        "summary": {
            "total_clients": len(clients),
            "clients_with_courier": clients_with_courier,
            "clients_without_courier": max(len(clients) - clients_with_courier, 0),
            "active_requests": sum(1 for row in requests_rows if (row.get("status") or "") in active_statuses),
            "unassigned_requests": len(unassigned),
            "sessions_tracked": len(sessions_rows),
            "pending_pickup": sample_status.get("pending_pickup", 0),
            "total_samples": len(samples),
            "catalog_tests": len(catalog),
            "catalog_profiles": len(profiles),
            "pending_manual_approvals": len(approval_rows),
        },
        "request_status": dict(Counter((row.get("status") or "unknown") for row in requests_rows)),
        "sample_status": dict(sample_status),
        "requests_by_status": dict(Counter((row.get("status") or "unknown") for row in requests_rows)),
        "service_area_counts": dict(Counter((row.get("service_area") or "unknown") for row in requests_rows)),
        "flow_stage_counts": [
            {"stage_key": key, "count": count}
            for key, count in sorted(phases.items())
        ],
        "flow_kanban_lanes": _build_flow_lanes(sessions_rows),
        "unassigned_request_rows": unassigned[:50],
        "clients": clients,
        "requests": requests_rows,
        "sessions": sessions_rows,
        "messages": messages,
        "samples": [{**s, "dropdown_status": _DROPDOWN_STATUS_MAP.get(s.get("status"), s.get("status"))} for s in samples],
        "sample_process_lanes": _build_sample_process_lanes_with_orders(samples, sample_events, service_order_rows),
        "service_order_rows": service_order_rows,
        "clients_rows": _build_client_rows(clients, requests_rows, samples, knowledge),
        "catalog_rows": _build_catalog_rows(catalog),
        "profile_catalog_rows": profile_rows,
        "profile_analysis_rows": analysis_rows,
        "profile_builder_items": builder_items,
        "custom_profiles": _safe_fetch(lambda: db.list_custom_profiles(limit=100), []),
        "profile_categories": sorted({row["category"] for row in builder_items if row.get("category")}),
        "profile_species": sorted({row["species"] for row in builder_items if row.get("species")}),
        "sample_requirements": sorted({row["sample"] for row in analysis_rows if row.get("sample") and row.get("sample") != "Sin muestra definida"}),
        "approval_rows": approval_rows,
        "reviewed_approval_rows": reviewed_rows,
        "operation_center": operation_center,
        "affiliation_rows": [],
        "client_type_options": CLIENT_TYPE_OPTIONS,
        "vat_regime_options": VAT_REGIME_OPTIONS,
        "request_priority_options": [{"value": key, "label": value} for key, value in REQUEST_PRIORITY_LABELS.items()],
        "request_status_options": [{"value": key, "label": value} for key, value in REQUEST_STATUS_LABELS.items()],
        "sample_status_options": list(SAMPLE_STATUS_DROPDOWN),
        "sample_type_options": sorted({row.get("sample") or row.get("sample_type") for row in catalog if row.get("sample") or row.get("sample_type")}),
        "sample_placeholder_rows": [],
        "sample_placeholder_status": {},
        "knowledge_profile_compat_mode": False,
        "error": None,
    }
    context.update(motorizados_context)
    return context


@dashboard.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        if username == DASHBOARD_ADMIN_USER and password == DASHBOARD_ADMIN_PASSWORD:
            session["dashboard_authenticated"] = True
            session["dashboard_username"] = username
            return redirect(url_for("dashboard.dashboard_home"))
        return render_template("login.html", error="Credenciales invalidas")
    return render_template("login.html", error=None)


@dashboard.get("/logout")
def logout():
    session.pop("dashboard_authenticated", None)
    session.pop("dashboard_username", None)
    return redirect(url_for("dashboard.login"))


@dashboard.get("/")
def root():
    if session.get("dashboard_authenticated"):
        return redirect(url_for("dashboard.dashboard_home"))
    return redirect(url_for("dashboard.login"))


@dashboard.get("/dashboard")
@_login_required
def dashboard_home():
    return _render_dashboard("dashboard")


@dashboard.get("/operacion")
@_login_required
def operation_page():
    return _render_dashboard("operacion")


@dashboard.get("/clientes")
@_login_required
def clients_page():
    return _render_dashboard("clientes")


@dashboard.route("/clientes/nuevo", methods=["GET", "POST"])
@_login_required
def new_client_page():
    couriers = _safe_fetch(lambda: db.list_active_couriers(limit=500), [])
    template_context = {
        "couriers": couriers,
        "client_type_options": CLIENT_TYPE_OPTIONS,
        "vat_regime_options": VAT_REGIME_OPTIONS,
    }
    if request.method == "POST":
        client_payload, review_payload, profile_payload = _client_form_payload(request.form)
        required_client_fields = ["clinic_name", "tax_id", "phone", "address", "zone"]
        required_form_fields = ["email", "billing_email", "client_type", "vat_regime", "electronic_invoicing", "contact_name"]
        missing = [field for field in required_client_fields if not client_payload.get(field)]
        missing.extend(field for field in required_form_fields if not (request.form.get(field) or "").strip())
        if missing:
            return render_template("new_client.html", error="Completa todos los campos obligatorios.", form=request.form, **template_context)

        invalid_options = (
            request.form.get("client_type") not in CLIENT_TYPE_OPTIONS
            or request.form.get("vat_regime") not in VAT_REGIME_OPTIONS
            or _bool_option(request.form.get("electronic_invoicing")) == "sin_dato"
        )
        if invalid_options:
            return render_template("new_client.html", error="Selecciona opciones validas.", form=request.form, **template_context)

        courier_id = review_payload.get("courier_id")
        courier_ids = {str(courier.get("id") or "") for courier in couriers}
        if courier_id and courier_id not in courier_ids:
            return render_template("new_client.html", error="Selecciona un motorizado valido.", form=request.form, **template_context)

        duplicate = db.find_client_for_dashboard(
            tax_id=client_payload["tax_id"],
            phone=client_payload["phone"],
            clinic_name=client_payload["clinic_name"],
        )
        if duplicate:
            return render_template("new_client.html", error="Ya existe un cliente con ese NIT, telefono o nombre.", form=request.form, **template_context)

        suggestion = _suggest_courier_for_location(request.form, couriers)
        review_payload["courier_suggestion"] = suggestion
        if not review_payload.get("courier_id") and suggestion["matched"]:
            review_payload["courier_id"] = suggestion["courier_id"]

        db.create_pending_client_review(client_payload=client_payload, review_payload=review_payload)
        db.upsert_client_profile(profile_payload)
        return redirect(url_for("dashboard.approvals_page", notice="Cliente enviado a revision", notice_type="ok"))

    return render_template("new_client.html", error=None, form={}, **template_context)


@dashboard.get("/solicitudes")
@_login_required
def requests_page():
    return _render_dashboard("solicitudes")


@dashboard.get("/muestras")
@_login_required
def samples_page():
    return _render_dashboard("muestras")


@dashboard.get("/ordenes-servicio/<request_id>/imprimir")
@_login_required
def service_order_print_page(request_id: str):
    context = build_dashboard_context()
    order = next(
        (row for row in context.get("service_order_rows", []) if str(row.get("request_id")) == request_id),
        None,
    )
    if not order:
        abort(404)
    return render_template("service_order_print.html", order=order)


@dashboard.get("/analisis")
@_login_required
def analysis_page():
    return _render_dashboard("analisis")


@dashboard.get("/flujo")
@_login_required
def flow_page():
    return _render_dashboard("flujo")


@dashboard.get("/aprobaciones")
@_login_required
def approvals_page():
    return _render_dashboard("aprobaciones")


@dashboard.post("/aprobaciones/decision")
@_login_required
def approval_decision():
    request_id = (request.form.get("request_id") or "").strip()
    decision = (request.form.get("decision") or "").strip()
    reason = (request.form.get("reason") or "").strip()
    if decision == "approve":
        ok = db.approve_pending_client(request_id)
        message = "Cliente aprobado" if ok else "No fue posible aprobar el cliente"
    else:
        ok = db.reject_pending_client(request_id, reason or "Rechazado desde dashboard")
        message = "Cliente rechazado" if ok else "No fue posible rechazar el cliente"
    return redirect(url_for("dashboard.approvals_page", notice=message, notice_type="ok" if ok else "error"))


@dashboard.get("/motorizados")
@_login_required
def motorizados_page():
    return _render_dashboard("motorizados")


@dashboard.get("/api/dashboard/courier-suggestion")
@_login_required
def courier_suggestion():
    couriers = _safe_fetch(lambda: db.list_active_couriers(limit=500), [])
    suggestion = _suggest_courier_for_location(request.args, couriers)
    return jsonify(suggestion)


@dashboard.get("/api/dashboard/neighborhood-search")
@_login_required
def neighborhood_search():
    query = (request.args.get("q") or "").strip()
    rows = territory.search_neighborhoods(query, limit=12)
    return jsonify({"count": len(rows), "rows": rows})


@dashboard.post("/api/dashboard/courier-phone")
@_login_required
def update_courier_phone():
    payload = request.get_json(silent=True) or {}
    courier_id = str(payload.get("courier_id") or "").strip()
    phone = _normalize_phone(payload.get("phone"))
    if not courier_id:
        return jsonify({"error": "Missing courier_id"}), 400
    if not phone or len(phone) < 7:
        return jsonify({"error": "Invalid phone"}), 400
    try:
        ok = db.update_courier_phone(courier_id, phone)
    except Exception as exc:
        if "duplicate" in str(exc).lower() or "couriers_phone_key" in str(exc).lower():
            return jsonify({"error": "Phone already exists for another courier"}), 409
        return jsonify({"error": "Unable to update courier phone"}), 503
    if not ok:
        return jsonify({"error": "Courier not found"}), 404
    return jsonify({"ok": True, "courier_id": courier_id, "phone": phone})


@dashboard.post("/api/dashboard/courier-availability")
@_login_required
def update_courier_availability():
    payload = request.get_json(silent=True) or {}
    courier_id = str(payload.get("courier_id") or "").strip()
    availability = str(payload.get("availability") or "").strip()
    if not courier_id:
        return jsonify({"error": "Missing courier_id"}), 400
    valid_options = {"available", "unavailable", "on_route", "territorial"}
    if availability not in valid_options:
        return jsonify({"error": "Invalid availability value"}), 400
    try:
        ok = db.update_courier(courier_id, {"availability": availability})
    except Exception:
        return jsonify({"error": "Unable to update courier availability"}), 503
    if not ok:
        return jsonify({"error": "Courier not found"}), 404
    return jsonify({"ok": True, "courier_id": courier_id, "availability": availability})


@dashboard.post("/api/dashboard/courier-locality-assignment")
@_login_required
def update_courier_locality_assignment():
    payload = request.get_json(silent=True) or {}
    locality_code = _normalize_locality_code(payload.get("locality_code"))
    courier_id = str(payload.get("courier_id") or "").strip()
    if locality_code not in BOGOTA_LOCALITIES_BY_CODE:
        return jsonify({"error": "Unsupported locality_code"}), 400
    locality_name = BOGOTA_LOCALITIES_BY_CODE[locality_code]["name"]
    assigned_by = f"dashboard:{session.get('dashboard_username') or 'operator'}"
    try:
        if courier_id:
            db.upsert_courier_locality_coverage(
                locality_code=locality_code,
                locality_name=locality_name,
                courier_id=courier_id,
                assigned_by=assigned_by,
            )
        else:
            db.delete_courier_locality_coverage(locality_code)
    except Exception:
        return jsonify({"error": "Unable to update locality coverage"}), 503
    return jsonify({"ok": True, "locality_code": locality_code, "locality_name": locality_name, "courier_id": courier_id or None})


@dashboard.post("/api/dashboard/client-assignment")
@_login_required
def update_client_assignment():
    payload = request.get_json(silent=True) or {}
    client_id = str(payload.get("client_id") or "").strip()
    courier_id = str(payload.get("courier_id") or "").strip()
    if not client_id:
        return jsonify({"error": "Missing client_id"}), 400
    try:
        db.upsert_client_assignment(client_id=client_id, courier_id=courier_id or None, assigned_by=f"dashboard:{session.get('dashboard_username') or 'operator'}")
    except Exception:
        return jsonify({"error": "Unable to update courier assignment"}), 503
    return jsonify({"ok": True, "client_id": client_id, "courier_id": courier_id or None})


@dashboard.post("/api/dashboard/client-delete")
@_login_required
def delete_client():
    payload = request.get_json(silent=True) or {}
    client_id = str(payload.get("client_id") or "").strip()
    clinic_key = _normalize_lookup_key(payload.get("clinic_key"))
    if not client_id:
        return jsonify({"error": "Missing client_id"}), 400
    try:
        ok = db.delete_client_completely(client_id=client_id, clinic_key=clinic_key or None)
    except Exception:
        return jsonify({"error": "Unable to delete client"}), 503
    if not ok:
        return jsonify({"error": "Client not found"}), 404
    return jsonify({"ok": True, "client_id": client_id})


@dashboard.post("/api/dashboard/client-profile")
@_login_required
def update_client_profile():
    payload = request.get_json(silent=True) or {}
    client_id = str(payload.get("client_id") or "").strip()
    clinic_key = _normalize_lookup_key(payload.get("clinic_key"))
    clinic_name = _sanitize_text(payload.get("clinic_name"), 180)
    field = str(payload.get("field") or "").strip()
    value = payload.get("value")
    allowed_client_fields = {"clinic_name", "phone", "address", "zone", "billing_type", "tax_id", "is_active"}
    allowed_profile_fields = {"client_code", "commercial_name", "client_type", "billing_email", "vat_regime", "electronic_invoicing", "invoicing_rut_url", "observations", "entered_flag"}
    if not client_id and not clinic_key:
        return jsonify({"error": "Missing client_id"}), 400
    if field not in allowed_client_fields and field not in allowed_profile_fields:
        return jsonify({"error": "Unsupported field"}), 400
    try:
        if field in allowed_client_fields:
            update_payload = {field: value}
            if field == "is_active":
                update_payload = {field: value is True or str(value).lower() == "true"}
            db.update_client_profile(client_id, update_payload)
            if field == "clinic_name" and clinic_key:
                db.upsert_client_profile({
                    "clinic_key": clinic_key,
                    "clinic_name": _sanitize_text(value, 180) or clinic_key,
                    "source_updated_at": datetime.now(timezone.utc).isoformat(),
                })
        else:
            profile_value = value
            if field in {"electronic_invoicing", "entered_flag"}:
                option = _bool_option(value)
                profile_value = True if option == "si" else False if option == "no" else None
            elif field == "client_type" and value not in CLIENT_TYPE_OPTIONS:
                profile_value = None
            elif field == "vat_regime" and value not in VAT_REGIME_OPTIONS:
                profile_value = None
            else:
                profile_value = _sanitize_text(value, 1200 if field == "observations" else 500)
            db.upsert_client_profile({
                "clinic_key": clinic_key,
                "clinic_name": clinic_name or clinic_key,
                field: profile_value,
                "source_updated_at": datetime.now(timezone.utc).isoformat(),
            })
            if field == "client_code" and client_id:
                db.update_client_profile(client_id, {"external_code": profile_value})
    except Exception:
        return jsonify({"error": "Unable to update client profile"}), 503
    return jsonify({"ok": True, "client_id": client_id, "field": field, "value": value})


@dashboard.post("/api/dashboard/request-operation")
@_login_required
def update_request_operation():
    payload = request.get_json(silent=True) or {}
    request_id = str(payload.get("request_id") or "").strip()
    if not request_id:
        return jsonify({"error": "Missing request_id"}), 400
    editable_keys = ("priority", "sample_count", "sample_types", "pickup_address", "assigned_courier_id", "scheduled_pickup_date")
    if not any(key in payload for key in editable_keys):
        return jsonify({"error": "Missing editable fields"}), 400

    event_payload = {"updated_by": session.get("dashboard_username") or "operator", "source": "dashboard_solicitudes", "updated_at": datetime.now(timezone.utc).isoformat()}
    response_payload = {"ok": True, "request_id": request_id}
    try:
        if "priority" in payload:
            priority = _normalize_priority(payload.get("priority"))
            if not priority:
                return jsonify({"error": "Invalid request priority"}), 400
            db_priority = _normalize_priority_db(priority)
            db.update_request(request_id, {"priority": db_priority})
            event_payload.update({"priority": priority, "priority_label": REQUEST_PRIORITY_LABELS.get(priority, priority), "priority_db_value": db_priority})
            response_payload["priority"] = priority
        if "sample_count" in payload:
            sample_count = _normalize_sample_count(payload.get("sample_count"))
            if sample_count is None:
                return jsonify({"error": "Invalid sample_count"}), 400
            event_payload["sample_count"] = sample_count
            response_payload["sample_count"] = sample_count
        if "sample_types" in payload:
            sample_types = _normalize_sample_types(payload.get("sample_types"))
            event_payload["sample_types"] = sample_types
            response_payload["sample_types"] = sample_types
        if "pickup_address" in payload:
            address = _sanitize_text(payload.get("pickup_address"), 300)
            db.update_request(request_id, {"pickup_address": address})
            event_payload["pickup_address"] = address
            response_payload["pickup_address"] = address
        if "assigned_courier_id" in payload:
            courier_id = str(payload.get("assigned_courier_id") or "").strip() or None
            db.update_request(request_id, {"assigned_courier_id": courier_id})
            event_payload["assigned_courier_id"] = courier_id
            response_payload["assigned_courier_id"] = courier_id
        if "scheduled_pickup_date" in payload:
            date_val = _sanitize_text(payload.get("scheduled_pickup_date"), 30)
            db.update_request(request_id, {"scheduled_pickup_date": date_val or None})
            event_payload["scheduled_pickup_date"] = date_val
            response_payload["scheduled_pickup_date"] = date_val
        db.create_request_event(request_id, "dashboard_request_manual_update", event_payload)
    except Exception:
        return jsonify({"error": "Unable to update request operation"}), 503
    return jsonify(response_payload)


@dashboard.post("/api/dashboard/request-status")
@_login_required
def update_request_status():
    payload = request.get_json(silent=True) or {}
    request_id = str(payload.get("request_id") or "").strip()
    status = _normalize_status(payload.get("status"))
    if not request_id:
        return jsonify({"error": "Missing request_id"}), 400
    if status not in REQUEST_STATUS_LABELS:
        return jsonify({"error": "Invalid request status"}), 400
    try:
        db.update_request(request_id, {"status": status})
        db.create_request_event(request_id, "dashboard_status_update", {"status": status, "status_label": REQUEST_STATUS_LABELS.get(status, status), "updated_by": session.get("dashboard_username") or "operator", "source": "dashboard_solicitudes", "updated_at": datetime.now(timezone.utc).isoformat()})
    except Exception:
        return jsonify({"error": "Unable to update request status"}), 503
    return jsonify({"ok": True, "request_id": request_id, "status": status, "status_label": REQUEST_STATUS_LABELS.get(status, status)})


@dashboard.post("/api/dashboard/profile-assignment")
@_login_required
def assign_profile_to_samples():
    payload = request.get_json(silent=True) or {}
    client_id = _normalize_uuid(payload.get("client_id"))
    items = payload.get("items") if isinstance(payload.get("items"), list) else []
    if not str(payload.get("client_id") or "").strip():
        return jsonify({"error": "Missing client_id"}), 400
    if not client_id:
        return jsonify({"error": "Invalid client_id"}), 400
    if not items:
        return jsonify({"error": "Missing items"}), 400

    priority = _normalize_priority(payload.get("priority")) or "normal"
    db_priority = _normalize_priority_db(priority)
    notes = _sanitize_text(payload.get("notes"), 600)
    now_iso = datetime.now(timezone.utc).isoformat()
    profiles = {str(row.get("code") or ""): row for row in _safe_fetch(lambda: db.list_catalog_profiles(limit=5000), [])}
    analyses = {str(row.get("code") or ""): row for row in _safe_fetch(lambda: db.list_catalog_tests(limit=5000), [])}
    selected_items = []
    sample_rows = []
    sample_requirements = []

    for item in items:
        item_type = str((item or {}).get("item_type") or "").strip()
        code = str((item or {}).get("code") or "").strip()
        row = profiles.get(code) if item_type == "profile" else analyses.get(code) if item_type == "analysis" else None
        if not row:
            return jsonify({"error": "Unsupported catalog item", "code": code}), 400
        sample_type = "Perfil personalizado" if item_type == "profile" else (row.get("sample") or "Sin muestra definida")
        if item_type == "analysis" and sample_type != "Sin muestra definida" and sample_type not in sample_requirements:
            sample_requirements.append(sample_type)
        selected = {
            "item_type": item_type,
            "code": code,
            "name": row.get("name") or "Sin nombre",
            "category": row.get("category") or "Sin categoria",
            "species": row.get("species") or "ambos",
            "sample_type": sample_type,
            "price": _price_value(row.get("price")),
            "source": _sanitize_text((item or {}).get("source"), 80),
            "included_from_profile_code": _sanitize_text((item or {}).get("included_from_profile_code"), 80),
        }
        selected_items.append(selected)
        sample_rows.append({
            "client_id": client_id,
"status": "pending_pickup",
            "priority": db_priority,
            "test_code": code,
            "test_name": selected["name"],
            "sample_type": sample_type,
            "source_system": "dashboard_profile_assignment",
            "source_reference": f"profile_assignment:{code}",
        })

    try:
        created_rows = db.insert_rows("lab_samples", sample_rows)
        event_payload = {
            "source": "dashboard_profile_assignment",
            "client_id": client_id,
            "selected_items": selected_items,
            "sample_requirements": sample_requirements,
            "priority": priority,
            "notes": notes,
            "assigned_by": session.get("dashboard_username") or "operator",
            "assigned_at": now_iso,
        }
        db.insert_rows("lab_sample_events", [
            {
                "sample_id": row.get("id"),
                "event_type": "profile_assigned_from_dashboard",
                "event_payload": {**event_payload, "assigned_item": selected_items[index]},
            }
            for index, row in enumerate(created_rows or [])
            if row.get("id")
        ])
    except Exception:
        return jsonify({"error": "Unable to assign profile to samples"}), 503
    return jsonify({"ok": True, "status": "pending_pickup", "created_count": len(created_rows or []), "sample_ids": [row.get("id") for row in created_rows or []]})


@dashboard.get("/api/dashboard/custom-profiles")
@_login_required
def list_custom_profiles():
    client_id = request.args.get("client_id", "").strip()
    try:
        profiles = db.list_custom_profiles(client_id=client_id or None, limit=200)
        for p in profiles:
            p["items_json"] = p.get("items_json") or []
        return jsonify({"ok": True, "profiles": profiles})
    except Exception:
        return jsonify({"ok": True, "profiles": [], "migration_required": True})


@dashboard.post("/api/dashboard/save-custom-profile")
@_login_required
def save_custom_profile():
    payload = request.get_json(silent=True) or {}
    client_id = str(payload.get("client_id") or "").strip()
    name = _sanitize_text(payload.get("name"), 200) or "Perfil personalizado"
    items = payload.get("items") or []
    if not client_id:
        return jsonify({"error": "Missing client_id"}), 400
    if not items:
        return jsonify({"error": "Missing items"}), 400
    try:
        profile = db.save_custom_profile({
            "client_id": client_id,
            "name": name,
            "items_json": items,
            "created_by": session.get("dashboard_username") or "operator",
        })
        profile["items_json"] = profile.get("items_json") or []
        return jsonify({"ok": True, "profile": profile})
    except Exception:
        return jsonify({"error": "Falta crear la tabla client_custom_profiles en Supabase"}), 503


@dashboard.post("/api/dashboard/delete-custom-profile")
@_login_required
def delete_custom_profile():
    payload = request.get_json(silent=True) or {}
    profile_id = str(payload.get("profile_id") or "").strip()
    if not profile_id:
        return jsonify({"error": "Missing profile_id"}), 400
    try:
        success = db.delete_custom_profile(profile_id)
        return jsonify({"ok": True, "deleted": success})
    except Exception:
        return jsonify({"error": "Unable to delete custom profile"}), 503


@dashboard.post("/api/dashboard/sample-status")
@_login_required
def update_sample_status():
    payload = request.get_json(silent=True) or {}
    sample_id = str(payload.get("sample_id") or "").strip()
    sample_seed = payload.get("sample_seed")
    status = _normalize_status(payload.get("status"))
    if status not in SAMPLE_STATUS_LABELS:
        return jsonify({"error": "Invalid sample status"}), 400
    if not sample_id and not isinstance(sample_seed, dict):
        return jsonify({"error": "Missing sample_id"}), 400

    now_iso = datetime.now(timezone.utc).isoformat()
    status_db = _sample_status_db_value(status)
    created_from_seed = False
    persistence_mode = "event_only"
    is_order = sample_id.startswith("order:")
    order_request_id = sample_id.replace("order:", "", 1) if is_order else None
    if is_order:
        sample_id = ""
    try:
        if is_order and order_request_id:
            request_status_map = {
                "pending_pickup": "received",
                "picked_up": "on_route",
                "received_lab": "in_lab",
                "in_lab": "in_lab",
                "processed": "processed",
                "sent": "sent",
            }
            new_request_status = request_status_map.get(status, status)
            db.update_request(order_request_id, {"status": new_request_status})
            try:
                db.create_request_event(order_request_id, "dashboard_status_update", {"status": new_request_status, "sample_status": status, "status_label": SAMPLE_STATUS_LABELS.get(status, status), "updated_by": session.get("dashboard_username") or "operator", "source": "dashboard_muestras", "updated_at": now_iso})
            except Exception:
                pass
            persistence_mode = "request_and_event"
        elif not sample_id and isinstance(sample_seed, dict):
            create_payload = {
                "status": status_db,
                "priority": _normalize_priority_db(_normalize_priority(sample_seed.get("priority")) or "normal"),
                "source_system": "dashboard_manual",
                "source_reference": _sanitize_text(sample_seed.get("seed_token"), 120) or "dashboard_seed",
            }
            optional_fields = {
                "request_id": _normalize_uuid(sample_seed.get("request_id")),
                "client_id": _normalize_uuid(sample_seed.get("client_id")),
                "sample_type": _sanitize_text(sample_seed.get("sample_type"), 80),
                "test_name": _sanitize_text(sample_seed.get("test_name"), 160),
            }
            create_payload.update({key: value for key, value in optional_fields.items() if value})
            created_rows = db.insert_rows("lab_samples", [create_payload])
            sample_id = str((created_rows[0] if created_rows else {}).get("id") or "").strip()
            if not sample_id:
                return jsonify({"error": "Unable to create sample"}), 503
            created_from_seed = True
            persistence_mode = "created_lab_sample_and_event" if status in SAMPLE_STATUS_DB_OPTIONS else "created_lab_sample_fallback_and_event"
        elif status in SAMPLE_STATUS_DB_OPTIONS:
            db.update_rows("lab_samples", {"id": sample_id}, {"status": status})
            persistence_mode = "lab_samples_and_event"

        if not is_order:
            db.insert_rows("lab_sample_events", [{
                "sample_id": sample_id,
                "event_type": "dashboard_status_update",
                "event_payload": {"status": status, "status_label": SAMPLE_STATUS_LABELS.get(status, status),
                "dropdown_status": _DROPDOWN_STATUS_MAP.get(status, status), "updated_by": session.get("dashboard_username") or "operator", "source": "dashboard_muestras", "persistence_mode": persistence_mode, "created_from_seed": created_from_seed, "status_db": status_db, "updated_at": now_iso},
            }])
    except Exception:
        return jsonify({"error": "Unable to update sample status"}), 503
    return jsonify({"ok": True, "sample_id": sample_id, "status": status, "status_label": SAMPLE_STATUS_LABELS.get(status, status),
            "dropdown_status": _DROPDOWN_STATUS_MAP.get(status, status), "persistence_mode": persistence_mode, "created_from_seed": created_from_seed})


def _geocode_address(address: str) -> tuple[float, float] | None:
    q = address + ", Bogota, Colombia"
    url = "https://nominatim.openstreetmap.org/search?q=" + urllib.request.quote(q) + "&format=json&limit=1&countrycodes=co"
    req = urllib.request.Request(url, headers={"User-Agent": "A3-Lab/1.0"})
    try:
        import time as _time
        _time.sleep(1.05)
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = _json.loads(resp.read())
            if data:
                return float(data[0]["lat"]), float(data[0]["lon"])
    except Exception:
        pass
    return None


def _nearest_locality(lat: float, lng: float) -> str | None:
    best = None
    best_dist = float("inf")
    for code, (la, lo) in BOGOTA_LOCALITY_COORDS.items():
        d = math.sqrt((lat - la) ** 2 + (lng - lo) ** 2)
        if d < best_dist:
            best_dist = d
            best = code
    return best


def _resolve_client_zone(
    client: dict,
    courier_by_name: dict,
    knowledge_by_name: dict,
    locality_keywords: dict,
) -> tuple[int | None, str]:
    addr = (client.get("address") or "").strip()
    zone = (client.get("zone") or "").strip()

    result = territory.suggest_zone_for_location(address=addr, zone=zone)
    if result.get("zone_number"):
        return result["zone_number"], "zona"

    name_key = _normalize_lookup_key(client.get("clinic_name"))
    k = knowledge_by_name.get(name_key, {})
    locality = k.get("locality")
    if locality:
        result = territory.suggest_zone_for_location(locality=locality, address=addr)
        if result.get("zone_number"):
            return result["zone_number"], "knowledge"

    text = _normalize_lookup_key(client.get("clinic_name", "") + " " + addr)
    for loc_key, zone_num in locality_keywords.items():
        if loc_key in text:
            return zone_num, "localidad"

    if locality:
        loc_key = _normalize_lookup_key(locality)
        for known_loc, zone_num in locality_keywords.items():
            if known_loc in loc_key or loc_key in known_loc:
                return zone_num, "knowledge_fuzzy"

    if addr and addr != "-":
        coords = _geocode_address(addr)
        if coords:
            loc_code = _nearest_locality(coords[0], coords[1])
            if loc_code:
                result = territory.suggest_zone_for_location(locality=loc_code)
                if result.get("zone_number"):
                    return result["zone_number"], "geocode"

    return None, "none"


@dashboard.post("/api/dashboard/suggest-couriers")
@_login_required
def suggest_couriers():
    clients = db.list_clients_with_assignment(limit=500)
    couriers = db.list_active_couriers(limit=500)
    courier_by_name = {_normalize_lookup_key(c["name"]): c for c in couriers if c.get("id") and c.get("name")}
    knowledge = _safe_fetch(lambda: db.list_a3_knowledge_index(limit=5000), [])
    knowledge_by_name = {}
    for k in knowledge:
        name_key = _normalize_lookup_key(k.get("clinic_name"))
        if name_key:
            knowledge_by_name[name_key] = k
    locality_keywords = {}
    for zone_num, locs in territory.ZONE_LOCALITIES.items():
        for _code, name, _count in locs:
            locality_keywords[_normalize_lookup_key(name)] = zone_num
    suggestions = []
    skipped = 0
    no_match = 0
    for client in clients:
        assignment = _assignment_from_client(client)
        if assignment and assignment.get("courier_id"):
            skipped += 1
            continue
        zone_number, method = _resolve_client_zone(client, courier_by_name, knowledge_by_name, locality_keywords)
        if not zone_number:
            no_match += 1
            continue
        courier_name = territory.ZONE_COURIERS.get(zone_number)
        courier = courier_by_name.get(_normalize_lookup_key(courier_name)) if courier_name else None
        if not courier:
            no_match += 1
            continue
        suggestions.append({
            "client_id": str(client["id"]),
            "clinic_name": client.get("clinic_name") or "",
            "courier_id": str(courier["id"]),
            "courier_name": courier["name"],
            "zone_number": zone_number,
            "method": method,
        })
    return jsonify({"ok": True, "suggestions": suggestions, "skipped": skipped, "no_match": no_match})


@dashboard.post("/api/dashboard/confirm-suggested-assignments")
@_login_required
def confirm_suggested_assignments():
    payload = request.get_json(silent=True) or {}
    assignments = payload.get("assignments") if isinstance(payload.get("assignments"), list) else []
    if not assignments:
        return jsonify({"error": "Missing assignments"}), 400
    confirmed = 0
    errors = 0
    for item in assignments:
        client_id = str(item.get("client_id") or "").strip()
        courier_id = str(item.get("courier_id") or "").strip()
        if not client_id or not courier_id:
            errors += 1
            continue
        try:
            db.upsert_client_assignment(
                client_id=client_id,
                courier_id=courier_id,
                assigned_by=f"dashboard:suggested:{session.get('dashboard_username') or 'operator'}",
            )
            confirmed += 1
        except Exception:
            errors += 1
    return jsonify({"ok": True, "confirmed": confirmed, "errors": errors})


@dashboard.get("/api/dashboard/overview")
@_login_required
def dashboard_overview():
    return jsonify(build_dashboard_context())


def _render_dashboard(active_tab: str):
    context = _empty_context()
    loaded = build_dashboard_context()
    context.update(loaded)
    summary = _empty_context()["summary"]
    summary.update(loaded.get("summary", {}))
    context["summary"] = summary
    if active_tab == "muestras" and request.args.get("demo") in {"1", "true", "si"}:
        demo_lanes = _demo_sample_process_lanes()
        context["demo_mode"] = True
        context["sample_process_lanes"] = demo_lanes
        context["sample_demo_total"] = sum(lane["count"] for lane in demo_lanes)
    return render_template(
        "dashboard.html",
        active_tab=active_tab,
        context=context,
        username=session.get("dashboard_username", "admin"),
        notice=(request.args.get("notice") or "").strip(),
        notice_type=(request.args.get("notice_type") or "info").strip(),
    )
