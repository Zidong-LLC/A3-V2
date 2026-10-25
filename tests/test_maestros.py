"""Cierre v1: ficha editable del cliente, baja y traslado de motorizados, historial."""
import pytest

from app.main import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    c = app.test_client()
    with c.session_transaction() as s:
        s["dashboard_authenticated"] = True
        s["dashboard_username"] = "ana"
        s["dashboard_role"] = "recepcion"
    return c


@pytest.fixture
def auditoria(monkeypatch):
    registros = []
    monkeypatch.setattr("app.services.audit_db.registrar", lambda *a, **k: registros.append(a))
    return registros


def test_ficha_guarda_solo_lo_que_cambio_y_lo_registra(client, monkeypatch, auditoria):
    guardado = {}
    monkeypatch.setattr("app.services.maestros_db.get_client_any",
                        lambda cid: {"id": cid, "clinic_name": "Norte", "phone": "1", "city": None, "is_active": True})
    monkeypatch.setattr("app.services.maestros_db.actualizar_cliente", lambda cid, c: guardado.update(c) or True)
    r = client.post("/api/dashboard/client-ficha", json={"client_id": "c1", "cambios": {
        "clinic_name": "Norte", "phone": "300 111", "city": "Soacha"}})
    assert r.status_code == 200
    assert guardado == {"phone": "300 111", "city": "Soacha"}
    entidad, entity_id, accion, cambios = auditoria[0]
    assert (entidad, entity_id, accion) == ("client", "c1", "update")
    assert cambios["city"] == {"antes": None, "despues": "Soacha"}


def test_ficha_no_permite_nombre_vacio(client, monkeypatch):
    monkeypatch.setattr("app.services.maestros_db.get_client_any", lambda cid: {"id": cid, "clinic_name": "Norte"})
    r = client.post("/api/dashboard/client-ficha", json={"client_id": "c1", "cambios": {"clinic_name": "  "}})
    assert r.status_code == 400


def test_ficha_reactiva_cliente(client, monkeypatch, auditoria):
    monkeypatch.setattr("app.services.maestros_db.get_client_any", lambda cid: {"id": cid, "is_active": False})
    monkeypatch.setattr("app.services.maestros_db.actualizar_cliente", lambda cid, c: True)
    client.post("/api/dashboard/client-ficha", json={"client_id": "c1", "cambios": {"is_active": True}})
    assert auditoria[0][2] == "activate"


def test_motorizado_con_clientes_no_se_elimina(client, monkeypatch):
    monkeypatch.setattr("app.services.db.get_courier", lambda cid: {"id": cid, "name": "Javier"})
    monkeypatch.setattr("app.services.maestros_db.historia_motorizado",
                        lambda cid: {"recogidas": 0, "clientes": 4, "localidades": 0, "zonas": 0})
    r = client.post("/api/dashboard/courier-delete", json={"courier_id": "m1"})
    assert r.status_code == 409 and "traslada" in r.get_json()["error"]


def test_motorizado_con_recogidas_no_se_elimina(client, monkeypatch):
    monkeypatch.setattr("app.services.db.get_courier", lambda cid: {"id": cid, "name": "Javier"})
    monkeypatch.setattr("app.services.maestros_db.historia_motorizado",
                        lambda cid: {"recogidas": 12, "clientes": 0, "localidades": 0, "zonas": 0})
    r = client.post("/api/dashboard/courier-delete", json={"courier_id": "m1"})
    assert r.status_code == 409 and "Desactívalo" in r.get_json()["error"]


def test_motorizado_sin_historia_se_elimina(client, monkeypatch, auditoria):
    eliminados = []
    monkeypatch.setattr("app.services.db.get_courier", lambda cid: {"id": cid, "name": "Nuevo"})
    monkeypatch.setattr("app.services.maestros_db.historia_motorizado",
                        lambda cid: {"recogidas": 0, "clientes": 0, "localidades": 0, "zonas": 0})
    monkeypatch.setattr("app.services.maestros_db.eliminar_motorizado", lambda cid: eliminados.append(cid) or True)
    r = client.post("/api/dashboard/courier-delete", json={"courier_id": "m9"})
    assert r.status_code == 200 and eliminados == ["m9"]
    assert auditoria[0][:3] == ("courier", "m9", "delete")


@pytest.fixture
def traslado(monkeypatch):
    estado = {"trasladar": None, "avisos": []}
    monkeypatch.setattr("app.services.db.get_courier", lambda cid: {"id": cid, "name": cid.upper()})
    monkeypatch.setattr("app.services.maestros_db.historia_motorizado",
                        lambda cid: {"recogidas": 9, "clientes": 30, "localidades": 2, "zonas": 1})
    monkeypatch.setattr("app.services.maestros_db.recogidas_pendientes", lambda o, f, z: [
        {"id": "r1", "order_number": "A-1", "pickup_address": "Cl 1", "scheduled_pickup_date": f,
         "clients": {"clinic_name": "Norte"}},
        {"id": "r2", "order_number": "A-2", "pickup_address": "Cl 2", "scheduled_pickup_date": f,
         "clients": {"clinic_name": "Sur"}}])
    monkeypatch.setattr("app.services.maestros_db.trasladar",
                        lambda o, d, c, l, ids: estado.update(trasladar=(o, d, c, l, ids)) or
                        {"clientes": 0, "localidades": 0, "zonas": 0, "recogidas": len(ids)})
    monkeypatch.setattr("app.dashboard_maestros.notify_assignment",
                        lambda courier, **k: estado["avisos"].append((courier, k["order_number"])))
    return estado


def test_reemplazo_del_dia_primero_muestra_el_plan_sin_mover_nada(client, traslado):
    r = client.post("/api/dashboard/courier-transfer", json={
        "origen": "jef", "destino": "ale", "recogidas": "dia", "fecha": "2026-10-20"})
    assert r.status_code == 200
    assert r.get_json()["plan"] == {"clientes": 0, "localidades": 0, "zonas": 0, "recogidas": 2}
    assert traslado["trasladar"] is None and traslado["avisos"] == []


def test_reemplazo_del_dia_confirmado_mueve_y_avisa(client, traslado, auditoria):
    r = client.post("/api/dashboard/courier-transfer", json={
        "origen": "jef", "destino": "ale", "recogidas": "dia", "fecha": "2026-10-20", "confirmar": True})
    assert r.status_code == 200
    assert traslado["trasladar"] == ("jef", "ale", False, False, ["r1", "r2"])
    assert traslado["avisos"] == [("ale", "A-1"), ("ale", "A-2")]
    assert auditoria[0][:3] == ("courier", "jef", "transfer")


def test_traslado_requiere_motorizados_distintos_y_fecha(client, traslado):
    assert client.post("/api/dashboard/courier-transfer", json={"origen": "a", "destino": "a"}).status_code == 400
    r = client.post("/api/dashboard/courier-transfer", json={"origen": "a", "destino": "b", "recogidas": "dia"})
    assert r.status_code == 400


def test_procesamiento_no_puede_trasladar_motorizados(client, traslado):
    with client.session_transaction() as s:
        s["dashboard_role"] = "procesamiento"
    r = client.post("/api/dashboard/courier-transfer", json={"origen": "a", "destino": "b"})
    assert r.status_code == 403


def test_historial_por_entidad(client, monkeypatch):
    monkeypatch.setattr("app.services.audit_db.listar",
                        lambda e, i, limit=50: [{"action": "update", "changes": {"phone": "1"}, "username": "ana"}])
    r = client.get("/api/dashboard/historial?entidad=courier&id=m1")
    assert r.get_json()["cambios"][0]["username"] == "ana"
    assert client.get("/api/dashboard/historial?entidad=otra&id=m1").status_code == 400


def test_traslado_informa_cuantos_avisos_salieron_de_verdad(client, traslado, auditoria, monkeypatch):
    monkeypatch.setattr("app.dashboard_maestros.notify_assignment", lambda courier, **k: k["order_number"] == "A-1")
    r = client.post("/api/dashboard/courier-transfer", json={
        "origen": "jef", "destino": "ale", "recogidas": "dia", "fecha": "2026-10-20", "confirmar": True})
    assert r.get_json()["avisos"] == 1 and r.get_json()["hecho"]["recogidas"] == 2


def test_no_se_desactiva_un_motorizado_con_clientes(client, monkeypatch):
    actualizados = []
    monkeypatch.setattr("app.services.maestros_db.historia_motorizado",
                        lambda cid: {"recogidas": 0, "clientes": 3, "localidades": 0, "zonas": 0})
    monkeypatch.setattr("app.services.db.update_courier", lambda cid, c: actualizados.append(c) or True)
    r = client.post("/api/dashboard/courier", json={"courier_id": "m1", "is_active": False})
    assert r.status_code == 409 and "traslada" in r.get_json()["error"] and actualizados == []


def test_filtro_de_zona_del_traslado_ignora_tildes(monkeypatch):
    from unittest.mock import MagicMock

    from app.services import maestros_db

    base = MagicMock()
    consulta = base.table.return_value.select.return_value.eq.return_value.in_.return_value
    consulta.limit.return_value.execute.return_value.data = [
        {"id": "r1", "clients": {"zone": None, "city": "Bogotá"}},
        {"id": "r2", "clients": {"zone": "Soacha.Centro", "city": None}}]
    monkeypatch.setattr(maestros_db, "_client", base)
    assert [f["id"] for f in maestros_db.recogidas_pendientes("m1", zona="bogota")] == ["r1"]
    assert [f["id"] for f in maestros_db.recogidas_pendientes("m1", zona="SOACHA")] == ["r2"]
