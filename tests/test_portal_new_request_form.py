"""El pedido del portal se ve y captura igual que la carga manual del laboratorio.

El cliente veía un `<select multiple>` con 275 análisis y solo podía elegir UN perfil,
mientras el personal tenía buscador, casillas y varios perfiles. Estos tests fijan lo
que se igualó (2026-09-08): varios perfiles y los campos de paciente que faltaban.
"""
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _pedido_sin_red(monkeypatch):
    """Las órdenes abren su pedido y su borrador (ERR-194): sin esto, create_pedido iba a la
    base de verdad (fallaba en silencio) y con ALEGRA_ENABLED del .env se intentaba facturar."""
    monkeypatch.setattr("app.pedido_directo.db.create_pedido",
                        lambda *a, **k: {"id": "ped-1", "pedido_number": "P-2026-001"})
    monkeypatch.setattr("app.pedido_directo.db.close_pedido", lambda *a, **k: None)
    monkeypatch.setattr("app.pedido_directo.config.ALEGRA_ENABLED", False)

CLIENT_ID = "11111111-1111-1111-1111-111111111111"
CLIENTE = {"id": CLIENT_ID, "clinic_name": "Vet A", "address": "Calle 1", "phone": "300"}
PERFIL_1 = {"code": "952", "name": "Perfil Prequirurgico", "price": 95000, "description": ""}
PERFIL_2 = {"code": "653", "name": "Perfil Renal", "price": 45000, "description": ""}
TEST_1903 = {"code": "1903", "name": "Creatinina", "price": 18000}


def _get_test_client():
    from app.main import app

    app.config["TESTING"] = True
    return app.test_client()


def _login(client):
    with client.session_transaction() as sess:
        sess["portal_user_id"] = "nit:900"
        sess["portal_client_id"] = CLIENT_ID
        sess["csrf_token"] = "tok"


def _form(**cambios):
    datos = {
        "csrf_token": "tok",
        "patient_name": "Rocky",
        "species": "Canino",
        "breed": "Labrador",
        "sex": "Macho",
        "patient_age": "5 anios",
        "owner_name": "Ana",
        "sample_taken_date": "2026-09-07",
        "profile_codes": ["952", "653"],
        "test_codes": ["1903"],
        "payment_method": "credito",
        "observations": "ayuno",
    }
    datos.update(cambios)
    return datos


def _patches(perfiles=None):
    perfiles = perfiles or {"952": dict(PERFIL_1), "653": dict(PERFIL_2)}
    return (
        patch("app.portal.client_requests.db.get_client_by_id", return_value=dict(CLIENTE)),
        patch("app.portal.client_requests.db.list_catalog_profiles",
              return_value=[dict(PERFIL_1), dict(PERFIL_2)]),
        patch("app.portal.client_requests.db.list_catalog_tests", return_value=[dict(TEST_1903)]),
        patch("app.orders.db.find_catalog_profile", side_effect=lambda c: perfiles.get(c)),
        patch("app.orders.db.get_tests_by_codes_or_names", return_value=[dict(TEST_1903)]),
        patch("app.portal.client_requests.portal_db.insert_notification"),
        patch("app.portal.client_requests.db.create_request",
              return_value={"order_number": "A3-00042", "request_id": "req-1"}),
    )


def test_el_cliente_puede_pedir_varios_perfiles():
    """Antes el portal mandaba `profile_code` (uno solo): el segundo perfil se perdia."""
    client = _get_test_client()
    _login(client)
    p = _patches()
    with p[0], p[1], p[2], p[3], p[4], p[5], p[6] as create:
        resp = client.post("/portal/mis/solicitudes/nueva", data=_form())

    assert resp.status_code == 302
    fields = create.call_args.kwargs["ai_response"]["captured_fields"]
    assert fields["_selected_profile_code"] == "952"
    assert fields["_extra_profiles"] == [{"code": "653", "name": "Perfil Renal", "price": 45000}]
    assert fields["selected_tests"] == ["1903"]


def test_los_campos_del_paciente_llegan_completos():
    """Raza, sexo y fecha de toma: el cliente los sabe mejor que nadie y antes no los pedia."""
    client = _get_test_client()
    _login(client)
    p = _patches()
    with p[0], p[1], p[2], p[3], p[4], p[5], p[6] as create:
        client.post("/portal/mis/solicitudes/nueva", data=_form())

    fields = create.call_args.kwargs["ai_response"]["captured_fields"]
    assert fields["breed"] == "Labrador"
    assert fields["sex"] == "Macho"
    assert fields["sample_taken_date"] == "2026-09-07"


def test_el_formulario_ofrece_el_catalogo_con_casillas_buscables():
    client = _get_test_client()
    _login(client)
    p = _patches()
    with p[0], p[1], p[2]:
        html = client.get("/portal/mis/solicitudes/nueva").get_data(as_text=True)

    assert 'name="profile_codes"' in html, "los perfiles deben ser casillas, no un desplegable"
    assert "data-picker-search" in html, "el catalogo necesita buscador"
    assert 'name="breed"' in html and 'name="sample_taken_date"' in html


def test_sin_analisis_no_se_registra_nada():
    """Una orden sin perfil ni analisis facturaria $0."""
    client = _get_test_client()
    _login(client)
    p = _patches(perfiles={})
    with p[0], p[1], p[2], p[3], \
         patch("app.orders.db.get_tests_by_codes_or_names", return_value=[]), \
         p[5], p[6] as create:
        resp = client.post("/portal/mis/solicitudes/nueva",
                           data=_form(profile_codes=[], test_codes=[]))

    assert resp.status_code == 200
    assert not create.called
