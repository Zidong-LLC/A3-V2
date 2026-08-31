"""Portal Web (solo clientes): login por veterinaria + NIT y protección de sesión.

El NIT es la llave; el nombre solo valida contra las filas de ese NIT. El match
de nombre usa la función REAL (client_name_matches, pura); solo se mockea el
acceso a datos (find_clients_by_tax_id).
"""
from unittest.mock import patch

import pytest

CLIENT_A = "11111111-1111-1111-1111-111111111111"
CLIENT_B = "22222222-2222-2222-2222-222222222222"

SEDE_A = {"id": CLIENT_A, "clinic_name": "Danimal Planet Suba", "tax_id": "900123456", "address": "Cl 1 # 2-3"}
SEDE_B = {"id": CLIENT_B, "clinic_name": "Danimal Planet Centro", "tax_id": "900123456", "address": "Cr 9 # 8-7"}


@pytest.fixture(autouse=True)
def _clean_rate_limit():
    from app.portal import auth

    auth._login_attempts.clear()
    yield
    auth._login_attempts.clear()


def _get_test_client():
    from app.main import app

    app.config["TESTING"] = True
    return app.test_client()


def _login_as_client(client, client_id=CLIENT_A):
    with client.session_transaction() as sess:
        sess["portal_user_id"] = "nit:900123456"
        sess["portal_client_id"] = client_id


def _post_login(client, name="Danimal Planet", nit="900123456", **extra):
    data = {"clinic_name": name, "nit": nit, **extra}
    return client.post("/portal/login", data=data)


def test_portal_pages_redirect_to_login_without_session():
    client = _get_test_client()
    for path in ("/portal/mis/solicitudes", "/portal/mis/resultados", "/portal/mis/perfil"):
        response = client.get(path)
        assert response.status_code == 302
        assert "/portal/login" in response.headers["Location"]


def test_portal_session_without_client_id_is_forbidden():
    client = _get_test_client()
    with client.session_transaction() as sess:
        sess["portal_user_id"] = "nit:900123456"
        sess["portal_client_id"] = None
    assert client.get("/portal/mis/resultados").status_code == 403


def test_login_single_sede_starts_session():
    with patch("app.portal.auth.find_clients_by_tax_id", return_value=[SEDE_A]):
        client = _get_test_client()
        response = _post_login(client)
        assert response.status_code == 302
        assert response.headers["Location"].endswith("/portal/mis/solicitudes")
        with client.session_transaction() as sess:
            assert sess["portal_client_id"] == CLIENT_A
            assert sess["portal_user_id"] == "nit:900123456"


def test_login_wrong_name_for_valid_nit_is_rejected():
    with patch("app.portal.auth.find_clients_by_tax_id", return_value=[SEDE_A]):
        client = _get_test_client()
        response = _post_login(client, name="Otra Veterinaria")
        assert response.status_code == 200
        assert "no coinciden" in response.get_data(as_text=True)
        with client.session_transaction() as sess:
            assert "portal_client_id" not in sess


def test_login_unknown_nit_shows_same_generic_error():
    with patch("app.portal.auth.find_clients_by_tax_id", return_value=[]):
        client = _get_test_client()
        response = _post_login(client, nit="999999999")
        assert response.status_code == 200
        assert "no coinciden" in response.get_data(as_text=True)


def test_login_multi_sede_lists_and_second_post_picks_one():
    with patch("app.portal.auth.find_clients_by_tax_id", return_value=[SEDE_A, SEDE_B]):
        client = _get_test_client()
        response = _post_login(client)
        body = response.get_data(as_text=True)
        assert response.status_code == 200
        assert "Danimal Planet Suba" in body and "Danimal Planet Centro" in body
        with client.session_transaction() as sess:
            assert "portal_client_id" not in sess

        response = _post_login(client, client_id=CLIENT_B)
        assert response.status_code == 302
        with client.session_transaction() as sess:
            assert sess["portal_client_id"] == CLIENT_B


def test_login_rejects_client_id_foreign_to_the_nit():
    """El client_id del form se re-valida contra las sedes del NIT."""
    with patch("app.portal.auth.find_clients_by_tax_id", return_value=[SEDE_A, SEDE_B]):
        client = _get_test_client()
        response = _post_login(client, client_id="33333333-3333-3333-3333-333333333333")
        assert response.status_code == 200
        with client.session_transaction() as sess:
            assert "portal_client_id" not in sess


def test_login_rate_limited_after_max_attempts():
    with patch("app.portal.auth.find_clients_by_tax_id", return_value=[]):
        client = _get_test_client()
        for _ in range(10):
            _post_login(client, nit="999999999")
        response = _post_login(client, nit="999999999")
        assert "Demasiados intentos" in response.get_data(as_text=True)


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


def test_si_la_base_falla_el_login_avisa_en_vez_de_reventar():
    """El QA de TestSprite corto la conexion a Supabase en pleno login y el cliente
    vio un traceback (httpx.RemoteProtocolError). Ahora ve un aviso amable (ERR-174)."""
    from unittest.mock import patch

    client = _get_test_client()
    with patch("app.portal.auth._find_sedes", side_effect=RuntimeError("Server disconnected")):
        respuesta = client.post("/portal/login", data={"clinic_name": "Vet Prueba", "nit": "900123456"})
    assert respuesta.status_code == 200
    cuerpo = respuesta.get_data(as_text=True)
    assert "No pudimos verificar los datos" in cuerpo
    assert "Traceback" not in cuerpo
