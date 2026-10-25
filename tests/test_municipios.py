"""Cierre v1: municipios cercanos como localidades en la cobertura, el mapa y la asignación."""
from collections import Counter

import pytest

from app import municipios, zone_routing
from app.main import app

MUNICIPIOS = [{"code": "mun_soacha", "name": "Soacha", "lat": 4.57, "lng": -74.21, "is_active": True},
              {"code": "mun_chia", "name": "Chía", "lat": 4.86, "lng": -74.03, "is_active": True},
              {"code": "mun_madrid", "name": "Madrid", "lat": 4.73, "lng": -74.26, "is_active": True}]
COBERTURA = [{"locality_code": "mun_soacha", "courier_id": "cesar"},
             {"locality_code": "mun_madrid", "courier_id": "luis"}]


def test_reconoce_el_municipio_como_palabra_completa_y_sin_tildes():
    assert municipios.coincide("chia", MUNICIPIOS)["code"] == "mun_chia"
    assert municipios.coincide("Soacha, Cundinamarca", MUNICIPIOS)["code"] == "mun_soacha"
    assert municipios.coincide("Barrio Soachita", MUNICIPIOS) is None


def test_el_campo_municipio_del_cliente_asigna_su_motorizado():
    r = zone_routing.resolve_zone_courier(address="Cl 1", zone_text=None, coverage_rows=COBERTURA,
                                          zone_rows=[], city="Soacha", municipios=MUNICIPIOS)
    assert r["courier_id"] == "cesar" and r["source"] == "municipio"


def test_la_direccion_solo_cuenta_si_bogota_no_reconoce_nada(monkeypatch):
    monkeypatch.setattr("app.territory.suggest_zone_for_location",
                        lambda **k: {"match_type": "neighborhood", "locality_code": "kennedy", "zone_number": 4})
    r = zone_routing.resolve_zone_courier(address="Cl 8 sur, barrio Madrid", zone_text=None,
                                          coverage_rows=COBERTURA, zone_rows=[{"zone_number": 4, "courier_id": "z4"}],
                                          city=None, municipios=MUNICIPIOS)
    assert r["courier_id"] == "z4"  # el barrio de Bogotá manda, no el municipio Madrid
    monkeypatch.setattr("app.territory.suggest_zone_for_location", lambda **k: {"match_type": "none"})
    r = zone_routing.resolve_zone_courier(address="Vereda centro, Madrid", zone_text=None,
                                          coverage_rows=COBERTURA, zone_rows=[], city=None, municipios=MUNICIPIOS)
    assert r["courier_id"] == "luis"


def test_municipio_sin_motorizado_sigue_la_cascada_de_bogota(monkeypatch):
    monkeypatch.setattr("app.territory.suggest_zone_for_location", lambda **k: {"match_type": "none"})
    r = zone_routing.resolve_zone_courier(address="x", zone_text=None, coverage_rows=COBERTURA,
                                          zone_rows=[], city="Chía", municipios=MUNICIPIOS)
    assert r is None


def test_los_municipios_entran_en_la_cobertura_y_el_mapa(monkeypatch):
    from app import dashboard
    monkeypatch.setattr("app.services.maestros_db.list_municipios", lambda: MUNICIPIOS)
    clientes = [{"city": "Soacha", "zone": None}, {"city": "", "zone": None, "address": "Centro, Chía"},
                {"city": "Bogotá", "zone": "Kennedy", "address": "Cl 1"}]
    filas, puntos, por_motorizado, locs = [], [], Counter(), {}
    dashboard._agregar_municipios(clientes, {"mun_soacha": {"courier_id": "cesar"}},
                                  {"cesar": {"name": "César"}}, locs, por_motorizado, filas, puntos)
    soacha = next(f for f in filas if f["locality_code"] == "mun_soacha")
    assert soacha["es_municipio"] and soacha["assigned_courier_name"] == "César" and soacha["clients_count"] == 1
    assert next(f for f in filas if f["locality_code"] == "mun_chia")["clients_count"] == 1
    assert len(puntos) == 3 and por_motorizado["cesar"] == 1 and locs["cesar"] == ["Soacha"]


@pytest.fixture
def client():
    app.config["TESTING"] = True
    c = app.test_client()
    with c.session_transaction() as s:
        s["dashboard_authenticated"] = True
        s["dashboard_role"] = "recepcion"
    return c


def test_agregar_municipio_usa_las_coordenadas_conocidas(client, monkeypatch):
    guardados = []
    monkeypatch.setattr("app.services.maestros_db.guardar_municipio",
                        lambda *a: guardados.append(a) or {"code": a[0], "name": a[1]})
    monkeypatch.setattr("app.services.audit_db.registrar", lambda *a, **k: None)
    r = client.post("/api/dashboard/municipio", json={"nombre": "  Cajicá "})
    assert r.get_json()["en_mapa"] is True
    assert guardados[0][:2] == ("mun_cajica", "Cajicá") and guardados[0][2] is not None


def test_asignar_motorizado_a_un_municipio(client, monkeypatch):
    asignados = []
    monkeypatch.setattr("app.services.maestros_db.list_municipios", lambda: MUNICIPIOS)
    monkeypatch.setattr("app.services.db.upsert_courier_locality_coverage", lambda **k: asignados.append(k))
    monkeypatch.setattr("app.services.audit_db.registrar", lambda *a, **k: None)
    r = client.post("/api/dashboard/courier-locality-assignment", json={"locality_code": "mun_chia", "courier_id": "m1"})
    assert r.status_code == 200 and asignados[0]["locality_name"] == "Chía"
    r = client.post("/api/dashboard/courier-locality-assignment", json={"locality_code": "mun_inventado", "courier_id": "m1"})
    assert r.status_code == 400
