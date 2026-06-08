import pytest
from unittest.mock import patch


def _get_test_client():
    from app.main import app

    app.config["TESTING"] = True
    return app.test_client()


def test_dashboard_requires_login():
    client = _get_test_client()

    response = client.get("/dashboard")

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_dashboard_login_accepts_configured_credentials(monkeypatch):
    monkeypatch.setattr("app.dashboard.DASHBOARD_ADMIN_USER", "admin")
    monkeypatch.setattr("app.dashboard.DASHBOARD_ADMIN_PASSWORD", "secret")

    client = _get_test_client()
    response = client.post(
        "/login",
        data={"username": "admin", "password": "secret"},
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/dashboard")


def test_dashboard_renders_operational_overview_after_login(monkeypatch):
    monkeypatch.setattr("app.dashboard.DASHBOARD_ADMIN_USER", "admin")
    monkeypatch.setattr("app.dashboard.DASHBOARD_ADMIN_PASSWORD", "secret")

    overview = {
        "summary": {
            "total_clients": 2,
            "clients_with_courier": 1,
            "clients_without_courier": 1,
            "active_requests": 3,
            "unassigned_requests": 1,
            "sessions_tracked": 4,
        },
        "requests_by_status": {"assigned": 2, "error_pending_assignment": 1},
        "service_area_counts": {"route_scheduling": 3},
        "flow_stage_counts": [{"stage_key": "fase_2_recogida_datos", "count": 2, "order": 2}],
        "unassigned_request_rows": [
            {"id": "r-1", "clinic_name": "Clinica Dos", "status": "error_pending_assignment"}
        ],
        "request_status": {"assigned": 2, "cancelled": 0},
        "samples": [],
        "messages": [],
        "clients_rows": [],
        "catalog_rows": [],
        "flow_kanban_lanes": [],
        "approval_rows": [],
        "reviewed_approval_rows": [],
        "affiliation_rows": [],
    }

    with patch("app.dashboard.build_dashboard_context", return_value=overview):
        client = _get_test_client()
        client.post("/login", data={"username": "admin", "password": "secret"})
        response = client.get("/dashboard")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Panel Ejecutivo" in body
    assert "CRM Operativo" in body
    assert "Solicitudes activas" in body


def test_dashboard_api_returns_context_for_authenticated_user(monkeypatch):
    monkeypatch.setattr("app.dashboard.DASHBOARD_ADMIN_USER", "admin")
    monkeypatch.setattr("app.dashboard.DASHBOARD_ADMIN_PASSWORD", "secret")

    context = {"summary": {"total_clients": 7}, "requests_by_status": {}}

    with patch("app.dashboard.build_dashboard_context", return_value=context):
        client = _get_test_client()
        client.post("/login", data={"username": "admin", "password": "secret"})
        response = client.get("/api/dashboard/overview")

    assert response.status_code == 200
    assert response.get_json()["summary"]["total_clients"] == 7


def test_operation_center_page_renders_daily_workbench(monkeypatch):
    monkeypatch.setattr("app.dashboard.DASHBOARD_ADMIN_USER", "admin")
    monkeypatch.setattr("app.dashboard.DASHBOARD_ADMIN_PASSWORD", "secret")
    context = {
        "summary": {"active_requests": 2, "pending_manual_approvals": 1},
        "requests": [],
        "operation_center": {
            "kpis": {"active_routes": 2, "pending_approvals": 1, "pending_samples": 3, "critical_alerts": 1},
            "alerts": [{"level": "warning", "title": "Ruta sin asignar", "detail": "Clinica Norte requiere motorizado."}],
            "route_rows": [{"clinic_name": "Clinica Norte", "status_label": "Recibida", "courier_name": "Sin asignar", "address": "Calle 1", "scheduled_pickup_date": "2026-05-15"}],
            "courier_agenda": [{"courier_name": "Sin asignar", "count": 1, "routes": [{"clinic_name": "Clinica Norte", "status_label": "Recibida", "address": "Calle 1"}]}],
            "approval_rows": [{"clinic_name": "Nueva Vet", "contact_phone": "301", "zone": "Kennedy"}],
            "sample_lanes": [{"label": "A retirar", "count": 3}],
        },
    }

    with patch("app.dashboard.build_dashboard_context", return_value=context):
        client = _get_test_client()
        client.post("/login", data={"username": "admin", "password": "secret"})
        response = client.get("/operacion")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Centro Operativo Diario" in body
    assert "Clinica Norte" in body
    assert "Nueva Vet" in body
    assert "Agenda por motorizado" in body


def test_operation_center_groups_active_routes_by_courier():
    from app.dashboard import _build_operation_center

    requests_rows = [
        {"id": "r-1", "service_area": "route_scheduling", "status": "assigned", "pickup_address": "Calle 1", "scheduled_pickup_date": "2026-05-15", "clients": {"clinic_name": "Clinica Diego"}, "couriers": {"name": "Diego"}},
        {"id": "r-2", "service_area": "route_scheduling", "status": "received", "pickup_address": "Calle 2", "scheduled_pickup_date": "2026-05-15", "clients": {"clinic_name": "Clinica Sin"}},
    ]

    context = _build_operation_center(requests_rows, [], [], {"motorizados_alerts": []})
    agenda = {row["courier_name"]: row for row in context["courier_agenda"]}

    assert agenda["Diego"]["count"] == 1
    assert agenda["Sin asignar"]["count"] == 1
    assert agenda["Diego"]["routes"][0]["clinic_name"] == "Clinica Diego"


def test_service_order_event_is_visible_in_operation_center():
    from app.dashboard import _build_operation_center, _build_service_order_rows

    requests_rows = [{
        "id": "req-os-1",
        "client_id": "client-1",
        "service_area": "route_scheduling",
        "status": "assigned",
        "pickup_address": "Calle 1",
        "scheduled_pickup_date": "2026-05-24",
        "requested_at": "2026-05-24T10:00:00",
        "exam_type": "Hemograma",
        "clients": {"clinic_name": "Clinica Norte"},
        "couriers": {"name": "Diego"},
    }]
    events = [{
        "id": "event-os-1",
        "request_id": "req-os-1",
        "event_type": "created",
        "created_at": "2026-05-24T10:00:01",
        "event_payload": {
            "service_order": {
                "date": "2026-05-24",
                "requesting_doctor": "Dr. Luis Mora",
                "clinic_name": "Clinica Norte",
                "clinic_phone": "3102223344",
                "pickup_address": "Calle 1",
                "patient": {"name": "Toby", "species": "canino", "breed": "criollo", "sex": "macho", "age": "5 anos", "owner_name": "Maria Lopez"},
                "exam_type": "Hemograma",
                "observations": "muestra refrigerada",
                "payment_method": "contraentrega",
            }
        },
    }]

    service_orders = _build_service_order_rows(requests_rows, events)
    op = _build_operation_center(requests_rows, [], [], {"motorizados_alerts": []}, service_orders)

    assert service_orders[0]["requesting_doctor"] == "Dr. Luis Mora"
    assert service_orders[0]["patient_name"] == "Toby"
    assert op["route_rows"][0]["service_order"]["exam_type"] == "Hemograma"
    assert "Toby" in op["route_rows"][0]["order_summary"]


def test_samples_page_renders_service_order_sheet(monkeypatch):
    monkeypatch.setattr("app.dashboard.DASHBOARD_ADMIN_USER", "admin")
    monkeypatch.setattr("app.dashboard.DASHBOARD_ADMIN_PASSWORD", "secret")
    service_order = {
        "request_id": "req-os-1",
        "service_order_date": "2026-05-24",
        "requesting_doctor": "Dr. Luis Mora",
        "clinic_name": "Clinica Norte",
        "clinic_phone": "3102223344",
        "pickup_address": "Calle 1",
        "patient_name": "Toby",
        "species": "canino",
        "breed": "criollo",
        "sex": "macho",
        "patient_age": "5 anos",
        "owner_name": "Maria Lopez",
        "exam_type": "Hemograma",
        "observations": "muestra refrigerada",
        "payment_method": "contraentrega",
        "status_label": "Asignada",
        "courier_name": "Diego",
        "scheduled_pickup_date": "2026-05-24",
    }
    context = {
        "summary": {},
        "request_status": {},
        "requests": [],
        "messages": [],
        "samples": [],
        "clients_rows": [],
        "profile_catalog_rows": [],
        "profile_analysis_rows": [],
        "profile_builder_items": [],
        "profile_categories": [],
        "profile_species": [],
        "sample_requirements": [],
        "sample_process_lanes": [],
        "service_order_rows": [service_order],
    }

    with patch("app.dashboard.build_dashboard_context", return_value=context):
        client = _get_test_client()
        client.post("/login", data={"username": "admin", "password": "secret"})
        response = client.get("/muestras")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Ordenes de servicio agendadas" in body
    assert "Orden de Servicio" in body
    assert "Dr. Luis Mora" in body
    assert "Toby" in body
    assert "Hemograma" in body
    assert "muestra refrigerada" in body


def test_service_order_print_page_renders_pdf_ready_form(monkeypatch):
    monkeypatch.setattr("app.dashboard.DASHBOARD_ADMIN_USER", "admin")
    monkeypatch.setattr("app.dashboard.DASHBOARD_ADMIN_PASSWORD", "secret")
    context = {
        "service_order_rows": [{
            "request_id": "req-os-1",
            "service_order_date": "2026-05-24",
            "requesting_doctor": "Dr. Luis Mora",
            "clinic_name": "Clinica Norte",
            "clinic_phone": "3102223344",
            "pickup_address": "Calle 1",
            "patient_name": "Toby",
            "species": "canino",
            "breed": "criollo",
            "sex": "macho",
            "patient_age": "5 anos",
            "owner_name": "Maria Lopez",
            "exam_type": "Hemograma",
            "observations": "muestra refrigerada",
            "payment_method": "contraentrega",
            "status_label": "Asignada",
            "courier_name": "Diego",
            "scheduled_pickup_date": "2026-05-24",
        }],
    }

    with patch("app.dashboard.build_dashboard_context", return_value=context):
        client = _get_test_client()
        client.post("/login", data={"username": "admin", "password": "secret"})
        response = client.get("/ordenes-servicio/req-os-1/imprimir")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Orden de Servicio" in body
    assert "Dr. Luis Mora" in body
    assert "Toby" in body
    assert "Hemograma" in body
    assert "window.print" in body


def test_dashboard_keeps_legacy_sections_connected(monkeypatch):
    monkeypatch.setattr("app.dashboard.DASHBOARD_ADMIN_USER", "admin")
    monkeypatch.setattr("app.dashboard.DASHBOARD_ADMIN_PASSWORD", "secret")
    context = {
        "summary": {
            "active_requests": 1,
            "pending_pickup": 1,
            "total_samples": 1,
            "total_clients": 1,
            "clients_with_courier": 1,
            "clients_without_courier": 0,
            "unassigned_requests": 0,
            "sessions_tracked": 1,
        },
        "request_status": {"received": 1, "cancelled": 0},
        "requests": [{"id": "r-1", "created_at": "2026-05-09T10:00:00", "status": "received"}],
        "messages": [{"id": "m-1", "created_at": "2026-05-09T10:00:00"}],
        "clients_rows": [{"clinic_name": "Clinica Norte", "phone": "300", "address": "Calle 1", "zone": "Norte", "courier_name": "Luis", "requests_count": 1, "samples_count": 1, "latest_request_status": "received", "latest_sample_status": "pending_pickup"}],
        "couriers_options": [{"id": "courier-1", "name": "Luis Moto", "color": "#f97316"}],
        "couriers_rows": [{"id": "courier-1", "name": "Luis Moto", "phone": "3001234567", "availability": "available", "color": "#f97316", "coverage_count": 1, "clients_count_from_coverage": 3, "localities_text": "Kennedy"}],
        "localities_rows": [{"locality_code": "kennedy", "locality_name": "Kennedy", "clients_count": 3, "coverage_state": "assigned", "assigned_courier_id": "courier-1", "assigned_courier_name": "Luis Moto", "is_assigned": True}],
        "motorizados_summary": {"coverage_rate": 5, "assigned_localities": 1, "total_localities": 20, "clients_in_assigned_localities": 3, "clients_in_catalog_localities": 4, "clients_in_unassigned_localities": 1, "localities_with_clients_without_coverage": 1, "busiest_courier_name": "Luis Moto", "busiest_courier_clients": 3},
        "motorizados_alerts": [{"level": "warning", "title": "Cobertura pendiente", "detail": "1 localidad sin motorizado"}],
        "samples": [{"created_at": "2026-05-09T10:00:00", "sample_type": "Sangre", "test_name": "Hemograma", "priority": "normal", "status": "pending_pickup", "clients": {"clinic_name": "Clinica Norte"}, "couriers": {"name": "Luis"}}],
        "catalog_rows": [{"analysis_code": "H001", "test_type": "Hematologia", "test_name": "Hemograma", "turnaround": "1 dia(s)", "price_cop": 10000}],
        "flow_kanban_lanes": [{"label": "Recogida de datos", "stage_key": "fase_2_recogida_datos", "count": 1, "cards": [{"clinic_name": "Clinica Norte", "phone": "300", "external_chat_id": "chat-1"}]}],
        "approval_rows": [{"external_chat_id": "chat-2", "clinic_name": "Nueva Vet", "profile_label": "Clinica veterinaria", "document_type": "nit", "document_number": "900", "contact_phone": "301", "updated_at": "2026-05-09T10:00:00"}],
        "reviewed_approval_rows": [],
        "affiliation_rows": [{"clinic_name": "Clinica Norte", "professional_name": "Dra Ana", "professional_card": "TP1", "source_sheet": "manual", "clinic_key": "c1", "professional_key": "p1"}],
    }

    with patch("app.dashboard.build_dashboard_context", return_value=context):
        client = _get_test_client()
        client.post("/login", data={"username": "admin", "password": "secret"})
        pages = {
            "/clientes": "Clinica Norte",
            "/muestras": "Hemograma",
            "/analisis": "H001",
            "/flujo": "Recogida de datos",
            "/aprobaciones": "Nueva Vet",
            "/motorizados": "Luis Moto",
        }
        for path, expected in pages.items():
            response = client.get(path)
            assert response.status_code == 200
            assert expected in response.get_data(as_text=True)


def test_clients_page_renders_total_delete_action(monkeypatch):
    monkeypatch.setattr("app.dashboard.DASHBOARD_ADMIN_USER", "admin")
    monkeypatch.setattr("app.dashboard.DASHBOARD_ADMIN_PASSWORD", "secret")
    context = {
        "summary": {},
        "request_status": {},
        "requests": [],
        "messages": [],
        "clients_rows": [{"client_id": "client-1", "clinic_key": "clinica_norte", "clinic_name": "Clinica Norte", "client_status": "Activo"}],
    }

    with patch("app.dashboard.build_dashboard_context", return_value=context):
        client = _get_test_client()
        client.post("/login", data={"username": "admin", "password": "secret"})
        response = client.get("/clientes")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "data-client-delete-btn" in body
    assert "Eliminar" in body


def test_new_client_button_only_renders_on_clients_page(monkeypatch):
    monkeypatch.setattr("app.dashboard.DASHBOARD_ADMIN_USER", "admin")
    monkeypatch.setattr("app.dashboard.DASHBOARD_ADMIN_PASSWORD", "secret")
    context = {
        "summary": {},
        "request_status": {},
        "requests": [],
        "messages": [],
        "clients_rows": [],
    }

    with patch("app.dashboard.build_dashboard_context", return_value=context):
        client = _get_test_client()
        client.post("/login", data={"username": "admin", "password": "secret"})
        clients_response = client.get("/clientes")
        other_responses = [client.get(path) for path in ("/dashboard", "/muestras", "/motorizados", "/aprobaciones")]

    assert clients_response.status_code == 200
    assert 'href="/clientes/nuevo"' in clients_response.get_data(as_text=True)
    for response in other_responses:
        assert response.status_code == 200
        assert 'href="/clientes/nuevo"' not in response.get_data(as_text=True)


def test_dashboard_context_includes_profile_builder_catalog(monkeypatch):
    with patch("app.dashboard.db.list_clients_with_assignment", return_value=[]), \
         patch("app.dashboard.db.list_requests", return_value=[]), \
         patch("app.dashboard.db.list_sessions", return_value=[]), \
         patch("app.dashboard.db.list_conversation_messages", return_value=[]), \
         patch("app.dashboard.db.list_catalog_tests", return_value=[{"code": "H001", "name": "Hemograma", "category": "Hematologia", "species": "ambos", "sample": "Tubo Tapa Morada", "price": 10000, "is_active": True}]), \
         patch("app.dashboard.db.list_catalog_profiles", return_value=[{"code": "P001", "name": "Perfil Renal", "category": "Renal", "species": "canino", "description": "Control renal", "price": 50000, "is_active": True}], create=True), \
         patch("app.dashboard.db.list_a3_knowledge_index", return_value=[]), \
         patch("app.dashboard.db.fetch_rows", return_value=[]), \
         patch("app.dashboard.db.list_pending_client_reviews", return_value=[]), \
         patch("app.dashboard.db.list_active_couriers", return_value=[]), \
         patch("app.dashboard.db.list_courier_locality_coverage", return_value=[]):
        from app.dashboard import build_dashboard_context

        context = build_dashboard_context()

    assert context["profile_catalog_rows"][0]["name"] == "Perfil Renal"
    assert context["profile_analysis_rows"][0]["sample"] == "Tubo Tapa Morada"
    assert {item["item_type"] for item in context["profile_builder_items"]} == {"profile", "analysis"}
    assert context["sample_requirements"] == ["Tubo Tapa Morada"]


def test_dashboard_context_groups_samples_by_process_status(monkeypatch):
    sample_rows = [{
        "id": "sample-1",
        "client_id": "client-1",
        "status": "received_lab",
        "priority": "normal",
        "test_code": "P001",
        "test_name": "Perfil Renal",
        "sample_type": "Perfil personalizado",
        "created_at": "2026-05-12T10:00:00",
        "clients": {"clinic_name": "Clinica Norte"},
    }]
    event_rows = [{
        "sample_id": "sample-1",
        "event_type": "profile_assigned_from_dashboard",
        "created_at": "2026-05-12T10:01:00",
        "event_payload": {
            "assigned_item": {"code": "P001", "name": "Perfil Renal", "item_type": "profile"},
            "sample_requirements": ["Tubo Tapa Morada"],
            "selected_items": [{"code": "P001", "name": "Perfil Renal", "item_type": "profile"}],
            "notes": "Muestras recibidas",
        },
    }]

    def fake_fetch_rows(table, _select="*", _limit=500):
        if table == "lab_samples":
            return sample_rows
        if table == "lab_sample_events":
            return event_rows
        return []

    with patch("app.dashboard.db.list_clients_with_assignment", return_value=[]), \
         patch("app.dashboard.db.list_requests", return_value=[]), \
         patch("app.dashboard.db.list_sessions", return_value=[]), \
         patch("app.dashboard.db.list_conversation_messages", return_value=[]), \
         patch("app.dashboard.db.list_catalog_tests", return_value=[]), \
         patch("app.dashboard.db.list_catalog_profiles", return_value=[], create=True), \
         patch("app.dashboard.db.list_a3_knowledge_index", return_value=[]), \
         patch("app.dashboard.db.fetch_rows", side_effect=fake_fetch_rows), \
         patch("app.dashboard.db.list_pending_client_reviews", return_value=[]), \
         patch("app.dashboard.db.list_active_couriers", return_value=[]), \
         patch("app.dashboard.db.list_courier_locality_coverage", return_value=[]):
        from app.dashboard import build_dashboard_context

        context = build_dashboard_context()

    received_lane = next(lane for lane in context["sample_process_lanes"] if lane["status_key"] == "received_lab")
    assert received_lane["count"] == 1
    card = received_lane["cards"][0]
    assert card["client_name"] == "Clinica Norte"
    assert card["profile_name"] == "Perfil Renal"
    assert card["profile_code"] == "P001"
    assert card["sample_requirements"] == ["Tubo Tapa Morada"]
    assert card["events"][0]["event_type"] == "profile_assigned_from_dashboard"


def test_samples_page_renders_profile_builder_catalog(monkeypatch):
    monkeypatch.setattr("app.dashboard.DASHBOARD_ADMIN_USER", "admin")
    monkeypatch.setattr("app.dashboard.DASHBOARD_ADMIN_PASSWORD", "secret")
    context = {
        "summary": {},
        "request_status": {},
        "requests": [],
        "messages": [],
        "samples": [],
        "clients_rows": [{"client_id": "client-1", "display_name": "Clinica Norte", "clinic_name": "Clinica Norte"}],
        "profile_catalog_rows": [{"code": "P001", "name": "Perfil Renal", "category": "Renal", "species": "canino", "description": "Control renal", "price": 50000}],
        "profile_analysis_rows": [{"code": "H001", "name": "Hemograma", "category": "Hematologia", "species": "ambos", "sample": "Tubo Tapa Morada", "price": 10000}],
        "profile_builder_items": [
            {"item_type": "profile", "code": "P001", "name": "Perfil Renal", "category": "Renal", "species": "canino", "sample": "Perfil", "price": 50000, "description": "Control renal"},
            {"item_type": "analysis", "code": "H001", "name": "Hemograma", "category": "Hematologia", "species": "ambos", "sample": "Tubo Tapa Morada", "price": 10000, "description": ""},
        ],
        "profile_categories": ["Hematologia", "Renal"],
        "profile_species": ["ambos", "canino"],
        "sample_requirements": ["Tubo Tapa Morada"],
        "sample_process_lanes": [{"status_key": "received_lab", "label": "Recibida laboratorio", "count": 1, "cards": [{"sample_id": "sample-1", "client_name": "Clinica Norte", "profile_name": "Perfil Renal", "profile_code": "P001", "sample_type": "Perfil personalizado", "sample_requirements": ["Tubo Tapa Morada"], "priority": "normal", "created_at": "2026-05-12T10:00:00", "events": []}]}],
    }

    with patch("app.dashboard.build_dashboard_context", return_value=context):
        client = _get_test_client()
        client.post("/login", data={"username": "admin", "password": "secret"})
        response = client.get("/muestras")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Constructor personalizado" in body
    assert "Perfil Renal" in body
    assert "Hemograma" in body
    assert "data-builder-add" in body
    assert "data-builder-accept" in body
    assert "Usar perfil" in body
    assert "Agregar analisis" in body
    assert "Agregar analisis extra" in body
    assert "applyBuilderCatalogFilters" in body
    assert "Resumen para cliente" in body
    assert "Proceso de muestras" in body
    assert "data-sample-process-board" in body
    assert "data-sample-process-card" in body
    assert "Tubo Tapa Morada" in body


def test_samples_page_demo_mode_renders_mock_process_lanes(monkeypatch):
    monkeypatch.setattr("app.dashboard.DASHBOARD_ADMIN_USER", "admin")
    monkeypatch.setattr("app.dashboard.DASHBOARD_ADMIN_PASSWORD", "secret")
    context = {
        "summary": {},
        "request_status": {},
        "requests": [],
        "messages": [],
        "samples": [],
        "clients_rows": [],
        "profile_catalog_rows": [],
        "profile_analysis_rows": [],
        "profile_builder_items": [],
        "profile_categories": [],
        "profile_species": [],
        "sample_requirements": [],
        "sample_process_lanes": [],
    }

    with patch("app.dashboard.build_dashboard_context", return_value=context):
        client = _get_test_client()
        client.post("/login", data={"username": "admin", "password": "secret"})
        response = client.get("/muestras?demo=1")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Modo demo" in body
    assert "Demo A retirar" in body
    assert "Demo Recibida laboratorio" in body
    assert "Demo Analizados resultados listos" in body
    assert "data-demo-sample-card" in body


def test_new_client_page_requires_login():
    client = _get_test_client()

    response = client.get("/clientes/nuevo")

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_new_client_form_creates_pending_review(monkeypatch):
    monkeypatch.setattr("app.dashboard.DASHBOARD_ADMIN_USER", "admin")
    monkeypatch.setattr("app.dashboard.DASHBOARD_ADMIN_PASSWORD", "secret")

    payload = {
        "clinic_name": "Clinica Revision",
        "tax_id": "900123456",
        "phone": "3001234567",
        "email": "ops@example.com",
        "billing_email": "facturas@example.com",
        "address": "Calle 10 # 20-30",
        "zone": "Norte",
        "billing_type": "credit",
        "client_type": "empresa",
        "vat_regime": "responsable_iva",
        "electronic_invoicing": "si",
        "contact_name": "Dra Laura",
        "rut_received": "on",
        "chamber_received": "on",
        "courier_id": "courier-1",
        "notes": "Validar documentos",
    }

    with patch("app.dashboard.db.find_client_for_dashboard", return_value=None), \
         patch("app.dashboard.db.list_active_couriers", return_value=[{"id": "courier-1", "name": "Luis Moto"}]), \
         patch("app.dashboard.db.create_pending_client_review", return_value={"request_id": "req-1", "client_id": "client-1"}) as create_review, \
         patch("app.dashboard.db.upsert_client_profile", return_value=None):
        client = _get_test_client()
        client.post("/login", data={"username": "admin", "password": "secret"})
        response = client.post("/clientes/nuevo", data=payload)

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/aprobaciones?notice=Cliente+enviado+a+revision&notice_type=ok")
    create_review.assert_called_once()
    review_payload = create_review.call_args.kwargs["client_payload"]
    assert review_payload["clinic_name"] == "Clinica Revision"
    assert review_payload["is_active"] is False
    assert create_review.call_args.kwargs["review_payload"]["documents"]["rut_received"] is True
    assert create_review.call_args.kwargs["review_payload"]["courier_id"] == "courier-1"


def test_new_client_form_persists_complete_profile(monkeypatch):
    monkeypatch.setattr("app.dashboard.DASHBOARD_ADMIN_USER", "admin")
    monkeypatch.setattr("app.dashboard.DASHBOARD_ADMIN_PASSWORD", "secret")

    payload = {
        "clinic_name": "Clinica Completa SAS",
        "commercial_name": "Clinica Completa",
        "client_code": "A3-999",
        "client_type": "empresa",
        "tax_id": "900999111",
        "phone": "3009991111",
        "email": "contacto@completa.test",
        "billing_email": "facturas@completa.test",
        "address": "Calle 99 # 1-23",
        "zone": "Kennedy",
        "billing_type": "credit",
        "vat_regime": "responsable_iva",
        "electronic_invoicing": "si",
        "invoicing_rut_url": "https://docs.example/rut.pdf",
        "contact_name": "Dra Completa",
        "entered_flag": "on",
        "rut_received": "on",
        "notes": "Cliente con datos completos",
    }

    with patch("app.dashboard.db.find_client_for_dashboard", return_value=None), \
         patch("app.dashboard.db.list_active_couriers", return_value=[]), \
         patch("app.dashboard.db.create_pending_client_review", return_value={"request_id": "req-2", "client_id": "client-2"}) as create_review, \
         patch("app.dashboard.db.upsert_client_profile", return_value=None) as upsert_profile:
        client = _get_test_client()
        client.post("/login", data={"username": "admin", "password": "secret"})
        response = client.post("/clientes/nuevo", data=payload)

    assert response.status_code == 302
    create_review.assert_called_once()
    review_payload = create_review.call_args.kwargs["review_payload"]
    assert review_payload["profile"]["commercial_name"] == "Clinica Completa"
    assert review_payload["profile"]["billing_email"] == "facturas@completa.test"
    assert review_payload["profile"]["electronic_invoicing"] is True

    upsert_profile.assert_called_once()
    profile_payload = upsert_profile.call_args.args[0]
    assert profile_payload["clinic_key"] == "clinica_completa_sas"
    assert profile_payload["client_code"] == "A3-999"
    assert profile_payload["client_type"] == "empresa"
    assert profile_payload["vat_regime"] == "responsable_iva"
    assert profile_payload["entered_flag"] is True


def test_new_client_page_lists_active_couriers(monkeypatch):
    monkeypatch.setattr("app.dashboard.DASHBOARD_ADMIN_USER", "admin")
    monkeypatch.setattr("app.dashboard.DASHBOARD_ADMIN_PASSWORD", "secret")

    with patch("app.dashboard.db.list_active_couriers", return_value=[{"id": "courier-1", "name": "Luis Moto"}]):
        client = _get_test_client()
        client.post("/login", data={"username": "admin", "password": "secret"})
        response = client.get("/clientes/nuevo")

    assert response.status_code == 200
    assert "Luis Moto" in response.get_data(as_text=True)


def test_new_client_form_rejects_duplicate(monkeypatch):
    monkeypatch.setattr("app.dashboard.DASHBOARD_ADMIN_USER", "admin")
    monkeypatch.setattr("app.dashboard.DASHBOARD_ADMIN_PASSWORD", "secret")

    with patch("app.dashboard.db.find_client_for_dashboard", return_value={"clinic_name": "Existente"}):
        client = _get_test_client()
        client.post("/login", data={"username": "admin", "password": "secret"})
        response = client.post(
            "/clientes/nuevo",
            data={
                "clinic_name": "Nueva",
                "tax_id": "900",
                "phone": "300",
                "email": "nueva@example.com",
                "billing_email": "facturas-nueva@example.com",
                "address": "Calle",
                "zone": "Norte",
                "client_type": "empresa",
                "vat_regime": "responsable_iva",
                "electronic_invoicing": "si",
                "contact_name": "Dra Nueva",
            },
        )

    assert response.status_code == 200
    assert "Ya existe un cliente" in response.get_data(as_text=True)


def test_new_client_form_requires_complete_registration_fields(monkeypatch):
    monkeypatch.setattr("app.dashboard.DASHBOARD_ADMIN_USER", "admin")
    monkeypatch.setattr("app.dashboard.DASHBOARD_ADMIN_PASSWORD", "secret")

    with patch("app.dashboard.db.find_client_for_dashboard", return_value=None), \
         patch("app.dashboard.db.list_active_couriers", return_value=[]), \
         patch("app.dashboard.db.create_pending_client_review") as create_review, \
         patch("app.dashboard.db.upsert_client_profile") as upsert_profile:
        client = _get_test_client()
        client.post("/login", data={"username": "admin", "password": "secret"})
        response = client.post(
            "/clientes/nuevo",
            data={"clinic_name": "Incompleta", "tax_id": "900", "phone": "300", "address": "Calle", "zone": "Norte"},
        )

    assert response.status_code == 200
    assert "Completa todos los campos obligatorios" in response.get_data(as_text=True)
    create_review.assert_not_called()
    upsert_profile.assert_not_called()


@pytest.mark.parametrize(
    ("payload", "expected_profile"),
    [
        (
            {
                "clinic_name": "Clinica Falsa Norte SAS",
                "commercial_name": "Falsa Norte",
                "client_code": "FAKE-001",
                "client_type": "empresa",
                "tax_id": "900111222",
                "phone": "3001112222",
                "email": "contacto@falsanorte.test",
                "billing_email": "facturas@falsanorte.test",
                "address": "Carrera 1 # 2-03",
                "zone": "Usaquen",
                "billing_type": "credit",
                "vat_regime": "responsable_iva",
                "electronic_invoicing": "si",
                "contact_name": "Laura Fake",
                "rut_received": "on",
                "chamber_received": "on",
                "entered_flag": "on",
                "notes": "Prueba empresa credito",
            },
            {"client_type": "empresa", "vat_regime": "responsable_iva", "electronic_invoicing": True, "entered_flag": True},
        ),
        (
            {
                "clinic_name": "Consultorio Falso Sur",
                "commercial_name": "Falso Sur",
                "client_code": "FAKE-002",
                "client_type": "es_persona",
                "tax_id": "52111222",
                "phone": "3003334444",
                "email": "contacto@falsosur.test",
                "billing_email": "facturas@falsosur.test",
                "address": "Calle 80 # 10-20",
                "zone": "Kennedy",
                "billing_type": "cash",
                "vat_regime": "no_responsable_iva",
                "electronic_invoicing": "no",
                "contact_name": "Carlos Fake",
                "representative_id_received": "on",
                "notes": "Prueba persona contado",
            },
            {"client_type": "es_persona", "vat_regime": "no_responsable_iva", "electronic_invoicing": False, "entered_flag": False},
        ),
    ],
)
def test_new_client_form_accepts_multiple_fake_complete_registrations(monkeypatch, payload, expected_profile):
    monkeypatch.setattr("app.dashboard.DASHBOARD_ADMIN_USER", "admin")
    monkeypatch.setattr("app.dashboard.DASHBOARD_ADMIN_PASSWORD", "secret")

    with patch("app.dashboard.db.find_client_for_dashboard", return_value=None), \
         patch("app.dashboard.db.list_active_couriers", return_value=[]), \
         patch("app.dashboard.db.create_pending_client_review", return_value={"request_id": "req-fake", "client_id": "client-fake"}) as create_review, \
         patch("app.dashboard.db.upsert_client_profile", return_value=None) as upsert_profile:
        client = _get_test_client()
        client.post("/login", data={"username": "admin", "password": "secret"})
        response = client.post("/clientes/nuevo", data=payload)

    assert response.status_code == 302
    create_review.assert_called_once()
    upsert_profile.assert_called_once()
    profile_payload = upsert_profile.call_args.args[0]
    for key, value in expected_profile.items():
        assert profile_payload[key] == value
    assert profile_payload["client_code"] == payload["client_code"]
    assert profile_payload["billing_email"] == payload["billing_email"]


def test_approval_post_activates_pending_client(monkeypatch):
    monkeypatch.setattr("app.dashboard.DASHBOARD_ADMIN_USER", "admin")
    monkeypatch.setattr("app.dashboard.DASHBOARD_ADMIN_PASSWORD", "secret")

    with patch("app.dashboard.db.approve_pending_client", return_value=True) as approve:
        client = _get_test_client()
        client.post("/login", data={"username": "admin", "password": "secret"})
        response = client.post("/aprobaciones/decision", data={"request_id": "req-1", "decision": "approve"})

    assert response.status_code == 302
    assert "notice=Cliente+aprobado" in response.headers["Location"]
    approve.assert_called_once_with("req-1")


def test_approve_pending_client_assigns_courier(monkeypatch):
    calls = []

    class FakeQuery:
        def __init__(self, table, action="select", payload=None):
            self.table = table
            self.action = action
            self.payload = payload
            self.filters = []

        def select(self, *_args):
            return self

        def eq(self, field, value):
            self.filters.append((field, value))
            return self

        def order(self, *_args, **_kwargs):
            return self

        def limit(self, *_args):
            return self

        def update(self, payload):
            self.action = "update"
            self.payload = payload
            return self

        def insert(self, payload):
            self.action = "insert"
            self.payload = payload
            return self

        def execute(self):
            calls.append((self.table, self.action, self.payload, tuple(self.filters)))
            if self.table == "requests" and self.action == "select":
                return type("Result", (), {"data": [{"id": "req-1", "client_id": "client-1"}]})()
            if self.table == "request_events" and self.action == "select":
                return type("Result", (), {"data": [{"event_payload": {"courier_id": "courier-1"}}]})()
            return type("Result", (), {"data": [{}]})()

    class FakeClient:
        def table(self, table):
            return FakeQuery(table)

    monkeypatch.setattr("app.services.db._client", FakeClient())

    from app.services import db

    assert db.approve_pending_client("req-1") is True
    assert ("client_courier_assignment", "insert", {"client_id": "client-1", "courier_id": "courier-1", "assigned_by": "dashboard_review"}, ()) in calls


def test_motorizados_page_requires_login():
    client = _get_test_client()

    response = client.get("/motorizados")

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_motorizados_context_uses_internal_territory_when_db_coverage_is_empty(monkeypatch):
    with patch("app.dashboard.db.list_active_couriers", return_value=[]), \
         patch("app.dashboard.db.list_courier_locality_coverage", return_value=[]):
        from app.dashboard import _build_motorizados_context

        context = _build_motorizados_context([])

    by_zone = {row["zone_number"]: row for row in context["territorial_zone_rows"]}
    by_courier = {row["name"]: row for row in context["couriers_rows"]}

    assert by_zone[1]["courier_name"] == "Javier"
    assert by_zone[5]["courier_name"] == "Gerardo"
    assert by_zone[8]["total_barrios"] == 161
    assert by_courier["Javier"]["zone_number"] == 1
    assert by_courier["Javier"]["phone"] == ""
    assert "San Cristobal" in by_courier["Javier"]["localities_text"]


def test_courier_phone_endpoint_updates_phone(monkeypatch):
    monkeypatch.setattr("app.dashboard.DASHBOARD_ADMIN_USER", "admin")
    monkeypatch.setattr("app.dashboard.DASHBOARD_ADMIN_PASSWORD", "secret")

    with patch("app.dashboard.db.update_courier_phone", return_value=True) as update_phone:
        client = _get_test_client()
        client.post("/login", data={"username": "admin", "password": "secret"})
        response = client.post("/api/dashboard/courier-phone", json={"courier_id": "courier-1", "phone": "300 123 4567"})

    assert response.status_code == 200
    assert response.get_json()["phone"] == "3001234567"
    update_phone.assert_called_once_with("courier-1", "3001234567")


def test_locality_assignment_endpoint_updates_coverage(monkeypatch):
    monkeypatch.setattr("app.dashboard.DASHBOARD_ADMIN_USER", "admin")
    monkeypatch.setattr("app.dashboard.DASHBOARD_ADMIN_PASSWORD", "secret")

    with patch("app.dashboard.db.upsert_courier_locality_coverage", return_value=None) as upsert:
        client = _get_test_client()
        client.post("/login", data={"username": "admin", "password": "secret"})
        response = client.post("/api/dashboard/courier-locality-assignment", json={"locality_code": "kennedy", "courier_id": "courier-1"})

    assert response.status_code == 200
    assert response.get_json()["locality_name"] == "Kennedy"
    upsert.assert_called_once_with(locality_code="kennedy", locality_name="Kennedy", courier_id="courier-1", assigned_by="dashboard:admin")


def test_client_assignment_endpoint_updates_assignment(monkeypatch):
    monkeypatch.setattr("app.dashboard.DASHBOARD_ADMIN_USER", "admin")
    monkeypatch.setattr("app.dashboard.DASHBOARD_ADMIN_PASSWORD", "secret")

    with patch("app.dashboard.db.upsert_client_assignment", return_value=None) as upsert:
        client = _get_test_client()
        client.post("/login", data={"username": "admin", "password": "secret"})
        response = client.post("/api/dashboard/client-assignment", json={"client_id": "client-1", "courier_id": "courier-1"})

    assert response.status_code == 200
    upsert.assert_called_once_with(client_id="client-1", courier_id="courier-1", assigned_by="dashboard:admin")


def test_client_delete_endpoint_deletes_client_completely(monkeypatch):
    monkeypatch.setattr("app.dashboard.DASHBOARD_ADMIN_USER", "admin")
    monkeypatch.setattr("app.dashboard.DASHBOARD_ADMIN_PASSWORD", "secret")

    with patch("app.dashboard.db.delete_client_completely", return_value=True, create=True) as delete_client:
        client = _get_test_client()
        client.post("/login", data={"username": "admin", "password": "secret"})
        response = client.post(
            "/api/dashboard/client-delete",
            json={"client_id": "client-1", "clinic_key": "clinica_norte"},
        )

    assert response.status_code == 200
    assert response.get_json() == {"ok": True, "client_id": "client-1"}
    delete_client.assert_called_once_with(client_id="client-1", clinic_key="clinica_norte")


def test_client_delete_endpoint_returns_not_found_when_client_missing(monkeypatch):
    monkeypatch.setattr("app.dashboard.DASHBOARD_ADMIN_USER", "admin")
    monkeypatch.setattr("app.dashboard.DASHBOARD_ADMIN_PASSWORD", "secret")

    with patch("app.dashboard.db.delete_client_completely", return_value=False, create=True):
        client = _get_test_client()
        client.post("/login", data={"username": "admin", "password": "secret"})
        response = client.post("/api/dashboard/client-delete", json={"client_id": "missing"})

    assert response.status_code == 404
    assert response.get_json()["error"] == "Client not found"


def test_delete_client_completely_removes_related_rows_before_client(monkeypatch):
    calls = []

    class FakeQuery:
        def __init__(self, table, action="select", payload=None):
            self.table = table
            self.action = action
            self.payload = payload
            self.filters = []

        def select(self, *_args):
            return self

        def eq(self, field, value):
            self.filters.append(("eq", field, value))
            return self

        def in_(self, field, values):
            self.filters.append(("in", field, tuple(values)))
            return self

        def delete(self):
            self.action = "delete"
            return self

        def execute(self):
            calls.append((self.table, self.action, tuple(self.filters)))
            if self.table == "clients" and self.action == "select":
                return type("Result", (), {"data": [{"id": "client-1", "clinic_name": "Clinica Norte"}]})()
            if self.table == "requests" and self.action == "select":
                return type("Result", (), {"data": [{"id": "req-1"}, {"id": "req-2"}]})()
            if self.table == "lab_samples" and self.action == "select":
                return type("Result", (), {"data": [{"id": "sample-1"}]})()
            if self.action == "delete":
                return type("Result", (), {"data": [{"deleted": True}]})()
            return type("Result", (), {"data": []})()

    class FakeClient:
        def table(self, table):
            return FakeQuery(table)

    monkeypatch.setattr("app.services.db._client", FakeClient())

    from app.services import db

    assert db.delete_client_completely(client_id="client-1", clinic_key="clinica_norte") is True
    delete_calls = [call for call in calls if call[1] == "delete"]
    assert delete_calls == [
        ("request_events", "delete", (("in", "request_id", ("req-1", "req-2")),)),
        ("lab_sample_events", "delete", (("in", "sample_id", ("sample-1",)),)),
        ("lab_samples", "delete", (("eq", "client_id", "client-1"),)),
        ("requests", "delete", (("eq", "client_id", "client-1"),)),
        ("client_courier_assignment", "delete", (("eq", "client_id", "client-1"),)),
        ("telegram_sessions", "delete", (("eq", "client_id", "client-1"),)),
        ("clients_a3_sample_events", "delete", (("eq", "clinic_key", "clinica_norte"),)),
        ("clients_a3_knowledge", "delete", (("eq", "clinic_key", "clinica_norte"),)),
        ("clients", "delete", (("eq", "id", "client-1"),)),
    ]


def test_request_operation_endpoint_logs_manual_update(monkeypatch):
    monkeypatch.setattr("app.dashboard.DASHBOARD_ADMIN_USER", "admin")
    monkeypatch.setattr("app.dashboard.DASHBOARD_ADMIN_PASSWORD", "secret")

    with patch("app.dashboard.db.update_request", return_value=True) as update_request, \
         patch("app.dashboard.db.create_request_event", return_value=None) as create_event:
        client = _get_test_client()
        client.post("/login", data={"username": "admin", "password": "secret"})
        response = client.post("/api/dashboard/request-operation", json={"request_id": "req-1", "priority": "alta", "sample_count": "3", "sample_types": ["Sangre", "Orina", "Sangre"]})

    assert response.status_code == 200
    body = response.get_json()
    assert body["priority"] == "high"
    assert body["sample_count"] == 3
    assert body["sample_types"] == ["Sangre", "Orina"]
    update_request.assert_called_once_with("req-1", {"priority": "urgent"})
    assert create_event.call_args.args[1] == "dashboard_request_manual_update"


def test_request_status_endpoint_updates_request(monkeypatch):
    monkeypatch.setattr("app.dashboard.DASHBOARD_ADMIN_USER", "admin")
    monkeypatch.setattr("app.dashboard.DASHBOARD_ADMIN_PASSWORD", "secret")

    with patch("app.dashboard.db.update_request", return_value=True) as update_request, \
         patch("app.dashboard.db.create_request_event", return_value=None) as create_event:
        client = _get_test_client()
        client.post("/login", data={"username": "admin", "password": "secret"})
        response = client.post("/api/dashboard/request-status", json={"request_id": "req-1", "status": "assigned"})

    assert response.status_code == 200
    assert response.get_json()["status_label"] == "Asignada"
    update_request.assert_called_once_with("req-1", {"status": "assigned"})
    assert create_event.call_args.args[1] == "dashboard_status_update"


def test_sample_status_endpoint_updates_lab_sample(monkeypatch):
    monkeypatch.setattr("app.dashboard.DASHBOARD_ADMIN_USER", "admin")
    monkeypatch.setattr("app.dashboard.DASHBOARD_ADMIN_PASSWORD", "secret")

    with patch("app.dashboard.db.update_rows", return_value=[{"id": "sample-1"}]) as update_rows, \
         patch("app.dashboard.db.insert_rows", return_value=[{"id": "event-1"}]) as insert_rows:
        client = _get_test_client()
        client.post("/login", data={"username": "admin", "password": "secret"})
        response = client.post("/api/dashboard/sample-status", json={"sample_id": "sample-1", "status": "pending_pickup"})

    assert response.status_code == 200
    assert response.get_json()["persistence_mode"] == "lab_samples_and_event"
    update_rows.assert_called_once_with("lab_samples", {"id": "sample-1"}, {"status": "pending_pickup"})
    assert insert_rows.call_args.args[0] == "lab_sample_events"


def test_profile_assignment_endpoint_registers_selected_items_as_received_samples(monkeypatch):
    monkeypatch.setattr("app.dashboard.DASHBOARD_ADMIN_USER", "admin")
    monkeypatch.setattr("app.dashboard.DASHBOARD_ADMIN_PASSWORD", "secret")

    profile = {"code": "P001", "name": "Perfil Renal", "category": "Renal", "species": "canino", "price": 50000, "description": "Control renal"}
    analysis = {"code": "H001", "name": "Hemograma", "category": "Hematologia", "species": "ambos", "sample": "Tubo Tapa Morada", "price": 10000}

    def fake_insert(table, rows):
        if table == "lab_samples":
            return [{"id": f"sample-{index + 1}"} for index, _row in enumerate(rows)]
        return [{"id": "event-1"}]

    with patch("app.dashboard.db.list_catalog_profiles", return_value=[profile]), \
         patch("app.dashboard.db.list_catalog_tests", return_value=[analysis]), \
         patch("app.dashboard.db.insert_rows", side_effect=fake_insert) as insert_rows:
        client = _get_test_client()
        client.post("/login", data={"username": "admin", "password": "secret"})
        response = client.post(
            "/api/dashboard/profile-assignment",
            json={
                "client_id": "11111111-1111-4111-8111-111111111111",
                "items": [{"item_type": "profile", "code": "P001"}, {"item_type": "analysis", "code": "H001"}],
                "priority": "normal",
                "notes": "Muestras recibidas en sede",
            },
        )

    assert response.status_code == 200
    body = response.get_json()
    assert body["created_count"] == 2
    assert body["status"] == "pending_pickup"
    sample_rows = insert_rows.call_args_list[0].args[1]
    assert sample_rows[0]["test_code"] == "P001"
    assert sample_rows[0]["test_name"] == "Perfil Renal"
    assert sample_rows[0]["sample_type"] == "Perfil personalizado"
    assert sample_rows[1]["test_code"] == "H001"
    assert sample_rows[1]["sample_type"] == "Tubo Tapa Morada"
    assert all(row["status"] == "pending_pickup" for row in sample_rows)
    assert all(row["client_id"] == "11111111-1111-4111-8111-111111111111" for row in sample_rows)
    event_rows = insert_rows.call_args_list[1].args[1]
    assert event_rows[0]["event_type"] == "profile_assigned_from_dashboard"
    assert event_rows[0]["event_payload"]["sample_requirements"] == ["Tubo Tapa Morada"]


def test_profile_assignment_endpoint_requires_client_and_items(monkeypatch):
    monkeypatch.setattr("app.dashboard.DASHBOARD_ADMIN_USER", "admin")
    monkeypatch.setattr("app.dashboard.DASHBOARD_ADMIN_PASSWORD", "secret")

    client = _get_test_client()
    client.post("/login", data={"username": "admin", "password": "secret"})
    response = client.post("/api/dashboard/profile-assignment", json={"client_id": "", "items": []})

    assert response.status_code == 400
    assert response.get_json()["error"] == "Missing client_id"


def test_client_profile_endpoint_updates_advanced_profile(monkeypatch):
    monkeypatch.setattr("app.dashboard.DASHBOARD_ADMIN_USER", "admin")
    monkeypatch.setattr("app.dashboard.DASHBOARD_ADMIN_PASSWORD", "secret")

    with patch("app.dashboard.db.upsert_client_profile", return_value=None) as upsert_profile:
        client = _get_test_client()
        client.post("/login", data={"username": "admin", "password": "secret"})
        response = client.post("/api/dashboard/client-profile", json={"client_id": "client-1", "clinic_key": "clinica_norte", "clinic_name": "Clinica Norte", "field": "billing_email", "value": "facturas@example.com"})

    assert response.status_code == 200
    payload = upsert_profile.call_args.args[0]
    assert payload["clinic_key"] == "clinica_norte"
    assert payload["billing_email"] == "facturas@example.com"


def test_client_name_edit_updates_client_table_and_knowledge(monkeypatch):
    monkeypatch.setattr("app.dashboard.DASHBOARD_ADMIN_USER", "admin")
    monkeypatch.setattr("app.dashboard.DASHBOARD_ADMIN_PASSWORD", "secret")

    with patch("app.dashboard.db.update_client_profile", return_value=True) as update_client, \
         patch("app.dashboard.db.upsert_client_profile", return_value=None) as upsert_profile:
        client = _get_test_client()
        client.post("/login", data={"username": "admin", "password": "secret"})
        response = client.post("/api/dashboard/client-profile", json={
            "client_id": "client-1",
            "clinic_key": "clinica_norte",
            "clinic_name": "Clinica Norte",
            "field": "clinic_name",
            "value": "Clinica Norte Renombrada",
        })

    assert response.status_code == 200
    update_client.assert_called_once_with("client-1", {"clinic_name": "Clinica Norte Renombrada"})
    upsert_profile.assert_called_once()
    profile_payload = upsert_profile.call_args.args[0]
    assert profile_payload["clinic_key"] == "clinica_norte"
    assert profile_payload["clinic_name"] == "Clinica Norte Renombrada"
