"""/health debe reflejar el estado real de las dependencias.

Regresión: antes devolvía {"status": "ok"} fijo, así que un monitor externo
no se enteraba nunca de que Supabase estaba caído.

Desde ERR-182 el chequeo COMPLETO vive en /health/detalle: /health es el liviano
que mira Render (solo Supabase) para no reiniciar el servicio por un pico de Alegra.
"""
from unittest.mock import patch


def _get_test_client():
    from app.main import app

    app.config["TESTING"] = True
    cliente = app.test_client()
    with cliente.session_transaction() as sesion:  # el detalle exige sesión o token
        sesion["dashboard_authenticated"] = True
    return cliente


def test_health_ok_when_supabase_responds():
    with patch("app.health.db.ping", return_value=True), \
         patch("app.health.ALEGRA_ENABLED", False):
        response = _get_test_client().get("/health/detalle")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "ok"
    assert payload["checks"]["supabase"]["status"] == "ok"
    assert payload["checks"]["alegra"]["status"] == "disabled"


def test_health_returns_503_when_supabase_is_down():
    with patch("app.health.db.ping", side_effect=RuntimeError("connection refused")), \
         patch("app.health.ALEGRA_ENABLED", False):
        response = _get_test_client().get("/health/detalle")

    assert response.status_code == 503
    payload = response.get_json()
    assert payload["status"] == "error"
    assert payload["checks"]["supabase"]["status"] == "error"
    assert "connection refused" in payload["checks"]["supabase"]["error"]


def test_health_degrades_but_stays_200_when_only_alegra_fails():
    """Alegra caído degrada la facturación, no la recogida de muestras."""
    with patch("app.health.db.ping", return_value=True), \
         patch("app.health.ALEGRA_ENABLED", True), \
         patch("app.health.alegra.ping", side_effect=RuntimeError("timeout")):
        response = _get_test_client().get("/health/detalle")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "degraded"
    assert payload["checks"]["alegra"]["status"] == "error"
