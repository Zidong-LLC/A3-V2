"""Pedido de A3 (2026-11-09): que recepción pueda cargar una CONTRAMUESTRA (no se factura) y
registrar la RECOLECCIÓN EFECTIVA de lo que el motorizado recogió sin ruta programada.

Las dos viven en «Nueva Orden». Lo que no puede pasar: que una contramuestra abra pedido o
guarde precios, que una recogida ya hecha le avise al motorizado, o que las órdenes del chat
y del portal cambien en algo.
"""
from datetime import date
from unittest.mock import patch

import pytest

from app import orden_manual
from tests.test_dashboard_new_request import _form, _get_test_client, _login, _patches
from tests.test_pedidos_data_layer import _payload, supabase  # noqa: F401 — fixture

HOY = date(2026, 11, 9)


@pytest.fixture(autouse=True)
def _sin_red(monkeypatch):
    abiertos = []
    monkeypatch.setattr("app.pedido_directo.db.create_pedido",
                        lambda *a, **k: abiertos.append(a) or {"id": "ped-1", "pedido_number": "P-2026-001"})
    monkeypatch.setattr("app.pedido_directo.db.close_pedido", lambda *a, **k: None)
    monkeypatch.setattr("app.pedido_directo.config.ALEGRA_ENABLED", False)
    monkeypatch.setattr("app.dashboard.db.list_couriers",
                        lambda *a, **k: [{"id": "mot-2", "name": "Javier", "is_active": True}])
    monkeypatch.setattr("app.dashboard.maestros_db.courier_de_cliente", lambda cid: "mot-1")
    return abiertos


# ── Lógica pura ─────────────────────────────────────────────────────────────

def test_la_contramuestra_no_guarda_nada_con_precio():
    campos = {"patient_name": "Lola", "exam_type": "Perfil Renal, Creatinina", "observations": "sin observaciones",
              "_selected_profile_code": "653", "_selected_profile_price": 45000, "_selected_profile_name": "Perfil Renal",
              "_extra_profiles": [{"code": "1", "price": 1}], "selected_tests": ["1404"]}
    limpio = orden_manual.como_contramuestra(campos)
    assert limpio["exam_type"] == "Contramuestra: Perfil Renal, Creatinina"
    assert limpio["observations"] == "CONTRAMUESTRA: no se factura."
    assert limpio["patient_name"] == "Lola"
    assert not any(k.startswith("_selected") or k in ("_extra_profiles", "selected_tests") for k in limpio)
    assert orden_manual.es_contramuestra(limpio["exam_type"])


def test_la_contramuestra_sin_analisis_igual_queda_rotulada_y_conserva_la_observacion():
    limpio = orden_manual.como_contramuestra({"exam_type": "", "observations": "confirmar creatinina alta"})
    assert limpio["exam_type"] == "Contramuestra"
    assert limpio["observations"] == "CONTRAMUESTRA: no se factura. confirmar creatinina alta"


def test_el_perfil_que_se_guarda_de_una_contramuestra_vale_cero():
    from app import billing
    from app.services import db
    perfil = db._profile_event_payload(orden_manual.como_contramuestra({"exam_type": "Perfil Renal"}))
    assert perfil["total_estimated"] == 0
    assert billing.build_invoice_lines(perfil) == [], "aunque alguien la metiera en un pedido, no factura"


def test_la_recoleccion_efectiva_nace_recogida_con_su_fecha_y_motorizado():
    columnas, error = orden_manual.recoleccion("2026-11-07", "mot-9", "mot-1", hoy=HOY)
    assert error is None
    assert columnas == {"status": "picked_up", "assigned_courier_id": "mot-9",
                        "scheduled_pickup_date": "2026-11-07", "fallback_reason": None}


def test_sin_fecha_es_hoy_y_sin_motorizado_es_el_del_cliente():
    columnas, _ = orden_manual.recoleccion("", "", "mot-1", hoy=HOY)
    assert columnas["scheduled_pickup_date"] == "2026-11-09" and columnas["assigned_courier_id"] == "mot-1"


@pytest.mark.parametrize("fecha,elegido,asignado,dice", [
    ("2026-11-10", "mot-9", "mot-1", "no puede ser futura"),
    ("09/11/2026", "mot-9", "mot-1", "no es válida"),
    ("2026-11-09", "", None, "Elige el motorizado"),
])
def test_la_recoleccion_no_se_inventa_datos(fecha, elegido, asignado, dice):
    columnas, error = orden_manual.recoleccion(fecha, elegido, asignado, hoy=HOY)
    assert columnas is None and dice in error


# ── «Nueva Orden» ───────────────────────────────────────────────────────────

def _enviar(monkeypatch, **campos):
    client = _get_test_client()
    _login(client, monkeypatch)
    p = _patches()
    with p[0], p[1], p[2], p[3], p[4], p[5], p[6] as create, \
         patch("app.dashboard.db.create_request_event") as evento:
        resp = client.post("/solicitudes/nueva", data=_form(**campos))
    return resp, create, evento


def test_una_orden_comun_llega_a_la_base_igual_que_antes(monkeypatch, _sin_red):
    resp, create, evento = _enviar(monkeypatch)
    assert resp.status_code in (301, 302) and len(_sin_red) == 1
    assert set(create.call_args.kwargs) == {"chat_id", "session", "pedido_id", "ai_response"}
    assert not evento.called


def test_la_contramuestra_no_abre_pedido_ni_lleva_precios(monkeypatch, _sin_red):
    resp, create, _ = _enviar(monkeypatch, facturacion="contramuestra")
    assert resp.status_code in (301, 302)
    assert _sin_red == [], "abrir un pedido es lo que después la factura"
    campos = create.call_args.kwargs["ai_response"]["captured_fields"]
    assert create.call_args.kwargs["pedido_id"] is None
    assert campos["exam_type"].startswith("Contramuestra: ") and "_selected_profile_price" not in campos
    assert "no+se+factura" in resp.headers["Location"] or "no%20se%20factura" in resp.headers["Location"]


def test_la_contramuestra_puede_ir_sin_analisis_pero_no_sin_paciente(monkeypatch):
    with patch("app.orders.db.find_catalog_profile", return_value=None):
        resp, create, _ = _enviar(monkeypatch, facturacion="contramuestra", profile_code="")
    assert resp.status_code in (301, 302)
    assert create.call_args.kwargs["ai_response"]["captured_fields"]["exam_type"] == "Contramuestra"
    resp, create, _ = _enviar(monkeypatch, facturacion="contramuestra", patient_name="")
    assert resp.status_code == 200 and not create.called


def test_la_recoleccion_efectiva_se_registra_recogida_y_sin_avisar_al_motorizado(monkeypatch, _sin_red):
    resp, create, evento = _enviar(monkeypatch, recogida="recolectada", collected_date="2026-11-07",
                                   collected_courier_id="mot-2")
    assert resp.status_code in (301, 302) and len(_sin_red) == 1, "se factura como cualquier orden"
    assert create.call_args.kwargs["columnas"] == {
        "status": "picked_up", "assigned_courier_id": "mot-2", "scheduled_pickup_date": "2026-11-07",
        "fallback_reason": None}
    assert create.call_args.kwargs["avisar_motorizado"] is False
    tipo, traza = evento.call_args.args[1], evento.call_args.args[2]
    assert tipo == "dashboard_status_update" and traza["status"] == "picked_up" and "sin ruta" in traza["nota"]


def test_la_recoleccion_usa_el_motorizado_del_cliente_si_no_se_elige_otro(monkeypatch):
    _, create, _ = _enviar(monkeypatch, recogida="recolectada", collected_date="")
    assert create.call_args.kwargs["columnas"]["assigned_courier_id"] == "mot-1"


def test_un_motorizado_que_no_esta_en_la_lista_no_se_acepta(monkeypatch):
    resp, create, _ = _enviar(monkeypatch, recogida="recolectada", collected_courier_id="inventado")
    assert resp.status_code == 200 and not create.called
    assert "motorizado de la lista" in resp.get_data(as_text=True)


def test_una_fecha_futura_vuelve_al_formulario_sin_registrar(monkeypatch):
    resp, create, _ = _enviar(monkeypatch, recogida="recolectada", collected_date="2999-01-01")
    assert resp.status_code == 200 and not create.called
    assert "no puede ser futura" in resp.get_data(as_text=True)


def test_el_formulario_ofrece_las_dos_opciones_y_los_motorizados(monkeypatch):
    client = _get_test_client()
    _login(client, monkeypatch)
    p = _patches()
    with p[0], p[1], p[2], p[3]:
        html = client.get("/solicitudes/nueva").get_data(as_text=True)
    assert 'name="recogida"' in html and "Ya recolectada, sin ruta programada" in html
    assert 'name="facturacion"' in html and "Contramuestra: no se factura" in html
    assert 'name="collected_courier_id"' in html and "Javier" in html


# ── Capa de datos ───────────────────────────────────────────────────────────

def test_las_columnas_manuales_pisan_lo_calculado_y_no_se_avisa(supabase):  # noqa: F811
    from app.services import db
    ai = {"intent": "route_scheduling", "captured_fields": {"clinic_name": "Vet"}}
    columnas = {"status": "picked_up", "assigned_courier_id": "mot-2", "scheduled_pickup_date": "2026-11-07"}
    with patch("app.courier_notify.notify_assignment") as aviso:
        db.create_request("dashboard:ana", {"client_id": None}, ai, columnas=columnas, avisar_motorizado=False)
    enviado = _payload(supabase, "requests", "insert")[0]
    assert enviado["status"] == "picked_up" and enviado["assigned_courier_id"] == "mot-2"
    assert enviado["scheduled_pickup_date"] == "2026-11-07"
    assert not aviso.called
