"""Pantalla «Autorizaciones de datos» (pedido de A3, 2026-11-25).

A3: «queda registrada la evidencia de cada autorización… no tenemos información de dónde
queda». Estaba en `privacy_consents`, sin pantalla. Solo lectura, solo Administrador.
"""
from unittest.mock import patch

import pytest

from app import dashboard_privacidad as dp
from app import permissions as P
from app.main import app

# Los eventos reales del chat 5 (17/11), del más nuevo al más viejo, como los devuelve la base.
EVENTOS = [
    {"created_at": "2026-11-17T16:12:54+00:00", "contact_key": "+573115824893", "channel": "whatsapp",
     "external_chat_id": "5", "event": "accepted", "response_text": "Sí 👍",
     "policy_version": "2026-11-09", "policy_url": "https://a3laboratorio.co/politica"},
    {"created_at": "2026-11-17T16:08:14+00:00", "contact_key": "+573115824893", "channel": "whatsapp",
     "external_chat_id": "5", "event": "asked", "response_text": None,
     "policy_version": "2026-11-09", "policy_url": "https://a3laboratorio.co/politica"},
    {"created_at": "2026-11-18T10:00:00+00:00", "contact_key": "+573000000000", "channel": "whatsapp",
     "external_chat_id": "9", "event": "asked", "response_text": None,
     "policy_version": "2026-11-09", "policy_url": "https://a3laboratorio.co/politica"},
]
CLIENTES = {"3115824893": "Clara Patricia Rodriguez Palacios"}


def test_cada_fila_dice_quien_cuando_que_y_que_version():
    fila = dp.filas(EVENTOS, CLIENTES)[0]
    assert fila["fecha"] == "17/11/2026 11:12:54"  # hora de Bogotá, con año y segundos
    assert fila["cliente"] == "Clara Patricia Rodriguez Palacios"
    assert fila["evento"] == "Aceptó"
    assert fila["respuesta"] == "Sí 👍"
    assert fila["version"] == "2026-11-09"


@pytest.mark.parametrize("busqueda, cuantas", [("3115824893", 2), ("clara", 2), ("+57 300", 1), ("nadie", 0)])
def test_busca_por_numero_o_por_cliente(busqueda, cuantas):
    assert len(dp.filas(EVENTOS, CLIENTES, busqueda)) == cuantas


def test_el_resumen_cuenta_el_ultimo_estado_de_cada_numero():
    assert dp.resumen(EVENTOS) == {"aceptaron": 1, "rechazaron": 0, "sin_responder": 1, "contactos": 2}


@pytest.fixture
def client():
    app.config["TESTING"] = True
    return app.test_client()


def _sesion(client, perfil):
    with client.session_transaction() as s:
        s["dashboard_authenticated"] = True
        s["dashboard_username"] = "prueba"
        s["dashboard_role"] = perfil


def _con_datos():
    return patch.multiple(dp.privacy_db, listar=lambda: EVENTOS, clientes_por_telefono=lambda: CLIENTES)


def test_el_administrador_ve_la_pantalla(client):
    _sesion(client, "administrador")
    with _con_datos():
        r = client.get("/autorizaciones")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "Autorizaciones de datos" in html and "Clara Patricia Rodriguez Palacios" in html


def test_el_csv_trae_toda_la_evidencia(client):
    _sesion(client, "administrador")
    with _con_datos():
        r = client.get("/autorizaciones.csv")
    texto = r.get_data(as_text=True)
    assert r.mimetype == "text/csv"
    assert texto.splitlines()[0].lstrip("﻿").startswith("Fecha y hora (Bogotá);Número;Cliente")
    assert "17/11/2026 11:12:54;+573115824893;Clara Patricia Rodriguez Palacios;Aceptó;Sí 👍;2026-11-09" in texto


@pytest.mark.parametrize("perfil", [p for p in P.PERFILES if p != "administrador"])
def test_los_demas_perfiles_no_entran(perfil):
    assert P.nivel(perfil, "autorizaciones") == P.NINGUNO


def test_recepcion_no_entra(client):
    _sesion(client, "recepcion")
    with _con_datos():
        r = client.get("/autorizaciones")
    assert r.status_code in (302, 403)


def test_si_la_base_falla_la_pantalla_avisa(client):
    _sesion(client, "administrador")
    with patch.object(dp.privacy_db, "listar", side_effect=RuntimeError("caída")):
        r = client.get("/autorizaciones")
    assert r.status_code == 200
    assert "No se pudo leer la evidencia" in r.get_data(as_text=True)
