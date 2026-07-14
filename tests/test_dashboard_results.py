"""Módulo Resultados del dashboard: subida de PDF, validaciones y publicación."""
import io
from unittest.mock import patch

CLIENT_A = "11111111-1111-1111-1111-111111111111"
RESULT_ID = "33333333-3333-3333-3333-333333333333"


def _get_test_client():
    from app.main import app

    app.config["TESTING"] = True
    return app.test_client()


def _login_dashboard(client):
    with client.session_transaction() as sess:
        sess["dashboard_authenticated"] = True
        sess["dashboard_username"] = "admin"


def _upload(client, pdf_bytes, **extra):
    data = {"order_number": "A3-00042", "pdf": (io.BytesIO(pdf_bytes), "informe.pdf")}
    data.update(extra)
    return client.post(
        "/resultados/subir", data=data, content_type="multipart/form-data",
        follow_redirects=True,
    )


def test_results_page_requires_dashboard_login():
    client = _get_test_client()
    response = client.get("/resultados")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_portal_client_session_cannot_open_results_page():
    """Una veterinaria logueada al portal no accede al módulo del personal."""
    client = _get_test_client()
    with client.session_transaction() as sess:
        sess["portal_user_id"] = "user-1"
        sess["portal_client_id"] = CLIENT_A
    response = client.get("/resultados")
    assert response.status_code == 302


def test_upload_pdf_creates_result():
    client = _get_test_client()
    _login_dashboard(client)
    request_row = {"id": "r-1", "client_id": CLIENT_A, "patient_name": "Rocky",
                   "owner_name": "Ana", "exam_type": "Hemograma"}
    with patch("app.dashboard_results.portal_db.get_request_by_order_number",
               return_value=request_row), \
         patch("app.dashboard_results.storage.upload_result_pdf",
               return_value=f"{CLIENT_A}/A3-00042/x.pdf") as mock_upload, \
         patch("app.dashboard_results.portal_db.insert_lab_result",
               return_value={"id": RESULT_ID, "client_id": CLIENT_A}) as mock_insert, \
         patch("app.dashboard_results.portal_db.list_lab_results", return_value=[]):
        response = _upload(client, b"%PDF-1.4 contenido")
    assert response.status_code == 200
    assert mock_upload.call_args[0][0] == CLIENT_A
    inserted = mock_insert.call_args[0][0]
    assert inserted["client_id"] == CLIENT_A
    assert inserted["patient_name"] == "Rocky"
    assert inserted["uploaded_by"] == "admin"


def test_upload_rejects_non_pdf_content():
    client = _get_test_client()
    _login_dashboard(client)
    with patch("app.dashboard_results.portal_db.get_request_by_order_number",
               return_value={"id": "r-1", "client_id": CLIENT_A}), \
         patch("app.dashboard_results.storage.upload_result_pdf") as mock_upload, \
         patch("app.dashboard_results.portal_db.list_lab_results", return_value=[]):
        response = _upload(client, b"no es un pdf")
    assert response.status_code == 200
    assert "Archivo inválido" in response.get_data(as_text=True)
    mock_upload.assert_not_called()


def test_upload_rejects_unknown_client():
    client = _get_test_client()
    _login_dashboard(client)
    with patch("app.dashboard_results.portal_db.get_request_by_order_number",
               return_value=None), \
         patch("app.dashboard_results.find_clients_by_tax_id", return_value=[]), \
         patch("app.dashboard_results.storage.upload_result_pdf") as mock_upload, \
         patch("app.dashboard_results.portal_db.list_lab_results", return_value=[]):
        response = _upload(client, b"%PDF-1.4 x")
    assert response.status_code == 200
    assert "No se encontró el cliente" in response.get_data(as_text=True)
    mock_upload.assert_not_called()


def test_publish_notifies_and_sends_telegram():
    client = _get_test_client()
    _login_dashboard(client)
    result_row = {"id": RESULT_ID, "client_id": CLIENT_A, "published": False,
                  "patient_name": "Rocky", "order_number": "A3-00042",
                  "exam_name": "Hemograma", "pdf_path": "p.pdf"}
    with patch("app.dashboard_results.portal_db.get_lab_result", return_value=result_row), \
         patch("app.dashboard_results.portal_db.publish_lab_result",
               return_value={**result_row, "published": True}), \
         patch("app.dashboard_results.portal_db.insert_notification") as mock_notif, \
         patch("app.dashboard_results.portal_db.telegram_chat_for_client",
               return_value="12345"), \
         patch("app.dashboard_results.telegram.send_message") as mock_tg:
        response = client.post(f"/resultados/{RESULT_ID}/publicar")
    assert response.status_code == 302
    assert mock_notif.call_args[0][0] == CLIENT_A
    assert mock_notif.call_args[0][1] == "result_published"
    assert mock_tg.call_args[0][0] == "12345"


def test_publish_survives_telegram_failure():
    client = _get_test_client()
    _login_dashboard(client)
    result_row = {"id": RESULT_ID, "client_id": CLIENT_A, "published": False,
                  "patient_name": "Rocky", "order_number": "A3-00042",
                  "exam_name": "Hemograma", "pdf_path": "p.pdf"}
    with patch("app.dashboard_results.portal_db.get_lab_result", return_value=result_row), \
         patch("app.dashboard_results.portal_db.publish_lab_result",
               return_value={**result_row, "published": True}), \
         patch("app.dashboard_results.portal_db.insert_notification"), \
         patch("app.dashboard_results.portal_db.telegram_chat_for_client",
               side_effect=RuntimeError("red caída")):
        response = client.post(f"/resultados/{RESULT_ID}/publicar")
    assert response.status_code == 302


def test_pdf_redirects_to_signed_url():
    client = _get_test_client()
    _login_dashboard(client)
    with patch("app.dashboard_results.portal_db.get_lab_result",
               return_value={"id": RESULT_ID, "pdf_path": "p.pdf"}), \
         patch("app.dashboard_results.storage.result_signed_url",
               return_value="https://signed.example/p.pdf"):
        response = client.get(f"/resultados/{RESULT_ID}/pdf")
    assert response.status_code == 302
    assert response.headers["Location"] == "https://signed.example/p.pdf"
