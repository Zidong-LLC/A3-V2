"""Sección "Nueva orden" del dashboard — carga manual desde el laboratorio.

A3 lo preguntó en la llamada del 21/08: *"cuando un cliente no hace su pedido a través del
bot, si lo hace por teléfono o va presencialmente al laboratorio, ¿cómo lo hacemos?"*.
Hasta ahora una orden solo nacía por el chat o por el portal (que exige la sesión del propio
cliente), así que el personal no tenía por dónde cargarla.

La regla de dinero es la misma que en el portal: el código y el precio salen del catálogo,
nunca del formulario (ERR-097).
"""
from unittest.mock import patch

CLIENTE = {
    "id": "cli-1", "clinic_name": "Emergencias Veterinarias", "tax_id": "900123456",
    "address": "Calle 27 sur 34-47", "phone": "3001234567",
}
PERFIL = {"code": "952", "name": "Perfil Toxicológico Órgano Fosforados", "price": 90000,
          "description": ""}
TEST_1903 = {"code": "1903", "name": "Citología PAF", "price": 52000}


def _get_test_client():
    from app.main import app

    app.config["TESTING"] = True
    return app.test_client()


def _login(client, monkeypatch):
    monkeypatch.setattr("app.dashboard.DASHBOARD_ADMIN_USER", "admin")
    monkeypatch.setattr("app.dashboard.DASHBOARD_ADMIN_PASSWORD", "secret")
    client.post("/login", data={"username": "admin", "password": "secret"})


def _form(**overrides):
    payload = {
        "client_id": "cli-1",
        "requesting_doctor": "Cristian Vargas",
        "patient_name": "Lola",
        "species": "Canino",
        "breed": "Border Collie",
        "sex": "Hembra",
        "patient_age": "6 años",
        "owner_name": "Marcela Osorio",
        "sample_taken_date": "hoy",
        "profile_code": "952",
        "payment_method": "contraentrega",
        "observations": "",
    }
    payload.update(overrides)
    return payload


def _patches(created={"request_id": "req-1", "order_number": "A3-2026-042"}):
    return (
        patch("app.dashboard.db.get_client_by_id", return_value=dict(CLIENTE)),
        patch("app.dashboard.db.list_clients_with_assignment", return_value=[dict(CLIENTE)]),
        patch("app.dashboard.db.list_catalog_profiles", return_value=[dict(PERFIL)]),
        patch("app.dashboard.db.list_catalog_tests", return_value=[dict(TEST_1903)]),
        patch("app.orders.db.find_catalog_profile", return_value=dict(PERFIL)),
        patch("app.orders.db.get_tests_by_codes_or_names", return_value=[]),
        patch("app.dashboard.db.create_request", return_value=created),
    )


def test_la_seccion_esta_protegida_por_login():
    client = _get_test_client()
    resp = client.get("/solicitudes/nueva")
    assert resp.status_code in (301, 302)
    assert "/login" in resp.headers.get("Location", "")


def test_registra_la_orden_con_el_precio_del_catalogo(monkeypatch):
    client = _get_test_client()
    _login(client, monkeypatch)
    p = _patches()
    with p[0], p[1], p[2], p[3], p[4], p[5], p[6] as create:
        resp = client.post("/solicitudes/nueva", data=_form())

    assert resp.status_code in (301, 302)
    assert create.called, "no se registró la orden"
    fields = create.call_args.kwargs["ai_response"]["captured_fields"]
    # El precio y el código vienen de la base, no del formulario (ERR-097).
    assert fields["_selected_profile_code"] == "952"
    assert fields["_selected_profile_price"] == 90000
    assert fields["exam_type"] == PERFIL["name"]
    # Y los datos del paciente llegan completos, incluida la fecha de toma.
    assert fields["patient_name"] == "Lola"
    assert fields["sample_taken_date"] == "hoy"
    assert create.call_args.kwargs["session"]["client_id"] == "cli-1"


def test_sin_veterinaria_no_registra_nada(monkeypatch):
    client = _get_test_client()
    _login(client, monkeypatch)
    with patch("app.dashboard.db.get_client_by_id", return_value=None), \
         patch("app.dashboard.db.list_clients_with_assignment", return_value=[]), \
         patch("app.dashboard.db.list_catalog_profiles", return_value=[]), \
         patch("app.dashboard.db.list_catalog_tests", return_value=[]), \
         patch("app.dashboard.db.create_request") as create:
        resp = client.post("/solicitudes/nueva", data=_form(client_id=""))

    assert resp.status_code == 200, "debe volver al formulario, no redirigir"
    assert not create.called
    assert "Elige la veterinaria" in resp.get_data(as_text=True)


def test_sin_analisis_del_catalogo_no_registra_nada(monkeypatch):
    """Una orden sin perfil ni análisis facturaría $0: se rechaza antes de crearla."""
    client = _get_test_client()
    _login(client, monkeypatch)
    with patch("app.dashboard.db.get_client_by_id", return_value=dict(CLIENTE)), \
         patch("app.dashboard.db.list_clients_with_assignment", return_value=[dict(CLIENTE)]), \
         patch("app.dashboard.db.list_catalog_profiles", return_value=[dict(PERFIL)]), \
         patch("app.dashboard.db.list_catalog_tests", return_value=[dict(TEST_1903)]), \
         patch("app.orders.db.find_catalog_profile", return_value=None), \
         patch("app.orders.db.get_tests_by_codes_or_names", return_value=[]), \
         patch("app.dashboard.db.create_request") as create:
        resp = client.post("/solicitudes/nueva", data=_form(profile_code=""))

    assert resp.status_code == 200
    assert not create.called
    assert "al menos un perfil o análisis" in resp.get_data(as_text=True)


def test_la_direccion_vacia_toma_la_del_cliente(monkeypatch):
    client = _get_test_client()
    _login(client, monkeypatch)
    p = _patches()
    with p[0], p[1], p[2], p[3], p[4], p[5], p[6] as create:
        client.post("/solicitudes/nueva", data=_form(pickup_address=""))

    fields = create.call_args.kwargs["ai_response"]["captured_fields"]
    assert fields["pickup_address"] == CLIENTE["address"]
    assert fields["clinic_name"] == CLIENTE["clinic_name"]


def test_el_formulario_ofrece_el_catalogo_y_los_clientes(monkeypatch):
    client = _get_test_client()
    _login(client, monkeypatch)
    p = _patches()
    with p[0], p[1], p[2], p[3]:
        html = client.get("/solicitudes/nueva").get_data(as_text=True)

    assert "Emergencias Veterinarias" in html
    assert "952" in html and "1903" in html
    assert "csrf_token" in html
