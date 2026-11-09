"""Eliminar una orden o quitarle un análisis desde Pedidos (pedido de A3, 2026-11-09).

Lo que estos tests cuidan es que NO cause problemas: respaldo antes de borrar, nada de tocar
lo que el laboratorio ya procesó, lo que el cliente ya pagó o lo que ya se emitió, y nunca
escribir en Alegra.
"""
import pytest

from app import dashboard_ordenes
from app.main import app
from tests.test_orden_edicion import CON_PERFILES

ORDEN = {"id": "req-1", "order_number": "A3-2026-050", "pedido_id": "ped-1", "status": "assigned",
         "assigned_courier_id": "mot-1", "couriers": {"name": "Javier"}, "patient_name": "Lola",
         "exam_type": "Perfil Toxicológico, Perfil Renal, Citología PAF"}
PEDIDO = {"id": "ped-1", "status": "cerrado", "alegra_invoice_id": None}


def _cliente(perfil="recepcion"):
    app.config["TESTING"] = True
    c = app.test_client()
    with c.session_transaction() as s:
        s["dashboard_authenticated"] = True
        s["dashboard_username"] = "ana"
        s["dashboard_role"] = perfil
    return c


@pytest.fixture
def base(monkeypatch):
    """Una orden limpia dentro de un pedido cerrado sin factura; cada test cambia lo suyo."""
    estado = {"orden": dict(ORDEN), "pedido": dict(PEDIDO), "ataduras": {"muestras": 0, "resultados": 0},
              "pagos": [], "factura": None, "pasos": []}
    db = dashboard_ordenes.ordenes_db
    monkeypatch.setattr(db, "orden", lambda rid: estado["orden"] if rid == "req-1" else None)
    monkeypatch.setattr(db, "pedido", lambda pid: estado["pedido"] if pid else None)
    monkeypatch.setattr(db, "ataduras", lambda rid: estado["ataduras"])
    monkeypatch.setattr(db, "pagos", lambda pid: estado["pagos"])
    monkeypatch.setattr(db, "foto", lambda fila, ped: {"orden": fila, "eventos": [], "pedido": ped})
    monkeypatch.setattr(db, "evento_creacion",
                        lambda rid: {"id": "ev-1", "event_payload": {"profile": CON_PERFILES, "service_order": {}}})
    monkeypatch.setattr(db, "respaldar", lambda rid, accion, foto, quien: estado["pasos"].append(("respaldo", accion, foto, quien)))
    monkeypatch.setattr(db, "borrar", lambda rid, ped: estado["pasos"].append(("borrar", rid)) or False)
    monkeypatch.setattr(db, "guardar_perfil",
                        lambda rid, ev, perfil, texto: estado["pasos"].append(("guardar", perfil, texto)))
    monkeypatch.setattr(dashboard_ordenes.db, "create_request_event",
                        lambda rid, tipo, datos: estado["pasos"].append(("evento", tipo, datos)))

    def _leer_factura(invoice_id):
        if estado["factura"] is None:
            raise RuntimeError("Alegra no responde")
        return {"id": invoice_id, "status": estado["factura"]}

    monkeypatch.setattr(dashboard_ordenes.alegra, "get_invoice", _leer_factura)
    return estado


def _hechos(estado):
    return [p[0] for p in estado["pasos"]]


# ── Eliminar la orden ───────────────────────────────────────────────────────

def test_eliminar_guarda_el_respaldo_antes_de_borrar(base):
    r = _cliente().post("/api/dashboard/order-delete", json={"request_id": "req-1"})
    assert r.status_code == 200 and r.get_json()["order_number"] == "A3-2026-050"
    assert _hechos(base) == ["respaldo", "borrar"]
    _, accion, foto, quien = base["pasos"][0]
    assert accion == "delete" and foto["orden"]["patient_name"] == "Lola" and quien == "ana"
    assert any("Javier" in a for a in r.get_json()["avisos"]), "el motorizado ya tenía la recogida"


def test_si_el_respaldo_falla_no_se_borra(base, monkeypatch):
    def _roto(*_a):
        raise RuntimeError("audit_log caído")
    monkeypatch.setattr(dashboard_ordenes.ordenes_db, "respaldar", _roto)
    r = _cliente().post("/api/dashboard/order-delete", json={"request_id": "req-1"})
    assert r.status_code == 503 and "borrar" not in _hechos(base)


@pytest.mark.parametrize("ataduras", [{"muestras": 1, "resultados": 0}, {"muestras": 0, "resultados": 2}])
def test_con_muestras_o_resultados_en_el_laboratorio_no_se_toca(base, ataduras):
    base["ataduras"] = ataduras
    for ruta, cuerpo in (("order-delete", {"request_id": "req-1"}),
                         ("order-line-delete", {"request_id": "req-1", "index": 2, "code": "1903"})):
        r = _cliente().post(f"/api/dashboard/{ruta}", json=cuerpo)
        assert r.status_code == 409 and "Cancelada" in r.get_json()["error"]
    assert base["pasos"] == []


def test_un_pedido_ya_pagado_en_linea_no_se_toca(base):
    base["pagos"] = [{"status": "declined"}, {"status": "approved"}]
    r = _cliente().post("/api/dashboard/order-delete", json={"request_id": "req-1"})
    assert r.status_code == 409 and "pagado en línea" in r.get_json()["error"] and base["pasos"] == []


def test_un_pedido_abierto_en_el_chat_no_se_toca(base):
    """El agente factura el pedido abierto con lo que lleva en la sesión: borrar acá no llegaría."""
    base["pedido"]["status"] = "abierto"
    for ruta, cuerpo in (("order-delete", {"request_id": "req-1"}),
                         ("order-line-delete", {"request_id": "req-1", "index": 2, "code": "1903"})):
        r = _cliente().post(f"/api/dashboard/{ruta}", json=cuerpo)
        assert r.status_code == 409 and "sigue abierto" in r.get_json()["error"]
    assert base["pasos"] == []


def test_un_link_de_pago_pendiente_solo_avisa(base):
    base["pagos"] = [{"status": "pending"}]
    r = _cliente().post("/api/dashboard/order-delete", json={"request_id": "req-1"})
    assert r.status_code == 200 and any("link de pago" in a for a in r.get_json()["avisos"])


def test_con_borrador_en_alegra_se_borra_y_se_avisa_que_hay_que_corregirlo_alla(base):
    base["pedido"]["alegra_invoice_id"], base["factura"] = "8812", "draft"
    r = _cliente().post("/api/dashboard/order-delete", json={"request_id": "req-1"})
    assert r.status_code == 200 and "borrar" in _hechos(base)
    assert any("8812" in a and "no modifica Alegra" in a for a in r.get_json()["avisos"])


@pytest.mark.parametrize("estado", ["open", "closed"])
def test_con_la_factura_ya_emitida_no_se_toca(base, estado):
    base["pedido"]["alegra_invoice_id"], base["factura"] = "8812", estado
    r = _cliente().post("/api/dashboard/order-delete", json={"request_id": "req-1"})
    assert r.status_code == 409 and "nota crédito" in r.get_json()["error"] and base["pasos"] == []


def test_si_no_se_puede_verificar_la_factura_no_se_adivina(base):
    base["pedido"]["alegra_invoice_id"] = "8812"  # y Alegra no responde
    r = _cliente().post("/api/dashboard/order-delete", json={"request_id": "req-1"})
    assert r.status_code == 409 and "No pude verificar" in r.get_json()["error"] and base["pasos"] == []


def test_una_orden_suelta_se_elimina_sin_mirar_pagos_ni_facturas(base, monkeypatch):
    base["orden"]["pedido_id"] = None
    monkeypatch.setattr(dashboard_ordenes.ordenes_db, "pagos", lambda pid: pytest.fail("no hay pedido"))
    r = _cliente().post("/api/dashboard/order-delete", json={"request_id": "req-1"})
    assert r.status_code == 200 and "borrar" in _hechos(base)


def test_una_orden_que_no_existe_o_sin_id(base):
    assert _cliente().post("/api/dashboard/order-delete", json={"request_id": "otra"}).status_code == 404
    assert _cliente().post("/api/dashboard/order-delete", json={}).status_code == 400


# ── Quitar un análisis ──────────────────────────────────────────────────────

def test_ver_las_lineas_de_la_orden(base):
    r = _cliente().get("/api/dashboard/order-lines?request_id=req-1")
    datos = r.get_json()
    assert [l["code"] for l in datos["lines"]] == ["952", "653", "1903"] and datos["total"] == 187000


def test_quitar_un_analisis_respalda_guarda_y_deja_traza(base):
    r = _cliente().post("/api/dashboard/order-line-delete", json={"request_id": "req-1", "index": 2, "code": "1903"})
    assert r.status_code == 200 and r.get_json()["total"] == 135000
    assert _hechos(base) == ["respaldo", "guardar", "evento"]
    _, perfil, texto = base["pasos"][1]
    assert perfil["added_tests"] == [] and texto == "Perfil Toxicológico, Perfil Renal"
    assert base["pasos"][0][2]["perfil_antes"] == CON_PERFILES, "el respaldo permite volver atrás"
    assert base["pasos"][2][1] == "dashboard_line_removed"


def test_si_la_orden_cambio_desde_que_se_abrio_la_lista_no_se_quita_otra_linea(base):
    r = _cliente().post("/api/dashboard/order-line-delete", json={"request_id": "req-1", "index": 1, "code": "1903"})
    assert r.status_code == 409 and "recarga" in r.get_json()["error"] and base["pasos"] == []


def test_el_unico_analisis_no_se_quita(base, monkeypatch):
    solo = dict(CON_PERFILES, extra_profiles=[], added_tests=[])
    monkeypatch.setattr(dashboard_ordenes.ordenes_db, "evento_creacion",
                        lambda rid: {"id": "ev-1", "event_payload": {"profile": solo}})
    r = _cliente().post("/api/dashboard/order-line-delete", json={"request_id": "req-1", "index": 0, "code": "952"})
    assert r.status_code == 400 and "elimina la orden" in r.get_json()["error"] and base["pasos"] == []


# ── Quién puede ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("perfil,puede", [("recepcion", True), ("digitacion", True), ("administrador", True),
                                          ("procesamiento", False), ("auxiliar_administrativa", False)])
def test_solo_quien_gestiona_ordenes_elimina(base, perfil, puede):
    r = _cliente(perfil).post("/api/dashboard/order-delete", json={"request_id": "req-1"})
    assert (r.status_code == 200) is puede
    if not puede:
        assert r.status_code == 403 and base["pasos"] == []


def test_quien_solo_consulta_puede_ver_las_lineas_pero_no_quitarlas(base):
    assert _cliente("procesamiento").get("/api/dashboard/order-lines?request_id=req-1").status_code == 200
    r = _cliente("procesamiento").post("/api/dashboard/order-line-delete",
                                       json={"request_id": "req-1", "index": 2, "code": "1903"})
    assert r.status_code == 403


def test_sin_sesion_no_se_llega(base):
    app.config["TESTING"] = True
    r = app.test_client().post("/api/dashboard/order-delete", json={"request_id": "req-1"})
    assert r.status_code in (301, 302, 401) and base["pasos"] == []
