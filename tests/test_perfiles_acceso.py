"""Perfiles del personal (Perfiles Plataforma.docx): matriz, control en servidor y usuarios."""
import time

import pytest
from werkzeug.security import check_password_hash, generate_password_hash

from app import access
from app import permissions as P
from app.main import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    return app.test_client()


def _sesion(client, perfil=None, user_id=None, checked=None):
    with client.session_transaction() as s:
        s["dashboard_authenticated"] = True
        s["dashboard_username"] = "prueba"
        if perfil:
            s["dashboard_role"] = perfil
        if user_id:
            s["dashboard_user_id"] = user_id
            s["dashboard_role_checked"] = checked if checked is not None else time.time()


def test_toda_ruta_del_personal_tiene_modulo_asignado():
    sin_mapa = [r.endpoint for r in app.url_map.iter_rules()
                if r.endpoint.split(".")[0] in access.BLUEPRINTS
                and r.endpoint not in P.LIBRES and P.modulos_de(r.endpoint) is None]
    assert sin_mapa == [], f"Rutas sin módulo en app/permissions.py: {sin_mapa}"


@pytest.mark.parametrize("perfil,modulo,esperado", [
    ("recepcion", "motorizados", P.GESTION), ("recepcion", "resultados", P.CONSULTA),
    ("recepcion", "facturacion", P.NINGUNO), ("digitacion", "clientes", P.CONSULTA),
    ("digitacion", "cargas", P.GESTION), ("auxiliar_administrativa", "facturacion", P.GESTION),
    ("auxiliar_administrativa", "pedidos", P.CONSULTA), ("auxiliar_administrativa", "operacion", P.NINGUNO),
    ("procesamiento", "clientes", P.NINGUNO), ("procesamiento", "solicitudes", P.CONSULTA),
    ("procesamiento", "muestras", P.GESTION), ("administrador", "usuarios", P.GESTION),
    ("recepcion", "precios", P.NINGUNO), ("perfil-inventado", "dashboard", P.NINGUNO),
])
def test_matriz_del_documento(perfil, modulo, esperado):
    assert P.nivel(perfil, modulo) == esperado


def test_sin_permiso_en_api_devuelve_403_json(client):
    _sesion(client, "recepcion")
    r = client.post("/api/dashboard/catalog-item", json={"kind": "analisis", "code": "1", "price": 1})
    assert r.status_code == 403
    assert "permiso" in r.get_json()["error"]


def test_consulta_no_permite_modificar(client):
    _sesion(client, "digitacion")  # Clientes: solo consultar
    r = client.post("/api/dashboard/client-delete", json={})
    assert r.status_code == 403


def test_gestion_pasa_el_control_y_llega_a_la_vista(client):
    _sesion(client, "recepcion")  # Clientes: gestionar
    r = client.post("/api/dashboard/client-delete", json={})
    assert r.status_code == 400  # la vista valida el pedido: el control de acceso dejó pasar


def test_pagina_sin_permiso_muestra_aviso_y_menu_del_perfil(client):
    _sesion(client, "auxiliar_administrativa")
    r = client.get("/agenda")
    html = r.get_data(as_text=True)
    assert r.status_code == 403
    assert "Sin permiso" in html
    menu = html.split("menu-list", 1)[1].split("</nav>", 1)[0]
    assert "Facturacion" in menu and "Clientes" in menu
    assert "Agenda" not in menu and "Usuarios" not in menu


def test_sesion_anterior_a_los_perfiles_es_administrador(client, monkeypatch):
    monkeypatch.setattr("app.services.users_db.list_users", lambda: [])
    _sesion(client)  # solo dashboard_authenticated, como las sesiones de antes
    r = client.get("/usuarios")
    assert r.status_code == 200
    assert "Usuarios de la plataforma" in r.get_data(as_text=True)


def test_usuario_bloqueado_pierde_la_sesion(client, monkeypatch):
    monkeypatch.setattr("app.services.users_db.get_user", lambda _id: {"is_active": False, "role": "recepcion"})
    _sesion(client, "recepcion", user_id="u1", checked=0)  # revalidación vencida
    r = client.get("/clientes")
    assert r.status_code == 302 and "/login" in r.headers["Location"]


def test_login_con_usuario_propio_guarda_el_perfil(client, monkeypatch):
    fila = {"id": "u1", "username": "ana", "full_name": "Ana", "role": "recepcion",
            "is_active": True, "password_hash": generate_password_hash("clave-segura")}
    monkeypatch.setattr("app.services.users_db.get_user_by_username", lambda u: fila if u == "ana" else None)
    monkeypatch.setattr("app.services.users_db.touch_login", lambda _id: None)
    r = client.post("/login", data={"username": "ana", "password": "clave-segura"})
    assert r.status_code == 302 and r.headers["Location"].endswith("/dashboard")
    with client.session_transaction() as s:
        assert s["dashboard_role"] == "recepcion" and s["dashboard_user_id"] == "u1"
    assert client.post("/logout").status_code in (302, 405)


def test_login_rechaza_clave_incorrecta_y_usuario_inactivo(monkeypatch):
    fila = {"id": "u1", "username": "ana", "role": "recepcion", "is_active": True,
            "password_hash": generate_password_hash("clave-segura")}
    monkeypatch.setattr("app.services.users_db.get_user_by_username", lambda u: fila)
    assert access.autenticar("ana", "otra", "admin", "x") is None
    fila["is_active"] = False
    assert access.autenticar("ana", "clave-segura", "admin", "x") is None


def test_admin_crea_usuario_con_clave_cifrada(client, monkeypatch):
    creados = []
    monkeypatch.setattr("app.services.users_db.get_user_by_username", lambda u: None)
    monkeypatch.setattr("app.services.users_db.create_user", lambda d: creados.append(d) or {"id": "n1", **d})
    monkeypatch.setattr("app.services.audit_db.registrar", lambda *a, **k: None)
    _sesion(client, "administrador")
    r = client.post("/usuarios", data={"username": "Recepcion.Ana", "full_name": "Ana Pérez",
                                       "role": "recepcion", "password": "clave-segura"})
    assert r.status_code == 302
    assert creados[0]["username"] == "recepcion.ana"
    assert creados[0]["password_hash"] != "clave-segura"
    assert check_password_hash(creados[0]["password_hash"], "clave-segura")


def test_admin_rechaza_clave_corta(client, monkeypatch):
    creados = []
    monkeypatch.setattr("app.services.users_db.get_user_by_username", lambda u: None)
    monkeypatch.setattr("app.services.users_db.create_user", lambda d: creados.append(d))
    _sesion(client, "administrador")
    client.post("/usuarios", data={"username": "ana", "full_name": "Ana", "role": "recepcion", "password": "123"})
    assert creados == []


def test_solo_administrador_entra_a_usuarios(client):
    _sesion(client, "recepcion")
    assert client.get("/usuarios").status_code == 403
