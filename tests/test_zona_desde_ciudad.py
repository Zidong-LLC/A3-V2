"""Clientes sin zona: la localidad venía escrita en «ciudad» y nadie la leía (ERR-193).

571 de 861 clientes no tenían zona; 95 traían la localidad en el campo ciudad («Timiza,
Kennedy», «Castilla», «Suba»). El bot no podía asignarles motorizado y el dashboard no los
ponía en el mapa. Ahora los dos usan la misma cascada, y Clientes tiene el filtro «Sin zona»
para que A3 complete a los que quedan.
"""
from unittest.mock import patch

import pytest

from app import client_filters, zone_routing

ZONAS = [{"zone_number": n, "courier_id": f"zona-{n}"} for n in range(1, 9)]


@pytest.mark.parametrize("ciudad, localidad", [
    ("Timiza, Kennedy", "kennedy"),
    ("Castilla", "kennedy"),
    ("Suba", "suba"),
    ("El Plan, Suba", "suba"),
    ("Olaya, Rafael Uribe Uribe", "rafael_uribe_uribe"),
    ("Engativá", "engativa"),
])
def test_lee_la_localidad_del_campo_ciudad(ciudad, localidad):
    assert zone_routing.sugerencia_por_ciudad(ciudad).get("locality_code") == localidad


@pytest.mark.parametrize("ciudad", ["Bogotá, D.C.", "Bogotá", "", None])
def test_bogota_a_secas_no_ubica_nada(ciudad):
    assert zone_routing.sugerencia_por_ciudad(ciudad)["match_type"] == "none"


def test_el_bot_asigna_por_la_localidad_de_la_ciudad():
    resultado = zone_routing.resolve_zone_courier(
        address="CL 40F SUR 74D-16", zone_text=None, city="Timiza, Kennedy",
        coverage_rows=[{"locality_code": "kennedy", "courier_id": "cesar"}], zone_rows=ZONAS)

    assert resultado["courier_id"] == "cesar"
    assert resultado["locality_code"] == "kennedy"


def test_la_zona_cargada_sigue_mandando_sobre_la_ciudad():
    resultado = zone_routing.resolve_zone_courier(
        address=None, zone_text="Suba", city="Timiza, Kennedy",
        coverage_rows=[], zone_rows=ZONAS)

    assert resultado["locality_code"] == "suba"


def test_solo_calle_y_numero_sigue_sin_ubicar():
    assert zone_routing.resolve_zone_courier(
        address="Cra 71 23-65", zone_text="No aplica", city="Bogotá, D.C.",
        coverage_rows=[], zone_rows=ZONAS) is None


def _contexto(clientes, municipios):
    from app.dashboard import _build_motorizados_context

    with patch("app.dashboard.db.list_couriers", return_value=[]), \
         patch("app.dashboard.db.list_courier_locality_coverage", return_value=[]), \
         patch("app.dashboard.db.list_territorial_zones", return_value=[]), \
         patch("app.dashboard.db.list_territorial_neighborhoods", return_value=[]), \
         patch("app.dashboard.maestros_db.list_municipios", return_value=municipios):
        return _build_motorizados_context(clientes)


def test_el_dashboard_ubica_igual_que_el_bot_y_sin_contar_dos_veces():
    soacha = {"code": "soacha", "name": "Soacha", "is_active": True, "lat": 4.58, "lng": -74.21}
    clientes = [
        {"id": "k", "clinic_name": "Timiza", "city": "Timiza, Kennedy", "address": "CL 40F SUR 74D-16"},
        {"id": "s", "clinic_name": "Soachuna", "city": "Soacha", "address": "Barrio La Academia"},
        {"id": "x", "clinic_name": "Sin datos", "city": "Bogotá, D.C.", "address": "Cra 71 23-65"},
    ]
    contexto = _contexto(clientes, [soacha])

    por_zona = {r["locality_code"]: r["clients_count"] for r in contexto["localities_rows"]}
    assert por_zona["kennedy"] == 1
    assert por_zona["soacha"] == 1  # «La Academia» es un barrio de Bogotá, pero la ciudad es Soacha
    assert sum(por_zona.values()) == 2
    assert contexto["clientes_ubicados"] == ["k", "s"]


def test_filtro_sin_zona_en_clientes():
    filas = [{"client_id": "a", "sin_zona": True}, {"client_id": "b", "sin_zona": False}]

    assert [f["client_id"] for f in client_filters.filtrar(filas, zona="sin")] == ["a"]
    assert [f["client_id"] for f in client_filters.filtrar(filas, zona="con")] == ["b"]
    assert len(client_filters.filtrar(filas)) == 2
    assert client_filters.desde_args({"zona": "sin"}) == {"zona": "sin"}
