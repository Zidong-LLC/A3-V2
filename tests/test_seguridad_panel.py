"""Endurecimiento del panel (auditoría 2026-10-19): sesión, ingreso, salud y webhooks."""
from unittest.mock import patch

import pytest
from werkzeug.security import generate_password_hash

from app import access
from app.main import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    return app.test_client()


def test_clave_con_tilde_no_rompe_el_ingreso():
    # compare_digest con str no acepta tildes: antes era un error 500 en el login.
    assert access.autenticar("admin", "contraseña", "admin", "contraseña")["role"] == "administrador"
    with patch("app.services.users_db.get_user_by_username", return_value=None):
        assert access.autenticar("admin", "contraseñá", "admin", "contraseña") is None


def test_usuario_inexistente_pasa_por_el_hash_igual_que_una_clave_mala():
    with patch("app.services.users_db.get_user_by_username", return_value=None), \
         patch("app.access.check_password_hash", return_value=True) as verificar:
        assert access.autenticar("nadie", "x", "admin", "y") is None
    verificar.assert_called_once()


def test_login_se_bloquea_tras_cinco_claves_equivocadas(client, monkeypatch):
    fila = {"id": "u1", "username": "ana", "full_name": "Ana", "role": "recepcion",
            "is_active": True, "password_hash": generate_password_hash("clave-segura")}
    monkeypatch.setattr("app.services.users_db.get_user_by_username", lambda u: fila if u == "ana" else None)
    monkeypatch.setattr("app.services.users_db.touch_login", lambda _id: None)
    for _ in range(5):
        assert client.post("/login", data={"username": "ana", "password": "mala"}).status_code == 200
    bloqueado = client.post("/login", data={"username": "ana", "password": "clave-segura"})
    assert bloqueado.status_code == 429
    assert "Demasiados intentos" in bloqueado.get_data(as_text=True)
    # Otro usuario desde la misma IP no queda bloqueado.
    assert client.post("/login", data={"username": "otro", "password": "x"}).status_code == 200


def test_ingreso_correcto_limpia_los_intentos_fallidos(client, monkeypatch):
    fila = {"id": "u1", "username": "ana", "role": "recepcion", "is_active": True,
            "password_hash": generate_password_hash("clave-segura")}
    monkeypatch.setattr("app.services.users_db.get_user_by_username", lambda u: fila)
    monkeypatch.setattr("app.services.users_db.touch_login", lambda _id: None)
    for _ in range(4):
        client.post("/login", data={"username": "ana", "password": "mala"})
    assert client.post("/login", data={"username": "ana", "password": "clave-segura"}).status_code == 302
    assert not access._fallidos


def test_cookie_de_sesion_no_viaja_desde_otros_sitios(client, monkeypatch):
    monkeypatch.setattr("app.services.users_db.touch_login", lambda _id: None)
    r = client.post("/login", data={"username": "admin", "password": "test-secret"})
    cookie = r.headers.get("Set-Cookie", "")
    assert "SameSite=Lax" in cookie and "HttpOnly" in cookie


def test_salud_detallada_exige_sesion_o_token(client):
    with patch("app.main.check_all", return_value=({"status": "ok"}, 200)) as completo:
        assert client.get("/health/detalle").status_code == 401
        completo.assert_not_called()
        con_token = client.get("/health/detalle", headers={"X-Platform-Token": "test-platform-token"})
        assert con_token.status_code == 200
        with client.session_transaction() as s:
            s["dashboard_authenticated"] = True
        assert client.get("/health/detalle").status_code == 200
    assert client.get("/health").status_code in (200, 503)  # el liviano sigue abierto para Render


def test_webhook_de_telegram_sin_secreto_configurado_no_deja_pasar(client, monkeypatch):
    monkeypatch.setattr("app.main.TELEGRAM_WEBHOOK_SECRET", "")
    r = client.post("/webhooks/telegram", json={}, headers={"X-Telegram-Bot-Api-Secret-Token": ""})
    assert r.status_code == 403
    assert client.post("/setup-webhook", headers={"X-Telegram-Bot-Api-Secret-Token": ""}).status_code == 403
