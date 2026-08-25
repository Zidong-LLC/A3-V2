"""Pantalla de emparejamiento de clientes de Anarvet (Fase 2).

Los endpoints de asignación existían desde la Fase 1 pero ningún template los usaba: la
única forma de resolver un mapeo era correr un script. Sin mapeo, el 41% de los informes
no tenía dueño y no podía publicarse en el portal.
"""
from unittest.mock import patch

import pytest

from app import dashboard as dash
from app import dashboard_anarvet as danarvet

MAPA = [
    {"cod_cliente": "75", "nombre_cliente": "Emergencias Veterinarias Integrales",
     "client_id": None, "match_source": "pending"},
    {"cod_cliente": "572", "nombre_cliente": "Clinica Veterinaria Zoopecas",
     "client_id": None, "match_source": "pending"},
    {"cod_cliente": "10", "nombre_cliente": "Animal Pets",
     "client_id": "ap", "match_source": "auto"},
]
CLIENTES = [
    {"id": "evi", "clinic_name": "Emergencias Veterinarias Integrales", "is_active": True},
    {"id": "z1", "clinic_name": "Clinica Veterinaria Zoopecas", "is_active": True},
    {"id": "z2", "clinic_name": "Zoopecas SAS", "is_active": True},
    {"id": "ap", "clinic_name": "Animal Pets", "is_active": True},
]
# El código 572 (ambiguo) pesa más que el 75, pero solo el 75 se puede resolver solo.
INFORMES = {"75": 65, "572": 13, "10": 4}


@pytest.fixture(autouse=True)
def anarvet_encendido(monkeypatch):
    monkeypatch.setattr(danarvet, "ANARVET_ENABLED", True)
    monkeypatch.setattr(dash, "ANARVET_ENABLED", True)


def _client_logueado():
    from app.main import app

    app.config["TESTING"] = True
    c = app.test_client()
    with c.session_transaction() as s:
        s["dashboard_authenticated"] = True
        s["dashboard_username"] = "admin"
    return c


def _patches_lectura():
    return (
        patch.object(danarvet.db, "list_anarvet_client_map", return_value=list(MAPA)),
        patch.object(danarvet.db, "list_clients_with_assignment", return_value=list(CLIENTES)),
        patch.object(danarvet.db, "count_anarvet_informes_por_cliente", return_value=dict(INFORMES)),
    )


def test_la_pantalla_pide_login():
    from app.main import app

    app.config["TESTING"] = True
    resp = app.test_client().get("/resultados/anarvet/clientes")
    assert resp.status_code in (301, 302)
    assert "/login" in resp.headers.get("Location", "")


def test_muestra_lo_pendiente_y_lo_ya_emparejado():
    c = _client_logueado()
    p = _patches_lectura()
    with p[0], p[1], p[2]:
        html = c.get("/resultados/anarvet/clientes").get_data(as_text=True)

    assert "Necesitan una decisión (1)" in html   # solo el 572; el 75 resuelve solo
    assert "Ya emparejados (1)" in html
    assert "Emparejar 1 automáticamente" in html
    # Los dos candidatos del ambiguo se muestran para que el humano elija.
    assert "Clinica Veterinaria Zoopecas" in html and "Zoopecas SAS" in html


def test_cuenta_cuantos_informes_desbloquea_cada_uno():
    """Sin ese número no se sabe cuál resolver primero."""
    c = _client_logueado()
    p = _patches_lectura()
    with p[0], p[1], p[2]:
        html = c.get("/resultados/anarvet/clientes").get_data(as_text=True)

    assert "4 de 82" in html   # informes con dueño / total (4 del cliente ya mapeado)


def test_el_automatch_solo_aplica_lo_inequivoco():
    """La regla de privacidad: con dos candidatos no se elige. Un mapeo errado le muestra
    los resultados de un paciente a la veterinaria equivocada."""
    c = _client_logueado()
    asignados = []
    with patch.object(dash.db, "list_anarvet_client_map",
                      return_value=[m for m in MAPA if not m["client_id"]]), \
         patch.object(dash.db, "list_clients_with_assignment", return_value=list(CLIENTES)), \
         patch.object(dash.db, "assign_anarvet_client",
                      side_effect=lambda cod, cid, src: asignados.append((cod, cid, src))):
        resp = c.post("/api/dashboard/anarvet/clients/automatch")

    assert resp.status_code == 200
    datos = resp.get_json()
    assert datos["aplicados"] == 1 and datos["ambiguos"] == 1
    assert asignados == [("75", "evi", "auto")], "solo el inequívoco"


def test_el_automatch_respeta_el_flag(monkeypatch):
    monkeypatch.setattr(dash, "ANARVET_ENABLED", False)
    resp = _client_logueado().post("/api/dashboard/anarvet/clients/automatch")
    assert resp.status_code == 400


def test_una_fila_que_falla_no_aborta_el_resto():
    c = _client_logueado()
    mapa = [
        {"cod_cliente": "75", "nombre_cliente": "Emergencias Veterinarias Integrales",
         "client_id": None, "match_source": "pending"},
        {"cod_cliente": "10", "nombre_cliente": "Animal Pets",
         "client_id": None, "match_source": "pending"},
    ]

    def _falla_el_primero(cod, cid, src):
        if cod == "75":
            raise RuntimeError("timeout")

    with patch.object(dash.db, "list_anarvet_client_map", return_value=mapa), \
         patch.object(dash.db, "list_clients_with_assignment", return_value=list(CLIENTES)), \
         patch.object(dash.db, "assign_anarvet_client", side_effect=_falla_el_primero):
        resp = c.post("/api/dashboard/anarvet/clients/automatch")

    assert resp.status_code == 207
    assert resp.get_json()["aplicados"] == 1
