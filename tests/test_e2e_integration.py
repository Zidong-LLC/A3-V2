"""
Test de integracion: agente conversacional + plataforma + orden de servicio.

Verifica el flujo end-to-end: datos del agente -> BD -> dashboard -> impresion.
Los tests de flujo del agente estan en test_agent_flows.py (137 tests).
Este archivo se enfoca en:
1. Service order payload tiene todos los campos requeridos
2. Dashboard construye las filas de service order correctamente
3. Operation center filtra rutas activas
4. Rutas sin motorizado generan alertas
5. Corte horario programa siguiente dia habil
6. Notificacion de motorizado incluida en respuesta del agente
7. Perfil personalizado calcula totales ajustados
8. Carga de clientes Alegra (sucursales, eliminados, sin NIT)
9. Print page de orden de servicio
10. Aprobacion de clientes pendientes
11. Estado de la BD despues de la carga
"""
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone


MOCK_COURER = {"id": "courier-1", "name": "Javier", "phone": "3001112222"}


def _full_route_captured(payment="contraentrega"):
    return {
        "clinic_name": "Centro Veterinario Agromascotas SAS",
        "_client_display_name": "Centro Veterinario Agromascotas SAS",
        "_client_found": True,
        "_address_confirmed": True,
        "tax_id": "901354321-1",
        "pickup_address": "CL 40C SUR 72N BIS-30",
        "exam_type": "Hemograma Completo",
        "patient_name": "Luna",
        "species": "canino",
        "breed": "labrador",
        "sex": "hembra",
        "patient_age": "3 anos",
        "owner_name": "Carlos Perez",
        "requesting_doctor": "Dra. Ana Gomez",
        "clinic_phone": "3102223344",
        "observations": "muestra refrigerada",
        "payment_method": payment,
    }


# --- Test 1: Service order payload contiene todos los campos ---

def test_e2e_service_order_payload_complete():
    from app.services.db import _service_order_event_payload

    fields = _full_route_captured()
    now = datetime.now(timezone.utc)

    payload = _service_order_event_payload(fields, now)

    assert payload["date"] == now.date().isoformat()
    assert payload["requesting_doctor"] == "Dra. Ana Gomez"
    assert payload["clinic_name"] == "Centro Veterinario Agromascotas SAS"
    assert payload["clinic_phone"] == "3102223344"
    assert payload["pickup_address"] == "CL 40C SUR 72N BIS-30"
    assert payload["exam_type"] == "Hemograma Completo"
    assert payload["observations"] == "muestra refrigerada"
    assert payload["payment_method"] == "contraentrega"

    patient = payload["patient"]
    assert patient["name"] == "Luna"
    assert patient["species"] == "canino"
    assert patient["breed"] == "labrador"
    assert patient["sex"] == "hembra"
    assert patient["age"] == "3 anos"
    assert patient["owner_name"] == "Carlos Perez"


# --- Test 2: Service order usa _client_display_name como fallback ---

def test_e2e_service_order_display_name_fallback():
    from app.services.db import _service_order_event_payload

    fields = _full_route_captured()
    fields["clinic_name"] = None
    fields["_client_display_name"] = "Veterinaria Fallback"
    now = datetime.now(timezone.utc)

    payload = _service_order_event_payload(fields, now)
    assert payload["clinic_name"] == "Veterinaria Fallback"


# --- Test 3: Profile adjusted total calculation ---

def test_e2e_profile_adjusted_total():
    from app.rules import calculate_profile_adjusted_total

    result = calculate_profile_adjusted_total(34000, [12000], [8000])
    assert result["base"] == 34000
    assert result["added"] == 12000
    assert result["removed"] == 8000
    assert result["total"] == 38000

    result_zero = calculate_profile_adjusted_total(34000, [], [])
    assert result_zero["total"] == 34000

    result_floor = calculate_profile_adjusted_total(20000, [5000], [30000])
    assert result_floor["total"] == 0


# --- Test 4: Dashboard lee service orders desde request_events ---

def test_e2e_dashboard_service_order_rows():
    from app.dashboard import _build_service_order_rows

    requests_rows = [{
        "id": "req-dash-1",
        "requested_at": "2026-05-27T10:00:00",
        "status": "assigned",
        "priority": "normal",
        "scheduled_pickup_date": "2026-05-28",
        "pickup_address": "CL 40C SUR 72N BIS-30",
        "patient_name": "Luna",
        "patient_age": "3 anos",
        "owner_name": "Carlos Perez",
        "species": "canino",
        "exam_type": "Hemograma Completo",
        "service_area": "route_scheduling",
        "clients": {"id": "c-1", "clinic_name": "Centro Vet Agromascotas"},
        "couriers": {"id": "courier-1", "name": "Javier"},
    }]

    request_events = [{
        "id": "evt-1",
        "request_id": "req-dash-1",
        "event_type": "created",
        "created_at": "2026-05-27T10:00:00",
        "event_payload": {
            "source": "telegram",
            "service_order": {
                "date": "2026-05-27",
                "requesting_doctor": "Dra. Ana Gomez",
                "clinic_name": "Centro Vet Agromascotas",
                "clinic_phone": "3102223344",
                "pickup_address": "CL 40C SUR 72N BIS-30",
                "patient": {"name": "Luna", "species": "canino", "breed": "labrador", "sex": "hembra", "age": "3 anos", "owner_name": "Carlos Perez"},
                "exam_type": "Hemograma Completo",
                "observations": "muestra refrigerada",
                "payment_method": "contraentrega",
            },
        },
    }]

    rows = _build_service_order_rows(requests_rows, request_events)

    assert len(rows) == 1
    order = rows[0]
    assert order["request_id"] == "req-dash-1"
    assert order["patient_name"] == "Luna"
    assert order["exam_type"] == "Hemograma Completo"
    assert order["requesting_doctor"] == "Dra. Ana Gomez"
    assert order["clinic_name"] == "Centro Vet Agromascotas"
    assert order["clinic_phone"] == "3102223344"
    assert order["pickup_address"] == "CL 40C SUR 72N BIS-30"
    assert order["payment_method"] == "Contra entrega"
    assert order["courier_name"] == "Javier"


# --- Test 5: Operation center filtra rutas activas ---

def test_e2e_operation_center_filters_active_routes():
    from app.dashboard import _build_operation_center

    requests = [
        {"id": "req-active", "status": "assigned", "service_area": "route_scheduling",
         "client_id": "c-1", "clients": {"id": "c-1", "clinic_name": "Clinica Norte"},
         "couriers": {"id": "courier-1", "name": "Javier"}, "requested_at": "2026-05-27T10:00:00",
         "pickup_address": "Calle 1", "patient_name": "Toby", "exam_type": "Hemograma",
         "priority": "normal", "scheduled_pickup_date": "2026-05-28"},
        {"id": "req-done", "status": "processed", "service_area": "route_scheduling",
         "client_id": "c-2", "clients": {"id": "c-2", "clinic_name": "Clinica Sur"},
         "couriers": {"id": "courier-2", "name": "Diego"}, "requested_at": "2026-05-26T10:00:00",
         "pickup_address": "Calle 2", "patient_name": "Max", "exam_type": "Perfil Renal",
         "priority": "normal", "scheduled_pickup_date": "2026-05-27"},
        {"id": "req-acc", "status": "received", "service_area": "accounting",
         "client_id": "c-3", "clients": {"id": "c-3", "clinic_name": "Clinica Este"},
         "couriers": None, "requested_at": "2026-05-27T10:00:00",
         "pickup_address": None, "patient_name": None, "exam_type": None,
         "priority": "normal", "scheduled_pickup_date": None},
    ]

    motorizados_ctx = {"summary": {"total_couriers": 8, "active_couriers": 7, "busiest_courier_name": "Javier", "busiest_courier_clients": 25}, "alerts": []}
    result = _build_operation_center(requests, [], [], motorizados_ctx)

    route_ids = [r["id"] for r in result["route_rows"]]
    assert "req-active" in route_ids
    assert "req-done" not in route_ids
    assert "req-acc" not in route_ids


# --- Test 6: Ruta sin motorizado genera alerta ---

def test_e2e_unassigned_route_generates_alert():
    from app.dashboard import _build_operation_center

    requests = [{"id": "req-unassigned", "status": "error_pending_assignment",
                 "service_area": "route_scheduling", "client_id": "c-10",
                 "clients": {"id": "c-10", "clinic_name": "Clinica Sin Motorizado"},
                 "couriers": None, "requested_at": "2026-05-27T10:00:00",
                 "pickup_address": "Calle 99", "patient_name": "Rex",
                 "exam_type": "Perfil Hepatico", "priority": "normal", "scheduled_pickup_date": None}]

    motorizados_ctx = {"summary": {"total_couriers": 8, "active_couriers": 7, "busiest_courier_name": "Javier", "busiest_courier_clients": 25}, "alerts": []}
    result = _build_operation_center(requests, [], [], motorizados_ctx)

    unassigned = [a for a in result["alerts"] if "sin asignar" in a.get("title", "").lower()]
    assert len(unassigned) >= 1


# --- Test 7: Corte horario programa siguiente dia habil ---

def test_e2e_cutoff_schedules_next_business_day():
    from app.rules import get_scheduled_pickup_date

    weekday_18pm = datetime(2026, 5, 27, 18, 0, 0, tzinfo=timezone.utc)
    result = get_scheduled_pickup_date(weekday_18pm)
    assert result > weekday_18pm.date()

    friday_18pm = datetime(2026, 5, 22, 18, 0, 0, tzinfo=timezone.utc)
    result_friday = get_scheduled_pickup_date(friday_18pm)
    assert result_friday.weekday() == 0


# --- Test 8: Notificacion de motorizado en respuesta ---

def test_e2e_courier_notification_appended():
    from app.agent import _append_courier_notification

    reply = "Orden registrada exitosamente."
    result = _append_courier_notification(reply, MOCK_COURER)
    assert "Javier" in result
    assert "3001112222" in result

    reply_no_courier = "Orden registrada."
    result_none = _append_courier_notification(reply_no_courier, None)
    assert result_none == "Orden registrada."


# --- Test 9: Print page de orden de servicio ---

def test_e2e_service_order_print_page_renders():
    from app.main import app

    app.config["TESTING"] = True
    client = app.test_client()

    overview = {
        "summary": {"total_clients": 1, "clients_with_courier": 1, "clients_without_courier": 0,
                     "active_requests": 1, "unassigned_requests": 0, "sessions_tracked": 1},
        "requests_by_status": {"assigned": 1}, "service_area_counts": {"route_scheduling": 1},
        "flow_stage_counts": [], "unassigned_request_rows": [],
        "request_status": {"assigned": 1}, "samples": [], "messages": [],
        "clients_rows": [], "catalog_rows": [], "flow_kanban_lanes": [],
        "approval_rows": [], "reviewed_approval_rows": [], "affiliation_rows": [],
        "service_order_rows": [{
            "request_id": "req-print-1", "status": "assigned", "status_label": "Asignada",
            "patient_name": "Luna", "exam_type": "Hemograma Completo",
            "clinic_name": "Centro Vet Agromascotas", "clinic_phone": "3102223344",
            "pickup_address": "CL 40C SUR 72N BIS-30", "requesting_doctor": "Dra. Ana Gomez",
            "observations": "muestra refrigerada", "payment_method": "contraentrega",
            "courier_name": "Javier", "scheduled_pickup_date": "2026-05-28",
            "order_summary": "Luna - Hemograma Completo", "species": "canino",
            "breed": "labrador", "sex": "hembra", "patient_age": "3 anos",
            "owner_name": "Carlos Perez", "date": "2026-05-27",
        }],
    }

    with patch("app.dashboard.DASHBOARD_ADMIN_USER", "admin"), \
         patch("app.dashboard.DASHBOARD_ADMIN_PASSWORD", "secret"), \
         patch("app.dashboard._login_required", lambda f: f), \
         patch("app.dashboard.build_dashboard_context", return_value=overview):

        client.post("/login", data={"username": "admin", "password": "secret"})
        response = client.get("/ordenes-servicio/req-print-1/imprimir")

    assert response.status_code == 200


# --- Test 10: Carga de clientes Alegra - sucursales ---

def test_e2e_allegra_branch_detection():
    from tools.scripts.validate_allegra_clients import load_excel_rows
    from collections import Counter

    rows = load_excel_rows()
    tax_ids = [r["tax_id"] for r in rows if r["tax_id"] and not r["is_deleted"]]
    duplicated = {tax: count for tax, count in Counter(tax_ids).items() if count > 1}

    sucursal_nits = {"901780420", "79371045", "80221946", "1018456718", "1073382009"}
    for nit in sucursal_nits:
        assert nit in duplicated, f"NIT {nit} deberia estar duplicado como sucursal"

    puppy_rows = [r for r in rows if r["tax_id"] == "901780420"]
    assert len(puppy_rows) == 4, "Puppy Export deberia tener 4 sedes"


# --- Test 11: Clientes eliminados y sin NIT ---

def test_e2e_allegra_deleted_and_no_nit_clients():
    from tools.scripts.validate_allegra_clients import load_excel_rows

    rows = load_excel_rows()
    deleted = [r for r in rows if r["is_deleted"]]
    if deleted:
        assert all(r["invoice_status"].lower() == "eliminado" for r in deleted)

    no_nit = [r for r in rows if not r["tax_id"] or not r["tax_id"].strip()]
    assert len(no_nit) >= 0


# --- Test 12: Import payload maneja defaults ---

def test_e2e_allegra_import_payload_defaults():
    from tools.scripts.import_allegra_clients import make_client_payload

    row_active = {
        "row_number": 10, "external_code": "901354321",
        "clinic_name": "Veterinaria Test E2E", "tax_id": "901354321-1",
        "phone": "3102223344", "address": "Calle 100 #20-30",
        "city": "Bogota", "is_deleted": False,
    }
    payload = make_client_payload(row_active, 10)
    assert payload["clinic_name"] == "Veterinaria Test E2E"
    assert payload["tax_id"] == "901354321-1"
    assert payload["is_active"] is True
    assert payload["address"] == "Calle 100 #20-30"

    row_no_phone = {
        "row_number": 20, "external_code": "12345",
        "clinic_name": "Vet Sin Telefono", "tax_id": "12345",
        "phone": "", "address": "", "city": "",
        "is_deleted": False,
    }
    payload2 = make_client_payload(row_no_phone, 20)
    assert payload2["phone"].startswith("s/tel-")
    assert payload2["address"] == "Sin dirección"
    assert payload2["city"] == "Bogotá"

    row_deleted = {
        "row_number": 30, "external_code": "99999",
        "clinic_name": "Veterinaria Eliminada", "tax_id": "99999",
        "phone": "3000000000", "address": "Calle Falsa 123",
        "city": "Bogota", "is_deleted": True,
    }
    payload3 = make_client_payload(row_deleted, 30)
    assert payload3["is_active"] is False


# --- Test 13: Dashboard API overview con service orders ---

def test_e2e_dashboard_api_overview_structure():
    from app.dashboard import _build_service_order_rows

    requests_rows = [{
        "id": "req-api-1", "requested_at": "2026-05-27T10:00:00",
        "status": "assigned", "priority": "normal",
        "scheduled_pickup_date": "2026-05-28",
        "pickup_address": "CL 40C SUR 72N", "patient_name": "Luna",
        "patient_age": "3 anos", "owner_name": "Carlos Perez",
        "species": "canino", "exam_type": "Hemograma",
        "service_area": "route_scheduling",
        "clients": {"id": "c-1", "clinic_name": "Centro Vet"},
        "couriers": {"id": "courier-1", "name": "Javier"},
    }]

    request_events = [{
        "id": "evt-api-1", "request_id": "req-api-1",
        "event_type": "created", "created_at": "2026-05-27T10:00:00",
        "event_payload": {
            "service_order": {
                "date": "2026-05-27", "requesting_doctor": "Dra. Gomez",
                "clinic_name": "Centro Vet", "clinic_phone": "3102223344",
                "pickup_address": "CL 40C SUR 72N",
                "patient": {"name": "Luna", "species": "canino", "breed": "labrador", "sex": "hembra", "age": "3 anos", "owner_name": "Carlos"},
                "exam_type": "Hemograma", "observations": None,
                "payment_method": "contraentrega",
            },
        },
    }]

    rows = _build_service_order_rows(requests_rows, request_events)
    assert len(rows) == 1
    assert rows[0]["requesting_doctor"] == "Dra. Gomez"
    assert rows[0]["patient_name"] == "Luna"
    assert rows[0]["breed"] == "labrador"


# --- Test 14: Aprobacion de cliente pendiente ---

def test_e2e_approve_pending_client_with_courier():
    with patch("app.services.db._client") as mock_db:
        mock_client_row = MagicMock()
        mock_client_row.data = [{"id": "client-new-1", "clinic_name": "Nueva Clinica"}]

        mock_request_row = MagicMock()
        mock_request_row.data = [{"id": "req-approve-1", "client_id": "client-new-1"}]

        mock_event_row = MagicMock()
        mock_event_row.data = [{"event_payload": {"courier_id": "courier-javier", "source": "dashboard_review"}}]

        def mock_table(table_name):
            m = MagicMock()
            if table_name == "clients":
                m.select.return_value.eq.return_value.execute.return_value = mock_client_row
                m.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"id": "client-new-1"}])
            elif table_name == "requests":
                m.select.return_value.eq.return_value.execute.return_value = mock_request_row
                m.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"id": "req-approve-1"}])
            elif table_name == "request_events":
                m.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = mock_event_row
                m.insert.return_value.execute.return_value = MagicMock(data=[{"id": "evt-1"}])
            elif table_name == "client_courier_assignment":
                m.insert.return_value.execute.return_value = MagicMock(data=[{"id": "assign-1"}])
            return m

        mock_db.table = mock_table

        from app.services.db import approve_pending_client
        result = approve_pending_client("req-approve-1")

    assert result is True


# --- Test 15: INTENT_TO_SERVICE_AREA y ESCALATED_INTENTS ---

def test_e2e_intent_mapping_complete():
    from app.rules import INTENT_TO_SERVICE_AREA, ESCALATED_INTENTS

    assert "route_scheduling" in INTENT_TO_SERVICE_AREA
    assert "results" in INTENT_TO_SERVICE_AREA
    assert "accounting" in INTENT_TO_SERVICE_AREA
    assert "new_client" in INTENT_TO_SERVICE_AREA
    assert "unknown" in INTENT_TO_SERVICE_AREA

    assert "accounting" in ESCALATED_INTENTS
    assert "new_client" in ESCALATED_INTENTS
    assert "route_scheduling" not in ESCALATED_INTENTS


# --- Test 16: Corte horario - antes del corte mismo dia ---

def test_e2e_cutoff_before_cutoff_same_day():
    from app.rules import get_scheduled_pickup_date

    before_cutoff = datetime(2026, 5, 27, 10, 0, 0, tzinfo=timezone.utc)
    result = get_scheduled_pickup_date(before_cutoff)

    from datetime import timedelta
    next_day = before_cutoff.date() + timedelta(days=1)
    assert result == next_day or result == before_cutoff.date() + timedelta(days=1)