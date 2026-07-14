"""Portal Web (solo clientes): login por GoTrue y protección de sesión."""
from unittest.mock import patch

from app.services.portal_auth import PortalAuthError

CLIENT_A = "11111111-1111-1111-1111-111111111111"


def _get_test_client():
    from app.main import app

    app.config["TESTING"] = True
    return app.test_client()


def _login_as_client(client, client_id=CLIENT_A):
    with client.session_transaction() as sess:
        sess["portal_user_id"] = "user-1"
        sess["portal_client_id"] = client_id
        sess["portal_email"] = "vet@x.test"


def test_portal_pages_redirect_to_login_without_session():
    client = _get_test_client()
    for path in ("/portal/mis/solicitudes", "/portal/mis/resultados", "/portal/mis/perfil"):
        response = client.get(path)
        assert response.status_code == 302
        assert "/portal/login" in response.headers["Location"]


def test_portal_session_without_client_id_is_forbidden():
    client = _get_test_client()
    with client.session_transaction() as sess:
        sess["portal_user_id"] = "user-1"
        sess["portal_client_id"] = None
    assert client.get("/portal/mis/resultados").status_code == 403


def test_login_client_stores_session_client_id():
    identity = {"user_id": "u-2", "email": "vet@x.test", "client_id": CLIENT_A}
    with patch("app.portal.auth.portal_auth.sign_in", return_value=identity), \
         patch("app.portal.auth.get_client_by_id", return_value={"id": CLIENT_A}):
        client = _get_test_client()
        response = client.post(
            "/portal/login", data={"email": "vet@x.test", "password": "x"}
        )
        assert response.status_code == 302
        assert response.headers["Location"].endswith("/portal/mis/solicitudes")
        with client.session_transaction() as sess:
            assert sess["portal_client_id"] == CLIENT_A


def test_login_rejected_shows_error():
    with patch(
        "app.portal.auth.portal_auth.sign_in",
        side_effect=PortalAuthError("La cuenta no tiene acceso al portal de clientes"),
    ):
        client = _get_test_client()
        response = client.post(
            "/portal/login", data={"email": "staff@a3.test", "password": "x"}
        )
    assert response.status_code == 200
    assert "La cuenta no tiene acceso al portal de clientes" in response.get_data(as_text=True)


def test_logout_clears_portal_session():
    client = _get_test_client()
    _login_as_client(client)
    client.get("/portal/logout")
    with client.session_transaction() as sess:
        assert "portal_user_id" not in sess
        assert "portal_client_id" not in sess


def test_portal_session_does_not_open_dashboard():
    """La sesión del portal no debe dar acceso al dashboard del personal."""
    client = _get_test_client()
    _login_as_client(client)
    response = client.get("/dashboard")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]
