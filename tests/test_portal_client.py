"""Portal Web (rol cliente): aislamiento por client_id y flujo de solicitudes."""
from unittest.mock import patch

CLIENT_A = "11111111-1111-1111-1111-111111111111"
CLIENT_B = "22222222-2222-2222-2222-222222222222"
RESULT_ID = "33333333-3333-3333-3333-333333333333"


def _get_test_client():
    from app.main import app

    app.config["TESTING"] = True
    return app.test_client()


def _login_client(client, client_id=CLIENT_A):
    with client.session_transaction() as sess:
        sess["portal_user_id"] = "user-1"
        sess["portal_role"] = "client"
        sess["portal_client_id"] = client_id
        sess["portal_email"] = "vet@x.test"


def _result(client_id, published=True):
    return {
        "id": RESULT_ID, "client_id": client_id, "published": published,
        "pdf_path": f"{client_id}/A3-1/x.pdf", "patient_name": "Rocky",
        "order_number": "A3-00001", "exam_name": "Hemograma",
        "created_at": "2026-07-01T10:00:00", "published_at": "2026-07-01T12:00:00",
        "clients": {"clinic_name": "Vet A"},
    }


def test_client_cannot_see_other_clients_result():
    client = _get_test_client()
    _login_client(client, CLIENT_A)
    with patch("app.portal.client_results.portal_db.get_lab_result",
               return_value=_result(CLIENT_B)):
        assert client.get(f"/portal/mis/resultados/{RESULT_ID}").status_code == 404
        assert client.get(f"/portal/mis/resultados/{RESULT_ID}/pdf").status_code == 404


def test_client_cannot_see_unpublished_result():
    client = _get_test_client()
    _login_client(client, CLIENT_A)
    with patch("app.portal.client_results.portal_db.get_lab_result",
               return_value=_result(CLIENT_A, published=False)):
        assert client.get(f"/portal/mis/resultados/{RESULT_ID}").status_code == 404


def test_client_sees_own_published_result():
    client = _get_test_client()
    _login_client(client, CLIENT_A)
    with patch("app.portal.client_results.portal_db.get_lab_result",
               return_value=_result(CLIENT_A)), \
         patch("app.portal.client_results.storage.result_signed_url",
               return_value="https://signed.example/x.pdf"), \
         patch("app.services.portal_db.count_unread_notifications", return_value=0):
        response = client.get(f"/portal/mis/resultados/{RESULT_ID}")
    assert response.status_code == 200
    assert "Rocky" in response.get_data(as_text=True)


def test_client_results_list_forces_session_client_and_published():
    client = _get_test_client()
    _login_client(client, CLIENT_A)
    with patch("app.portal.client_results.portal_db.list_lab_results",
               return_value=[]) as mock_list, \
         patch("app.services.portal_db.count_unread_notifications", return_value=0):
        response = client.get("/portal/mis/resultados?patient=Rocky")
    assert response.status_code == 200
    _, kwargs = mock_list.call_args
    assert kwargs["client_id"] == CLIENT_A
    assert kwargs["only_published"] is True


def test_new_request_uses_session_client_id():
    client = _get_test_client()
    _login_client(client, CLIENT_A)
    created = {"request_id": "r-1", "order_number": "A3-00042", "event_payload": {}}
    with patch("app.portal.client_requests.db.get_client_by_id",
               return_value={"id": CLIENT_A, "clinic_name": "Vet A",
                             "address": "Calle 1", "phone": "300"}), \
         patch("app.portal.client_requests.db.create_request",
               return_value=created) as mock_create, \
         patch("app.portal.client_requests.portal_db.insert_notification") as mock_notif, \
         patch("app.services.portal_db.count_unread_notifications", return_value=0):
        response = client.post(
            "/portal/mis/solicitudes/nueva",
            data={"patient_name": "Rocky", "exam_type": "Hemograma",
                  "payment_method": "contraentrega"},
        )
    assert response.status_code == 302
    _, kwargs = mock_create.call_args
    assert kwargs["session"]["client_id"] == CLIENT_A
    assert kwargs["session"]["channel"] == "portal"
    assert kwargs["ai_response"]["intent"] == "route_scheduling"
    assert mock_notif.call_args[0][0] == CLIENT_A


def test_mark_notification_read_scoped_to_session_client():
    client = _get_test_client()
    _login_client(client, CLIENT_A)
    notif_id = "44444444-4444-4444-4444-444444444444"
    with patch("app.portal.client_results.portal_db.mark_notification_read") as mock_read:
        response = client.post(f"/portal/mis/notificaciones/{notif_id}/leer")
    assert response.status_code == 302
    assert mock_read.call_args[0] == (notif_id, CLIENT_A)
