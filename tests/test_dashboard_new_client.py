from unittest.mock import patch


def _get_test_client():
    from app.main import app

    app.config["TESTING"] = True
    return app.test_client()


def _login(client, monkeypatch):
    monkeypatch.setattr("app.dashboard.DASHBOARD_ADMIN_USER", "admin")
    monkeypatch.setattr("app.dashboard.DASHBOARD_ADMIN_PASSWORD", "secret")
    client.post("/login", data={"username": "admin", "password": "secret"})


def _valid_payload(**overrides):
    payload = {
        "clinic_name": "Clinica Pruebas SAS",
        "commercial_name": "Clinica Pruebas",
        "client_code": "A3-TEST",
        "client_type": "empresa",
        "tax_id": "900123456",
        "phone": "3001234567",
        "email": "contacto@pruebas.test",
        "billing_email": "facturas@pruebas.test",
        "address": "Calle 10 # 20-30",
        "zone": "Kennedy",
        "billing_type": "credit",
        "vat_regime": "responsable_iva",
        "electronic_invoicing": "si",
        "contact_name": "Dra Pruebas",
        "rut_received": "on",
    }
    payload.update(overrides)
    return payload


def test_new_client_form_normalizes_phone_before_lookup_and_persistence(monkeypatch):
    with patch("app.dashboard.db.find_client_for_dashboard", return_value=None) as find_client, \
         patch("app.dashboard.db.list_active_couriers", return_value=[]), \
         patch("app.dashboard.db.create_pending_client_review", return_value={"request_id": "req-1", "client_id": "client-1"}) as create_review, \
         patch("app.dashboard.db.upsert_client_profile", return_value=None):
        client = _get_test_client()
        _login(client, monkeypatch)
        response = client.post("/clientes/nuevo", data=_valid_payload(phone="300 123-4567"))

    assert response.status_code == 302
    find_client.assert_called_once_with(
        tax_id="900123456",
        phone="3001234567",
        clinic_name="Clinica Pruebas SAS",
    )
    assert create_review.call_args.kwargs["client_payload"]["phone"] == "3001234567"


def test_new_client_form_rejects_invalid_select_values(monkeypatch):
    with patch("app.dashboard.db.find_client_for_dashboard") as find_client, \
         patch("app.dashboard.db.list_active_couriers", return_value=[]), \
         patch("app.dashboard.db.create_pending_client_review") as create_review, \
         patch("app.dashboard.db.upsert_client_profile") as upsert_profile:
        client = _get_test_client()
        _login(client, monkeypatch)
        response = client.post(
            "/clientes/nuevo",
            data=_valid_payload(
                client_type="cliente_invalido",
                vat_regime="regimen_invalido",
                electronic_invoicing="talvez",
            ),
        )

    assert response.status_code == 200
    assert "Selecciona opciones validas" in response.get_data(as_text=True)
    find_client.assert_not_called()
    create_review.assert_not_called()
    upsert_profile.assert_not_called()


def test_new_client_form_rejects_unknown_courier(monkeypatch):
    with patch("app.dashboard.db.find_client_for_dashboard") as find_client, \
         patch("app.dashboard.db.list_active_couriers", return_value=[{"id": "courier-1", "name": "Luis Moto"}]), \
         patch("app.dashboard.db.create_pending_client_review") as create_review, \
         patch("app.dashboard.db.upsert_client_profile") as upsert_profile:
        client = _get_test_client()
        _login(client, monkeypatch)
        response = client.post("/clientes/nuevo", data=_valid_payload(courier_id="courier-falso"))

    assert response.status_code == 200
    assert "Selecciona un motorizado valido" in response.get_data(as_text=True)
    find_client.assert_not_called()
    create_review.assert_not_called()
    upsert_profile.assert_not_called()


def test_courier_suggestion_endpoint_matches_neighborhood(monkeypatch):
    with patch("app.dashboard.db.list_active_couriers", return_value=[{"id": "courier-marlon", "name": "Marlon"}]):
        client = _get_test_client()
        _login(client, monkeypatch)
        response = client.get("/api/dashboard/courier-suggestion?neighborhood=Bosa&locality=Bosa")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["matched"] is True
    assert payload["zone_number"] == 7
    assert payload["courier_name"] == "Marlon"
    assert payload["courier_id"] == "courier-marlon"
    assert payload["match_type"] == "neighborhood"


def test_neighborhood_search_endpoint_returns_zone_and_courier(monkeypatch):
    client = _get_test_client()
    _login(client, monkeypatch)
    response = client.get("/api/dashboard/neighborhood-search?q=casti")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["count"] >= 1
    castilla = next(row for row in payload["rows"] if row["neighborhood_name"] == "Castilla")
    assert castilla["locality_name"] == "Kennedy"
    assert castilla["zone_number"] == 3
    assert castilla["courier_name"] == "Diego"


def test_new_client_form_auto_assigns_suggested_courier_when_manual_is_empty(monkeypatch):
    with patch("app.dashboard.db.find_client_for_dashboard", return_value=None), \
         patch("app.dashboard.db.list_active_couriers", return_value=[{"id": "courier-diego", "name": "Diego"}]), \
         patch("app.dashboard.db.create_pending_client_review", return_value={"request_id": "req-1", "client_id": "client-1"}) as create_review, \
         patch("app.dashboard.db.upsert_client_profile", return_value=None):
        client = _get_test_client()
        _login(client, monkeypatch)
        response = client.post(
            "/clientes/nuevo",
            data=_valid_payload(neighborhood="Castilla", locality="Kennedy", zone="Kennedy", courier_id=""),
        )

    assert response.status_code == 302
    review_payload = create_review.call_args.kwargs["review_payload"]
    assert review_payload["courier_id"] == "courier-diego"
    assert review_payload["courier_suggestion"]["zone_number"] == 3
    assert review_payload["courier_suggestion"]["match_type"] == "neighborhood"


def test_dashboard_context_includes_motorizados_data_from_real_builder():
    with patch("app.dashboard.db.list_clients_with_assignment", return_value=[{"id": "client-1", "clinic_name": "Clinica Kennedy", "zone": "Kennedy"}]), \
         patch("app.dashboard.db.list_requests", return_value=[]), \
         patch("app.dashboard.db.list_sessions", return_value=[]), \
         patch("app.dashboard.db.list_conversation_messages", return_value=[]), \
         patch("app.dashboard.db.list_catalog_tests", return_value=[]), \
         patch("app.dashboard.db.list_a3_knowledge_index", return_value=[]), \
         patch("app.dashboard.db.fetch_rows", return_value=[]), \
         patch("app.dashboard.db.list_pending_client_reviews", return_value=[]), \
         patch("app.dashboard.db.list_active_couriers", return_value=[{"id": "courier-1", "name": "Luis Moto", "phone": "3001234567", "availability": "available"}]), \
         patch("app.dashboard.db.list_courier_locality_coverage", return_value=[{"locality_code": "kennedy", "locality_name": "Kennedy", "courier_id": "courier-1", "couriers": {"id": "courier-1", "name": "Luis Moto"}}]):
        from app.dashboard import build_dashboard_context

        context = build_dashboard_context()

    assert context["couriers_rows"][0]["name"] == "Luis Moto"
    assert context["motorizados_summary"]["busiest_courier_name"] == "Luis Moto"
    kennedy = next(row for row in context["localities_rows"] if row["locality_code"] == "kennedy")
    assert kennedy["assigned_courier_id"] == "courier-1"
    assert kennedy["clients_count"] == 1
