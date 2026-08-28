import csv
import hashlib
import io
import json as _json
import math
import re
import urllib.request
from collections import Counter
from datetime import date, datetime, timezone
from functools import wraps

from flask import Blueprint, Response, abort, jsonify, redirect, render_template, request, session, url_for

from app.config import (
    ALEGRA_ENABLED,
    APP_TIMEZONE,
    ALEGRA_PRODUCTION,
    ANARVET_ENABLED,
    DASHBOARD_ADMIN_PASSWORD,
    DASHBOARD_ADMIN_USER,
    DISCOUNT_TIERS,
)
from app import billing_charts, client_filters, demo_data
from app.services import db, alegra
from app import anarvet_sync, dashboard_metrics, orders, pricing, territory, billing

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
        "catalog_species_options": sorted(_CATALOG_SPECIES),
        "discount_tiers_rows": [{"min_tests": m, "pct": p} for m, p in DISCOUNT_TIERS],
        "exec_tat_avg_hours": None,
        "exec_tat_count": 0,
        "exec_tat_stages": [],
        "exec_requests_daily": [],
        "exec_tat_weekly": [],
        "sample_requirements": [],
        "approval_rows": [],
        "reviewed_approval_rows": [],
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


def _index_professionals(professional_rows: list[dict] | None) -> dict[str, list[dict]]:
    """Agrupa los médicos por clinic_key para colgarlos de la ficha de cada cliente."""
    grouped: dict[str, list[dict]] = {}
    for row in professional_rows or []:
        key = str(row.get("clinic_key") or "").strip()
        name = str(row.get("professional_name") or "").strip()
        if not key or not name:
            continue
        bucket = grouped.setdefault(key, [])
        if not any(item["name"] == name for item in bucket):  # el mismo médico llega de varios Excel
            bucket.append({"name": name, "card": row.get("professional_card") or ""})
    return grouped


def _build_client_rows(clients: list[dict], requests_rows: list[dict], samples: list[dict], knowledge_rows: list[dict] | None = None, pending_request_by_client: dict | None = None, professional_rows: list[dict] | None = None) -> list[dict]:
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

    professionals_by_clinic = _index_professionals(professional_rows)

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
        # La facturación electrónica sale de `clients`, no de la ficha de knowledge: es la
        # columna que lee la facturación al decidir si emite al NIT del cliente o a
        # Consumidor Final (migración 028). La de knowledge quedó siempre vacía.
        electronic_option = _bool_option(client.get("electronic_invoice"))
        entered_option = _bool_option(knowledge.get("entered_flag"))
        raw_zone = client.get("zone") or ""
        zone_display = _resolve_zone_display(raw_zone)
        row_clinic_key = knowledge.get("clinic_key") or _normalize_lookup_key(clinic_name)
        doctors = professionals_by_clinic.get(row_clinic_key, [])
        rows.append({
            "client_id": client_id,
            "clinic_key": row_clinic_key,
            "doctors": doctors,
            "doctors_label": ", ".join(d["name"] for d in doctors) if doctors else "-",
            "clinic_name": clinic_name,
            "display_name": display_name,
            "secondary_name": secondary_name,
            "commercial_name": commercial_name or "-",
            "client_code": knowledge.get("client_code") or client.get("external_code") or "-",
            "client_type": knowledge.get("client_type") or "",
            "tax_id": client.get("tax_id") or "-",
            "phone": client.get("phone") or "-",
            # `clients.email` es el que se manda a Alegra al facturar; knowledge es el anexo.
            "email": knowledge.get("email") or client.get("email") or knowledge.get("contact_email") or "-",
            "billing_email": knowledge.get("billing_email") or "-",
            "vat_regime": knowledge.get("vat_regime") or "",
            "electronic_invoicing_option": electronic_option,
            "invoice_note": client.get("invoice_note") or "",
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
            "pending_request_id": (pending_request_by_client or {}).get(client_id),
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


def _service_order_items(payload: dict) -> list[dict]:
    """Análisis de la orden con su código y su valor, como en la orden de servicio en papel:
    `Cód | Descripción | Valor`, una fila por análisis.

    El bloque `service_order` del evento nunca guardó importes —solo `exam_type` como texto—,
    así que se leen del `profile` hermano, que sí los tiene resueltos contra el catálogo.
    """
    perfil = payload.get("profile") if isinstance(payload.get("profile"), dict) else {}
    if not perfil:
        return []
    items: list[dict] = []
    base = perfil.get("base_profile") or {}
    # Un perfil PERSONALIZADO no tiene código ni precio propio: su valor son las pruebas
    # sueltas, que ya se listan abajo una por una. Incluirlo agregaba una fila con el nombre
    # largo ("Perfil personalizado: 1201 PT…, 1202 PTT…") y la columna Valor vacía.
    if (base.get("code") or base.get("name")) and (base.get("code") or int(base.get("price") or 0)):
        items.append({"code": base.get("code") or "", "name": base.get("name") or "",
                      "price": int(base.get("price") or 0)})
    for extra in (perfil.get("extra_profiles") or []):
        items.append({"code": extra.get("code") or "", "name": extra.get("name") or "",
                      "price": int(extra.get("price") or 0)})
    for test in (perfil.get("added_tests") or []):
        items.append({"code": test.get("code") or "", "name": test.get("name") or "",
                      "price": int(test.get("price") or 0)})
    return items


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
            # La declara el cliente en el chat; NO es la fecha de recogida del motorizado.
            "sample_taken_date": service_order.get("sample_taken_date") or "",
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
            # Ítems con CÓDIGO y VALOR para la orden imprimible. Salen del `profile` hermano
            # del mismo evento, que ya los guarda resueltos contra el catálogo: el bloque
            # `service_order` nunca tuvo importes, y por eso el PDF venía imprimiendo la
            # forma de pago en la columna "Valor" y con una sola fila fija.
            "items": _service_order_items(payload),
            "items_total": sum(int(i.get("price") or 0) for i in _service_order_items(payload)),
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

    # KPIs operativos adicionales (estado acumulado)
    request_status_counter = Counter((row.get("status") or "unknown") for row in requests_rows)
    received_total = request_status_counter.get("received", 0)
    assigned_total = request_status_counter.get("assigned", 0)
    results_emitted = request_status_counter.get("processed", 0) + request_status_counter.get("sent", 0)
    unassigned_orders = [
        order for order in (service_orders or [])
        if (order.get("courier_name") or "Sin asignar") == "Sin asignar"
        and order.get("status") not in ("cancelled", "sent")
    ]

    return {
        "kpis": {
            "active_routes": len(route_rows),
            "pending_approvals": len(approval_rows),
            "pending_samples": sum(sample_status.get(status, 0) for status in sample_pending_statuses),
            "critical_alerts": len(alerts),
            "received_total": received_total,
            "assigned_total": assigned_total,
            "results_emitted": results_emitted,
            "total_orders": len(service_orders or []),
        },
        "alerts": alerts[:8],
        "route_rows": route_rows[:12],
        "courier_agenda": courier_agenda,
        "service_order_rows": (service_orders or [])[:15],
        "unassigned_orders": unassigned_orders[:20],
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


INVOICES_PER_PAGE = 15
INVOICE_STATUS_OPTIONS = [{"value": key, "label": label} for key, label in {
    "draft": "Borrador", "open": "Abierta", "closed": "Pagada", "void": "Anulada",
}.items()]


def _invoice_cache_payload(row: dict, raw: dict) -> dict:
    """Traduce la fila mapeada (billing.invoice_to_row) a las columnas del cache."""
    return {
        "alegra_invoice_id": row["invoice_id"],
        "number": row["number"],
        "client_nit": row["client_nit"],
        "client_name": row["client_name"],
        "document_type": row["document_type"],
        "number_template": row["number_template"],
        "status": row["status"],
        "subtotal": row["subtotal"],
        "tax": row["tax"],
        "total": row["total"],
        "balance": row.get("balance", 0),
        "total_paid": row.get("total_paid", 0),
        "is_stamped": row["is_stamped"],
        "invoice_date": row["date"] if row["date"] != "-" else None,
        "due_date": row["due_date"] if row["due_date"] != "-" else None,
        "request_id": row["request_id"] or None,
        "origin": row["origin"],
        "raw": raw,
        "synced_at": datetime.now(timezone.utc).isoformat(),
    }


def _build_cartera_context(top: int = 25) -> dict:
    """Cartera para el módulo Facturación: cuánto se facturó, cuánto entró y cuánto falta
    cobrar, con el detalle por cliente. Sale del cache; los pagos se registran en Alegra."""
    rows = _safe_fetch(lambda: db.list_cartera(), [])
    totales = db.cartera_totales(rows)
    por_cliente = db.cartera_por_cliente(rows)
    hoy = datetime.now(APP_TIMEZONE).date()
    for item in por_cliente:
        vence = item.get("vence_primero")
        item["dias_mora"] = (hoy - date.fromisoformat(vence)).days if vence else 0
    return {
        "cartera_totales": totales,
        "cartera_clientes": por_cliente[:top],
        "cartera_clientes_total": len(por_cliente),
        "cartera_deudores": sum(1 for c in por_cliente if c["por_cobrar"] > 0),
    }


def _invoice_event_index() -> dict:
    """Cruza facturas de Alegra con la orden de servicio que las generó, usando el evento
    `alegra_invoiced` que el agente guarda en request_events (ver guardrails)."""
    events = _safe_fetch(lambda: db.fetch_rows("request_events", "request_id, event_type, event_payload", 4000), [])
    index = {}
    for event in events:
        if event.get("event_type") != "alegra_invoiced":
            continue
        payload = event.get("event_payload") if isinstance(event.get("event_payload"), dict) else {}
        invoice_id = str(payload.get("invoice_id") or "")
        if invoice_id:
            index[invoice_id] = {
                "request_id": str(event.get("request_id") or ""),
                "origin": payload.get("updated_by") or payload.get("source") or "Agente",
            }
    return index


def _sync_invoices_from_alegra(max_pages: int = 60, per_page: int = 30) -> dict:
    """Lee facturas de Alegra (solo lectura) y refresca el cache. No emite ni envía nada."""
    event_index = _invoice_event_index()
    synced = 0
    errors: list[str] = []
    for page in range(max_pages):
        try:
            batch = alegra.list_invoices(start=page * per_page, limit=per_page)
        except alegra.AlegraError as exc:
            errors.append(str(exc))
            break
        if not batch:
            break
        rows = []
        for invoice in batch:
            invoice_id = str(invoice.get("id") or "")
            if not invoice_id:
                continue
            meta = event_index.get(invoice_id, {})
            mapped = billing.invoice_to_row(invoice, request_id=meta.get("request_id"), origin=meta.get("origin"))
            rows.append(_invoice_cache_payload(mapped, invoice))
        if rows:
            synced += db.upsert_invoices_cache(rows)
        if len(batch) < per_page:
            break
    return {"synced": synced, "errors": errors}


def _parse_invoice_filters(args) -> dict:
    """Normaliza los filtros del módulo Facturación desde request.args."""
    def _money(value):
        text = re.sub(r"[^\d]", "", str(value or ""))
        return int(text) if text else None

    return {
        "search": _sanitize_text(args.get("search"), 80),
        "status": _sanitize_text(args.get("status"), 20),
        "document_type": _sanitize_text(args.get("document_type"), 60),
        "client_nit": _sanitize_text(args.get("client_nit"), 40),
        "number": _sanitize_text(args.get("number"), 40),
        "date_from": _sanitize_text(args.get("date_from"), 10),
        "date_to": _sanitize_text(args.get("date_to"), 10),
        "total_min": _money(args.get("total_min")),
        "total_max": _money(args.get("total_max")),
    }


def _compute_invoice_metrics(rows: list[dict]) -> dict:
    """Métricas del panel superior calculadas sobre el cache (no emite nada)."""
    today = datetime.now(timezone.utc).date().isoformat()
    month_prefix = today[:7]
    year_prefix = today[:4]
    count = len(rows)
    total_all = sum(int(row.get("total") or 0) for row in rows)
    by_client = Counter()
    today_count = month_total = year_total = 0
    for row in rows:
        invoice_date = str(row.get("invoice_date") or "")
        total = int(row.get("total") or 0)
        if invoice_date[:10] == today:
            today_count += 1
        if invoice_date[:7] == month_prefix:
            month_total += total
        if invoice_date[:4] == year_prefix:
            year_total += total
        by_client[row.get("client_name") or "Sin cliente"] += total
    top_clients = [{"name": name, "total": value} for name, value in by_client.most_common(5)]
    return {
        "today_count": today_count,
        "month_total": month_total,
        "year_total": year_total,
        "invoices_count": count,
        "avg_ticket": round(total_all / count) if count else 0,
        "top_clients": top_clients,
    }


def _build_invoices_context(page: int = 1, filters: dict | None = None, order_field: str = "invoice_date", order_desc: bool = True) -> dict:
    rows, total = _safe_fetch(
        lambda: db.list_cached_invoices(filters, page=page, per_page=INVOICES_PER_PAGE, order_field=order_field, order_desc=order_desc),
        ([], 0),
    )
    metrics_rows = _safe_fetch(lambda: db.list_all_cached_invoices("total, invoice_date, client_name"), [])
    pages = max((total + INVOICES_PER_PAGE - 1) // INVOICES_PER_PAGE, 1)
    return {
        "invoices_rows": rows,
        "invoices_total": total,
        "invoices_page": page,
        "invoices_pages": pages,
        "invoices_metrics": _compute_invoice_metrics(metrics_rows),
        "invoice_status_options": INVOICE_STATUS_OPTIONS,
        "invoices_actions_locked": not ALEGRA_PRODUCTION,
        "alegra_enabled": ALEGRA_ENABLED,
    }


def _money_fmt(value) -> str:
    """Formatea un entero como peso colombiano: $ 1.234.567"""
    return f"$ {int(value or 0):,}".replace(",", ".")


def _build_executive_panel(requests_rows: list, request_events: list) -> dict:
    """Métricas adicionales del Panel Ejecutivo. No hace queries extra."""
    from datetime import timedelta
    today_str = datetime.now(timezone.utc).date().isoformat()
    week_ago_str = (datetime.now(timezone.utc).date() - timedelta(days=7)).isoformat()
    active_statuses_exec = {
        "received", "assigned", "on_route", "picked_up", "in_lab", "processed", "error_pending_assignment",
    }

    # Alertas: activas sin motorizado
    alerts = []
    for row in requests_rows:
        status = row.get("status") or ""
        if status not in active_statuses_exec:
            continue
        courier = row.get("couriers") if isinstance(row.get("couriers"), dict) else {}
        if not courier.get("name") and not row.get("assigned_courier_id"):
            client = row.get("clients") if isinstance(row.get("clients"), dict) else {}
            alerts.append({
                "clinic_name": client.get("clinic_name") or "-",
                "order_number": row.get("order_number") or "-",
                "status": status,
            })

    # Procesadas esta semana
    processed_week = sum(
        1 for r in requests_rows
        if r.get("status") == "processed"
        and (r.get("requested_at") or "")[:10] >= week_ago_str
    )

    # Tasa de cancelación histórica
    total_req = len(requests_rows)
    cancelled = sum(1 for r in requests_rows if r.get("status") == "cancelled")
    cancel_rate = round(cancelled / total_req * 100) if total_req > 0 else 0

    # Carga activa por motorizado
    courier_load: dict[str, int] = {}
    for row in requests_rows:
        if (row.get("status") or "") not in active_statuses_exec:
            continue
        courier = row.get("couriers") if isinstance(row.get("couriers"), dict) else {}
        name = courier.get("name")
        if name:
            courier_load[name] = courier_load.get(name, 0) + 1
    courier_load_rows = sorted(
        [{"name": k, "count": v} for k, v in courier_load.items()],
        key=lambda x: -x["count"],
    )[:6]

    # Top clientes por volumen de solicitudes
    client_req: dict[str, int] = {}
    for row in requests_rows:
        client = row.get("clients") if isinstance(row.get("clients"), dict) else {}
        name = client.get("clinic_name") or "Desconocido"
        client_req[name] = client_req.get(name, 0) + 1
    top_clients_req = sorted(
        [{"name": k, "count": v} for k, v in client_req.items()],
        key=lambda x: -x["count"],
    )[:5]

    # Feed de actividad reciente
    _ev_labels: dict[str, tuple[str, str]] = {
        "created":                      ("Solicitud creada",      "file-plus"),
        "status_updated":               ("Estado actualizado",    "refresh-cw"),
        "service_order_generated":      ("Orden generada",        "clipboard-list"),
        "alegra_invoiced":              ("Factura creada",        "receipt"),
        "client_review_approved":       ("Cliente aprobado",      "user-check"),
        "client_review_rejected":       ("Cliente rechazado",     "user-x"),
        "dashboard_request_manual_update": ("Actualización manual", "edit"),
    }
    activity = []
    for ev in sorted(request_events, key=lambda e: e.get("created_at") or "", reverse=True)[:12]:
        payload = ev.get("event_payload") if isinstance(ev.get("event_payload"), dict) else {}
        so = payload.get("service_order") if isinstance(payload.get("service_order"), dict) else {}
        ev_type = ev.get("event_type") or "evento"
        label, icon = _ev_labels.get(ev_type, ("Evento del sistema", "activity"))
        activity.append({
            "event_type": ev_type,
            "label": label,
            "icon": icon,
            "clinic_name": so.get("clinic_name") or payload.get("clinic_name") or "—",
            "created_at": str(ev.get("created_at") or "")[:16].replace("T", " "),
        })

    return {
        "exec_alerts":        alerts[:5],
        "exec_alerts_count":  len(alerts),
        "exec_processed_week": processed_week,
        "exec_cancel_rate":   cancel_rate,
        "exec_courier_load":  courier_load_rows,
        "exec_top_clients_req": top_clients_req,
        "exec_activity":      activity,
    }


def build_dashboard_context(billing_period: str = "auto") -> dict:
    try:
        clients = db.list_clients_with_assignment()
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
    professionals = _safe_fetch(lambda: db.list_client_professionals(limit=5000), [])
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
    pending_reviews = _safe_fetch(lambda: db.list_pending_client_reviews(limit=300), [])
    pending_request_by_client = {
        str(row["client_id"]): row["id"] for row in pending_reviews if row.get("client_id")
    }
    approval_rows, reviewed_rows = _build_approval_rows(sessions_rows)
    approval_rows.extend(_build_request_approval_rows(pending_reviews))
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
        "clients_rows": _build_client_rows(clients, requests_rows, samples, knowledge, pending_request_by_client, professionals),
        "catalog_rows": _build_catalog_rows(catalog),
        "profile_catalog_rows": profile_rows,
        "profile_analysis_rows": analysis_rows,
        "profile_builder_items": builder_items,
        "custom_profiles": _safe_fetch(lambda: db.list_custom_profiles(limit=100), []),
        "profile_categories": sorted({row["category"] for row in builder_items if row.get("category")}),
        "profile_species": sorted({row["species"] for row in builder_items if row.get("species")}),
        "catalog_species_options": sorted(_CATALOG_SPECIES),
        "discount_tiers_rows": [{"min_tests": m, "pct": p} for m, p in pricing.get_discount_tiers()],
        "sample_requirements": sorted({row["sample"] for row in analysis_rows if row.get("sample") and row.get("sample") != "Sin muestra definida"}),
        "approval_rows": approval_rows,
        "reviewed_approval_rows": reviewed_rows,
        "operation_center": operation_center,
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

    # Panel Ejecutivo — métricas adicionales
    exec_data = _build_executive_panel(requests_rows, request_events)
    context.update(exec_data)
    context.update(dashboard_metrics.build_tat_and_trends(requests_rows, request_events))
    _billing_rows = _safe_fetch(
        lambda: db.list_all_cached_invoices("total, balance, invoice_date, client_name"), [])
    _raw_billing = _compute_invoice_metrics(_billing_rows)
    # Serie de los últimos 12 meses para el gráfico del Panel (facturado, cobrado y deuda).
    context["exec_billing_chart"] = billing_charts.chart_data(_billing_rows, periodo=billing_period)
    context["exec_billing"] = {
        **_raw_billing,
        "month_total_fmt": _money_fmt(_raw_billing.get("month_total", 0)),
        "year_total_fmt":  _money_fmt(_raw_billing.get("year_total", 0)),
        "avg_ticket_fmt":  _money_fmt(_raw_billing.get("avg_ticket", 0)),
    }
    context["alegra_enabled"] = ALEGRA_ENABLED
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
        return redirect(url_for("dashboard.clients_page", notice="Cliente enviado a revision", notice_type="ok"))

    return render_template("new_client.html", error=None, form={}, **template_context)


@dashboard.route("/solicitudes/nueva", methods=["GET", "POST"])
@_login_required
def new_request_page():
    """Cargar una orden desde el laboratorio: el cliente llamó por teléfono o vino en persona.

    A3 lo preguntó en la llamada del 21/08 ("si lo hace por teléfono o va presencialmente,
    ¿cómo lo hacemos?"). Hasta ahora una orden solo nacía por el chat o por el portal, que
    exige la sesión del propio cliente; el personal no tenía por dónde.

    Usa la MISMA traducción de catálogo que el portal —`orders.resolve_catalog_selection`,
    donde el código y el precio salen siempre de la base (ERR-097)— y el mismo
    `db.create_request`, para no abrir una segunda verdad sobre el dinero. La diferencia real
    es que acá el cliente se ELIGE, en vez de salir de la sesión."""
    catalog = {
        "profiles": _safe_fetch(lambda: db.list_catalog_profiles(), []),
        "tests": _safe_fetch(lambda: db.list_catalog_tests(limit=5000), []),
    }
    clients = _safe_fetch(lambda: db.list_clients_with_assignment(limit=5000), [])

    def _render(error=None, form=None, selected=None):
        return render_template(
            "new_request.html", error=error, form=form or {}, catalog=catalog,
            clients=clients, selected_test_codes=selected or [],
            selected_profile_codes=(form or {}).getlist("profile_codes") if hasattr(form, "getlist") else [],
            payment_options=orders.PAYMENT_METHOD_OPTIONS, active_tab="solicitudes",
        )

    if request.method != "POST":
        return _render()

    form = request.form
    client_id = (form.get("client_id") or "").strip()
    client = db.get_client_by_id(client_id) if client_id else None
    if not client:
        return _render("Elige la veterinaria a la que pertenece la orden.", form)

    fields = {
        key: (form.get(key) or "").strip() or None
        for key in (
            "requesting_doctor", "patient_name", "species", "breed", "sex",
            "patient_age", "owner_name", "sample_taken_date", "pickup_address",
            "observations", "payment_method",
        )
    }
    selected_test_codes = form.getlist("test_codes")
    selected_profile_codes = [c.strip() for c in form.getlist("profile_codes") if c.strip()]
    if not selected_profile_codes and (form.get("profile_code") or "").strip():
        selected_profile_codes = [form["profile_code"].strip()]
    fields.update(orders.resolve_catalog_selection(selected_profile_codes, selected_test_codes))

    if not fields.get("patient_name") or not fields.get("exam_type"):
        return _render("Indica el paciente y al menos un perfil o análisis del catálogo.",
                       form, selected_test_codes)

    fields["pickup_address"] = fields["pickup_address"] or client.get("address")
    fields["clinic_name"] = client.get("clinic_name")
    fields["clinic_phone"] = client.get("phone")
    fields["observations"] = fields["observations"] or "sin observaciones"

    created = db.create_request(
        chat_id=f"dashboard:{session.get('dashboard_username') or 'staff'}",
        session={"client_id": client_id, "channel": "telegram"},
        ai_response={"intent": "route_scheduling", "captured_fields": fields},
    )
    if not created:
        return _render("No se pudo registrar la orden, intenta de nuevo.", form,
                       selected_test_codes)

    numero = created.get("order_number") or "sin número"
    return redirect(url_for("dashboard.requests_page",
                            notice=f"Orden {numero} registrada para {client.get('clinic_name')}",
                            notice_type="ok"))


@dashboard.get("/solicitudes")
@_login_required
def requests_page():
    return _render_dashboard("solicitudes")


@dashboard.get("/muestras")
@_login_required
def samples_page():
    return _render_dashboard("muestras")


@dashboard.get("/pedidos")
@_login_required
def pedidos_page():
    return _render_dashboard("pedidos")


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
    return redirect(url_for("dashboard.clients_page", notice=message, notice_type="ok" if ok else "error"))


@dashboard.get("/motorizados")
@_login_required
def motorizados_page():
    return _render_dashboard("motorizados")


@dashboard.get("/facturacion")
@_login_required
def billing_page():
    return _render_dashboard("facturacion")


@dashboard.get("/api/dashboard/invoices")
@_login_required
def api_list_invoices():
    try:
        page = max(1, int(request.args.get("page", 1)))
    except (TypeError, ValueError):
        page = 1
    filters = _parse_invoice_filters(request.args)
    order_field = request.args.get("order_field") or "invoice_date"
    order_desc = (request.args.get("order_dir") or "desc").lower() != "asc"
    rows, total = _safe_fetch(
        lambda: db.list_cached_invoices(filters, page=page, per_page=INVOICES_PER_PAGE, order_field=order_field, order_desc=order_desc),
        ([], 0),
    )
    pages = max((total + INVOICES_PER_PAGE - 1) // INVOICES_PER_PAGE, 1)
    return jsonify({"rows": rows, "total": total, "page": page, "pages": pages})


@dashboard.get("/api/dashboard/invoices/<invoice_id>")
@_login_required
def api_invoice_detail(invoice_id: str):
    invoice_id = str(invoice_id or "").strip()
    if not invoice_id:
        return jsonify({"error": "Missing invoice_id"}), 400
    # Detalle read-through a Alegra cuando está habilitado; si no, cae al cache local.
    if ALEGRA_ENABLED:
        try:
            invoice = alegra.get_invoice(invoice_id)
            return jsonify({"source": "alegra", "invoice": invoice, "pdf_url": alegra.get_invoice_pdf_url(invoice)})
        except alegra.AlegraError as exc:
            return jsonify({"error": str(exc)}), 502
    cached = _safe_fetch(lambda: db.get_cached_invoice(invoice_id), None)
    if not cached:
        return jsonify({"error": "Invoice not found in cache"}), 404
    return jsonify({"source": "cache", "invoice": cached.get("raw") or cached})


@dashboard.post("/api/dashboard/invoices/sync")
@_login_required
def api_sync_invoices():
    if not ALEGRA_ENABLED:
        return jsonify({"error": "Alegra deshabilitado (ALEGRA_ENABLED=false)"}), 400
    try:
        result = _sync_invoices_from_alegra()
    except Exception as exc:
        return jsonify({"error": f"Sync falló: {exc}"}), 503
    status = 200 if not result["errors"] else 207
    return jsonify({"ok": not result["errors"], **result}), status


# --------------------------- Espejo Anarvet (decisión 013) ---------------------------

@dashboard.post("/api/dashboard/anarvet/sync")
@_login_required
def api_anarvet_sync():
    """Vuelca fn_reporte_examenes al espejo local. Solo lectura contra Anarvet."""
    if not ANARVET_ENABLED:
        return jsonify({"error": "Anarvet deshabilitado (ANARVET_ENABLED=false)"}), 400
    payload = request.get_json(silent=True) or {}
    try:
        result = anarvet_sync.sync_results(payload.get("desde"), payload.get("hasta"))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": f"Sync falló: {exc}"}), 503
    status = 200 if not result["errors"] else 207
    return jsonify({"ok": not result["errors"], **result}), status


@dashboard.get("/api/dashboard/anarvet/clients")
@_login_required
def api_anarvet_clients():
    """Mapeo cod_cliente Anarvet → clients; ?status=pending filtra por estado."""
    if not ANARVET_ENABLED:
        return jsonify({"error": "Anarvet deshabilitado (ANARVET_ENABLED=false)"}), 400
    status = (request.args.get("status") or "").strip() or None
    return jsonify({"clients": db.list_anarvet_client_map(status)})


@dashboard.post("/api/dashboard/anarvet/clients/<cod_cliente>/assign")
@_login_required
def api_anarvet_assign(cod_cliente: str):
    """Asigna a mano un cod_cliente de Anarvet a un cliente nuestro.
    Body {"client_id": "..."} → manual; {"client_id": null} → sin correspondencia."""
    if not ANARVET_ENABLED:
        return jsonify({"error": "Anarvet deshabilitado (ANARVET_ENABLED=false)"}), 400
    payload = request.get_json(silent=True) or {}
    client_id = (payload.get("client_id") or "").strip() or None
    if client_id:
        if not db.get_client_by_id(client_id):
            return jsonify({"error": f"Cliente {client_id} no existe"}), 404
        db.assign_anarvet_client(cod_cliente, client_id, "manual")
    else:
        db.assign_anarvet_client(cod_cliente, None, "none")
    return jsonify({"ok": True})


@dashboard.post("/api/dashboard/anarvet/clients/automatch")
@_login_required
def api_anarvet_automatch():
    """Empareja de una sola vez los códigos que tienen UN destino inequívoco.

    Solo asigna cuando el nombre normalizado apunta a un único cliente activo. Con dos o
    más candidatos no elige: un mapeo errado le mostraría los resultados de un paciente a
    la veterinaria equivocada. Esos quedan pendientes para que alguien decida.
    """
    if not ANARVET_ENABLED:
        return jsonify({"error": "Anarvet deshabilitado (ANARVET_ENABLED=false)"}), 400
    from app import anarvet_map

    pendientes = db.list_anarvet_client_map(status="pending")
    clientes = db.list_clients_with_assignment()
    plan = anarvet_map.planificar(pendientes, clientes)

    aplicados, errores = 0, []
    for entrada in plan["automaticos"]:
        cod = entrada["pendiente"].get("cod_cliente")
        try:
            db.assign_anarvet_client(cod, entrada["cliente"]["id"], "auto")
            aplicados += 1
        except Exception as exc:  # una fila que falla no aborta el resto
            errores.append(f"{cod}: {exc}")
    return jsonify({
        "ok": not errores,
        "aplicados": aplicados,
        "ambiguos": len(plan["ambiguos"]),
        "sin_candidato": len(plan["sin_candidato"]),
        "errors": errores,
    }), (207 if errores else 200)


@dashboard.get("/api/dashboard/invoices/export")
@_login_required
def api_export_invoices():
    fmt = (request.args.get("format") or "csv").lower()
    filters = _parse_invoice_filters(request.args)
    rows, _total = _safe_fetch(
        lambda: db.list_cached_invoices(filters, page=1, per_page=10000),
        ([], 0),
    )
    columns = [
        ("number", "Numero"), ("invoice_date", "Fecha"), ("client_name", "Cliente"),
        ("client_nit", "NIT"), ("document_type", "Tipo documento"), ("subtotal", "Neto"),
        ("tax", "IVA"), ("total", "Total"), ("status", "Estado"), ("request_id", "Orden"),
    ]
    output = io.StringIO()
    writer = csv.writer(output, delimiter=";" if fmt == "xlsx" else ",")
    writer.writerow([label for _key, label in columns])
    for row in rows:
        writer.writerow([row.get(key, "") for key, _label in columns])
    payload = output.getvalue()
    # "Excel": CSV con BOM y separador ';' que Excel-ES abre en columnas sin asistente.
    if fmt == "xlsx":
        payload = "﻿" + payload
        filename, mimetype = "facturas.csv", "application/vnd.ms-excel; charset=utf-8"
    else:
        filename, mimetype = "facturas.csv", "text/csv; charset=utf-8"
    return Response(
        payload,
        mimetype=mimetype,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


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


@dashboard.get("/api/dashboard/column-prefs")
@_login_required
def get_column_prefs():
    user_key = session.get("dashboard_username") or "operator"
    rows = _safe_fetch(lambda: db.list_column_prefs(user_key), [])
    prefs = {
        str(row.get("table_id")): row.get("prefs") or {}
        for row in rows
        if row.get("table_id")
    }
    return jsonify({"prefs": prefs})


@dashboard.post("/api/dashboard/column-prefs")
@_login_required
def save_column_prefs():
    payload = request.get_json(silent=True) or {}
    table_id = str(payload.get("table_id") or "").strip()
    prefs = payload.get("prefs")
    if not table_id or not isinstance(prefs, dict):
        return jsonify({"error": "Missing table_id or prefs"}), 400
    visible = prefs.get("visible")
    order = prefs.get("order")
    if not isinstance(visible, list) or not isinstance(order, list):
        return jsonify({"error": "Invalid prefs"}), 400
    clean = {
        "visible": [str(slug)[:60] for slug in visible[:80]],
        "order": [str(slug)[:60] for slug in order[:80]],
    }
    user_key = session.get("dashboard_username") or "operator"
    try:
        db.upsert_column_prefs(user_key, table_id[:60], clean)
    except Exception:
        return jsonify({"error": "Unable to save column preferences"}), 503
    return jsonify({"ok": True, "table_id": table_id})


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
    allowed_client_fields = {"clinic_name", "phone", "address", "zone", "billing_type", "tax_id", "is_active",
                             "electronic_invoicing", "invoice_note"}
    allowed_profile_fields = {"client_code", "commercial_name", "client_type", "email", "billing_email", "vat_regime", "invoicing_rut_url", "observations", "entered_flag"}
    if not client_id and not clinic_key:
        return jsonify({"error": "Missing client_id"}), 400
    if field not in allowed_client_fields and field not in allowed_profile_fields:
        return jsonify({"error": "Unsupported field"}), 400
    try:
        if field in allowed_client_fields:
            update_payload = {field: value}
            if field == "is_active":
                update_payload = {field: value is True or str(value).lower() == "true"}
            elif field == "electronic_invoicing":
                # La columna de `clients` se llama electronic_invoice; el selector del
                # dashboard manda si/no. Sin dato = sí lleva, que es el default seguro.
                update_payload = {"electronic_invoice": _bool_option(value) != "no"}
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


_CATALOG_TABLES = {"analisis": "catalog_tests", "perfil": "catalog_profiles"}
# 'ambos' = disponible para todas las especies. Cualquier otro valor marca el ítem como
# EXCLUSIVO de esa especie (decisión 012): así A3 puede reclasificar sus 73 perfiles sin
# depender de nosotros.
_CATALOG_SPECIES = {"ambos", "canino", "felino", "bovino", "equino", "porcino",
                    "ovino", "caprino", "conejo", "ave", "roedor", "reptil"}


@dashboard.post("/api/dashboard/pedido-close")
@_login_required
def close_pedido_manually():
    """Cierra un pedido a mano y, si se pide, emite su factura.

    Es el respaldo humano del barrido automático: el barrido corre de forma oportunista
    (sin scheduler), así que un pedido abandonado sin tráfico posterior necesita que alguien
    de operaciones pueda cerrarlo desde acá.

    Cerrar y facturar están separados a propósito, igual que en el agente: si Alegra falla el
    pedido queda 'cerrado' y NO pasa a 'facturado', y eso es justamente lo que permite ver
    después cuáles quedaron sin factura.
    """
    payload = request.get_json(silent=True) or {}
    pedido_id = str(payload.get("pedido_id") or "").strip()
    payment_method = _sanitize_text(payload.get("payment_method"), 40) or None
    facturar = bool(payload.get("invoice"))
    if not pedido_id:
        return jsonify({"error": "Missing pedido_id"}), 400

    pedido = db.get_pedido(pedido_id)
    if not pedido:
        return jsonify({"error": "El pedido no existe"}), 404
    if pedido.get("status") == "facturado":
        return jsonify({"error": "Ese pedido ya está facturado"}), 400

    try:
        if pedido.get("status") == "abierto":
            db.close_pedido(pedido_id, payment_method or pedido.get("payment_method"))
    except Exception:
        return jsonify({"error": "No se pudo cerrar el pedido"}), 503

    resultado = {"ok": True, "status": "cerrado", "invoice": None}
    if not facturar:
        return jsonify(resultado)

    if not ALEGRA_ENABLED:
        resultado["warning"] = "Alegra está desactivado: el pedido quedó cerrado sin facturar."
        return jsonify(resultado)
    try:
        lineas = []
        ordenes = {o["id"]: o for o in db.list_pedido_requests(pedido_id)}
        for request_id, perfil in db.get_pedido_profiles(pedido_id, con_request_id=True):
            paciente = (ordenes.get(request_id) or {}).get("patient_name")
            lineas.extend(billing.build_invoice_lines(perfil, paciente))
        if not lineas:
            resultado["warning"] = "El pedido no tiene líneas facturables; quedó cerrado."
            return jsonify(resultado)
        cliente = db.get_client_by_id(pedido.get("client_id")) or {}
        nit = cliente.get("tax_id")
        if not nit:
            resultado["warning"] = "El cliente no tiene NIT; el pedido quedó cerrado sin facturar."
            return jsonify(resultado)
        factura = billing.invoice_order(
            nit, cliente.get("clinic_name") or "Cliente A3", lineas,
            datetime.now(timezone.utc).date().isoformat(),
            {k: v for k, v in {"email": cliente.get("email")}.items() if v},
        )
        if factura and factura.get("invoice_id"):
            db.mark_pedido_invoiced(pedido_id, str(factura["invoice_id"]))
            resultado.update(status="facturado", invoice=factura.get("number") or factura["invoice_id"])
        else:
            resultado["warning"] = "Alegra no devolvió factura; el pedido quedó cerrado."
    except Exception as exc:  # noqa: BLE001
        resultado["warning"] = f"Cerrado, pero la factura falló: {str(exc)[:120]}"
    return jsonify(resultado)


@dashboard.post("/api/dashboard/catalog-item")
@_login_required
def update_catalog_item():
    """Edita el PRECIO y/o la ETIQUETA DE ESPECIE de un ítem del catálogo.

    El catálogo era de solo lectura: cambiar un precio exigía SQL a mano. Pedido de A3 del
    07/04 (el pendiente más antiguo) y del 28/07 (la etiqueta).

    Cada cambio queda auditado en `request_events` con el valor anterior y quién lo hizo:
    tocar un precio mueve plata, así que tiene que poder rastrearse.
    """
    payload = request.get_json(silent=True) or {}
    kind = str(payload.get("kind") or "").strip().lower()
    tabla = _CATALOG_TABLES.get(kind)
    code = str(payload.get("code") or "").strip()
    if not tabla:
        return jsonify({"error": "kind debe ser 'analisis' o 'perfil'"}), 400
    if not code:
        return jsonify({"error": "Missing code"}), 400

    cambios: dict = {}
    if "price" in payload:
        try:
            precio = int(str(payload.get("price")).replace(".", "").replace(",", "").strip())
        except (TypeError, ValueError):
            return jsonify({"error": "El precio debe ser un número entero"}), 400
        if precio < 0:
            return jsonify({"error": "El precio no puede ser negativo"}), 400
        cambios["price"] = precio
    if "species" in payload:
        especie = str(payload.get("species") or "").strip().lower() or "ambos"
        if especie not in _CATALOG_SPECIES:
            return jsonify({"error": f"Especie no reconocida: {especie}"}), 400
        cambios["species"] = especie
    if not cambios:
        return jsonify({"error": "Nada para actualizar"}), 400

    try:
        anterior = db.get_catalog_item(tabla, code) or {}
        if not anterior:
            return jsonify({"error": f"No existe el código {code}"}), 404
        actualizado = db.update_catalog_item(tabla, code, cambios)
    except Exception:
        return jsonify({"error": "No se pudo actualizar el catálogo"}), 503

    db.log_catalog_change(
        tabla, code,
        antes={k: anterior.get(k) for k in cambios},
        despues=cambios,
        por=session.get("dashboard_username"),
    )
    return jsonify({"ok": True, "item": actualizado})


@dashboard.post("/api/dashboard/discount-tiers")
@_login_required
def update_discount_tiers():
    """Reemplaza los tramos del descuento por volumen (pedido de A3, llamada 6).

    Los tramos vivían hardcodeados en config.py y cambiarlos exigía deploy. Editar
    un descuento mueve plata: validación dura, auditoría en catalog_audit con el
    valor anterior, e invalidación del cache que usa el agente (app/pricing.py).
    """
    payload = request.get_json(silent=True) or {}
    tiers = payload.get("tiers") if isinstance(payload.get("tiers"), list) else None
    if not tiers:
        return jsonify({"error": "Falta la lista de tramos"}), 400

    parsed: list[dict] = []
    prev_min, prev_pct = 0, -1.0
    for item in tiers:
        try:
            min_tests = int(item.get("min_tests"))
            pct = float(item.get("pct"))
        except (TypeError, ValueError, AttributeError):
            return jsonify({"error": "Cada tramo necesita min_tests entero y pct numérico"}), 400
        if not 2 <= min_tests <= 99:
            return jsonify({"error": f"Mínimo de pruebas fuera de rango (2-99): {min_tests}"}), 400
        if not 0 <= pct <= 0.9:
            return jsonify({"error": f"Porcentaje fuera de rango (0-0.9): {pct}"}), 400
        if min_tests <= prev_min:
            return jsonify({"error": "Los tramos deben ir con mínimos ascendentes y sin repetir"}), 400
        if pct < prev_pct:
            return jsonify({"error": "El porcentaje no puede bajar al subir el tramo"}), 400
        prev_min, prev_pct = min_tests, pct
        parsed.append({"min_tests": min_tests, "pct": pct})

    try:
        anteriores = db.list_discount_tiers()
        guardados = db.replace_discount_tiers(parsed, session.get("dashboard_username"))
    except Exception:
        return jsonify({"error": "No se pudieron guardar los tramos"}), 503

    db.log_catalog_change(
        "discount_tiers", "tiers",
        antes={"tiers": anteriores},
        despues={"tiers": parsed},
        por=session.get("dashboard_username"),
    )
    pricing.invalidate_discount_tiers_cache()
    return jsonify({"ok": True, "tiers": guardados})


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
    clients = db.list_clients_with_assignment()
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
    # El período del gráfico de facturación llega por la URL (?facturacion=mes|semana|dia);
    # `auto` deja que lo elija el propio dato. Se lee acá y no dentro del builder para que
    # build_dashboard_context siga funcionando fuera de un request.
    loaded = build_dashboard_context(billing_period=(request.args.get("facturacion") or "auto"))
    context.update(loaded)
    summary = _empty_context()["summary"]
    summary.update(loaded.get("summary", {}))
    context["summary"] = summary
    # Vista de ejemplo (?demo=1): datos en memoria para ver el diseño con movimiento
    # mientras lo transaccional está vacío. NO toca la base y se avisa en pantalla.
    modo_demo = request.args.get("demo") in {"1", "true", "si"}
    if modo_demo:
        context["demo_mode"] = True
    if active_tab == "muestras" and modo_demo:
        demo_lanes = _demo_sample_process_lanes()
        context["sample_process_lanes"] = demo_lanes
        context["sample_demo_total"] = sum(lane["count"] for lane in demo_lanes)
        # La tabla también, no solo el tablero: ahí es donde se ve si una muestra con
        # tres perfiles del mismo paciente entra o desborda la celda.
        context["samples"] = demo_data.samples()
    if active_tab == "solicitudes" and modo_demo:
        context["requests"] = demo_data.requests(couriers=context.get("couriers_options") or [])
        context["request_status"] = demo_data.request_status_counts(context["requests"])
    if active_tab == "pedidos":
        if modo_demo:
            pedidos = demo_data.pedidos()
        else:
            # Solo se consulta en su pestaña: son dos queries y no hacen falta en el resto.
            pedidos = db.list_pedidos_for_dashboard()
        context["pedidos"] = pedidos
        context["pedidos_abiertos"] = sum(1 for p in pedidos if p.get("status") == "abierto")
        context["pedidos_sin_facturar"] = sum(1 for p in pedidos if p.get("status") == "cerrado")
    if active_tab == "clientes":
        # La búsqueda y los filtros corren ACÁ, sobre los 992 clientes, y recién después se
        # corta la página: hacerlo en el navegador solo miraba las 15 filas visibles y
        # buscar «animal pet» devolvía cero con el cliente cargado en otra página.
        criterios = client_filters.desde_args(request.args)
        todas = context.get("clients_rows") or []
        all_rows = client_filters.filtrar(
            todas,
            q=criterios.get("q", ""),
            tipo=criterios.get("tipo", "all"),
            estado=criterios.get("estado", "all"),
            motorizado=criterios.get("motorizado", "all"),
            fe=criterios.get("fe", "all"),
        )
        per_page = 15
        try:
            pedida = int(request.args.get("page", 1))
        except (TypeError, ValueError):
            pedida = 1
        paginas = max(1, (len(all_rows) + per_page - 1) // per_page)
        page = max(1, min(pedida, paginas))
        context["clients_total"] = len(all_rows)
        context["clients_all_total"] = len(todas)
        context["clients_page"] = page
        context["clients_per_page"] = per_page
        context["clients_pages"] = paginas
        context["clients_rows"] = all_rows[(page - 1) * per_page : page * per_page]
        context["clients_filters"] = criterios
        context["clients_query"] = criterios.get("q", "")
        context["clients_filter_values"] = {
            "tipo": criterios.get("tipo", "all"),
            "estado": criterios.get("estado", "all"),
            "motorizado": criterios.get("motorizado", "all"),
            "fe": criterios.get("fe", "all"),
        }
    if active_tab == "facturacion":
        # Dos pestañas, y se arma SOLO la que se está viendo: cada una lee el cache de
        # facturas entero (1.200 filas), así que calcular las dos en cada visita era leerlo
        # dos veces para mostrar la mitad. La pestaña va en la URL y no en el navegador
        # porque los filtros y la paginación recargan la página.
        vista = (request.args.get("vista") or "").strip().lower()
        if vista not in ("facturas", "cartera"):
            vista = "facturas"
        context["billing_view"] = vista
        if vista == "cartera":
            context.update(_build_cartera_context())
        else:
            try:
                page = max(1, int(request.args.get("page", 1)))
            except (TypeError, ValueError):
                page = 1
            filters = _parse_invoice_filters(request.args)
            order_field = request.args.get("order_field") or "invoice_date"
            order_desc = (request.args.get("order_dir") or "desc").lower() != "asc"
            context.update(_build_invoices_context(page, filters, order_field, order_desc))
    return render_template(
        "dashboard.html",
        active_tab=active_tab,
        context=context,
        username=session.get("dashboard_username", "admin"),
        notice=(request.args.get("notice") or "").strip(),
        notice_type=(request.args.get("notice_type") or "info").strip(),
    )
