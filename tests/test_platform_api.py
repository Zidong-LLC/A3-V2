from unittest.mock import patch

# La API interna exige siempre X-Platform-Token (fail-closed). Coincide con el
# PLATFORM_API_TOKEN dummy que inyecta conftest.py.
AUTH = {"X-Platform-Token": "test-platform-token"}


def _get_test_client():
    from app.main import app

    app.config["TESTING"] = True
    return app.test_client()


def test_platform_overview_includes_unassigned_requests_and_stage_counts():
    clients = [
        {
            "id": "c-1",
            "clinic_name": "Clinica Uno",
            "client_courier_assignment": [
                {
                    "courier_id": "m-1",
                    "couriers": {"id": "m-1", "name": "Carlos", "phone": "300", "availability": "available"},
                }
            ],
        },
        {"id": "c-2", "clinic_name": "Clinica Dos", "client_courier_assignment": []},
    ]
    requests_rows = [
        {
            "id": "r-1",
            "status": "error_pending_assignment",
            "service_area": "route_scheduling",
            "assigned_courier_id": None,
            "clients": {"clinic_name": "Clinica Dos"},
            "fallback_reason": "no_courier_assigned",
            "scheduled_pickup_date": "2026-05-06",
        },
        {
            "id": "r-2",
            "status": "assigned",
            "service_area": "route_scheduling",
            "assigned_courier_id": "m-1",
            "clients": {"clinic_name": "Clinica Uno"},
            "fallback_reason": None,
            "scheduled_pickup_date": "2026-05-05",
        },
    ]
    sessions = [
        {"phase_current": "fase_2_recogida_datos", "requires_handoff": False},
        {"phase_current": "fase_2_recogida_datos", "requires_handoff": False},
        {"phase_current": "fase_7_escalado", "requires_handoff": True},
    ]

    with patch("app.platform_api.db.list_clients_with_assignment", return_value=clients), \
         patch("app.platform_api.db.list_requests", return_value=requests_rows), \
         patch("app.platform_api.db.list_sessions", return_value=sessions):
        client = _get_test_client()
        response = client.get("/api/platform/overview", headers=AUTH)

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["summary"]["total_clients"] == 2
    assert payload["summary"]["clients_without_courier"] == 1
    assert payload["summary"]["unassigned_requests"] == 1
    assert payload["requests_by_status"]["assigned"] == 1
    assert payload["requests_by_status"]["error_pending_assignment"] == 1
    assert payload["flow_stage_counts"][0]["stage_key"] == "fase_2_recogida_datos"


def test_platform_api_requires_token_when_configured(monkeypatch):
    monkeypatch.setattr("app.platform_api.PLATFORM_API_TOKEN", "secret-token")

    with patch("app.platform_api.db.list_clients_with_assignment", return_value=[]), \
         patch("app.platform_api.db.list_requests", return_value=[]), \
         patch("app.platform_api.db.list_sessions", return_value=[]):
        client = _get_test_client()
        unauthorized = client.get("/api/platform/overview")
        wrong_token = client.get(
            "/api/platform/overview",
            headers={"X-Platform-Token": "not-the-token"},
        )
        authorized = client.get(
            "/api/platform/overview",
            headers={"X-Platform-Token": "secret-token"},
        )

    assert unauthorized.status_code == 401
    assert wrong_token.status_code == 401
    assert authorized.status_code == 200


def test_platform_api_is_closed_when_token_is_not_configured(monkeypatch):
    """Sin PLATFORM_API_TOKEN la API queda CERRADA, no abierta.

    Regresión del hallazgo H1: el decorador dejaba pasar cuando la variable
    estaba vacía, y como no estaba definida en el entorno la API sirvió datos
    de clientes reales (NIT, teléfono, dirección) sin credenciales.
    """
    monkeypatch.setattr("app.platform_api.PLATFORM_API_TOKEN", "")

    with patch("app.platform_api.db.list_clients_with_assignment") as mock_clients:
        client = _get_test_client()
        sin_token = client.get("/api/platform/overview")
        con_token = client.get("/api/platform/overview", headers=AUTH)

    assert sin_token.status_code == 503
    assert con_token.status_code == 503
    # Ni siquiera llega a consultar la base de datos.
    mock_clients.assert_not_called()


def test_platform_request_status_update_validates_status_and_updates_request():
    request_id = "11111111-1111-1111-1111-111111111111"
    with patch("app.platform_api.db.update_request_status", return_value={"id": request_id, "status": "assigned"}) as mock_update:
        client = _get_test_client()

        invalid = client.patch(
            f"/api/platform/requests/{request_id}/status",
            json={"status": "invalid-status"},
            headers=AUTH,
        )
        valid = client.patch(
            f"/api/platform/requests/{request_id}/status",
            json={"status": "assigned", "assigned_courier_id": "m-10"},
            headers=AUTH,
        )

    assert invalid.status_code == 400
    assert valid.status_code == 200
    mock_update.assert_called_once_with(
        request_id=request_id,
        status="assigned",
        assigned_courier_id="m-10",
        fallback_reason=None,
    )


def test_platform_request_status_update_returns_not_found_for_invalid_request_id_format():
    client = _get_test_client()
    response = client.patch(
        "/api/platform/requests/not-a-uuid/status",
        json={"status": "assigned"},
        headers=AUTH,
    )

    assert response.status_code == 404


def test_platform_unassigned_requests_endpoint_filters_rows():
    rows = [
        {"id": "r-1", "status": "error_pending_assignment", "service_area": "route_scheduling", "assigned_courier_id": None},
        {"id": "r-2", "status": "assigned", "service_area": "route_scheduling", "assigned_courier_id": "m-1"},
    ]

    with patch("app.platform_api.db.list_requests", return_value=rows):
        client = _get_test_client()
        response = client.get("/api/platform/requests/unassigned", headers=AUTH)

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["count"] == 1
    assert payload["rows"][0]["id"] == "r-1"
