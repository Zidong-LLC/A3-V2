"""Cobro de un pedido (2026-11-16): el estado del pago en línea en Pedidos, el link de pago
para lo que no entra por el chat, la emisión ante la DIAN (apagada por defecto) y que el
motivo de un borrador fallido quede escrito.

La emisión es lo delicado: una factura emitida no se deshace. Los tests cuidan que no pueda
salir sola, sin la variable, sin permiso, ni sobre algo que no sea un borrador revisable.
"""
import logging
from unittest.mock import MagicMock, patch

import pytest

from app import billing, dashboard_cobro, emision, facturar_pedido, pedido_directo, pedidos_vista
from app.main import app
from app.services import alegra, chatwoot, pagos_db


def _cliente(perfil="administrador"):
    app.config["TESTING"] = True
    c = app.test_client()
    with c.session_transaction() as s:
        s.update({"dashboard_authenticated": True, "dashboard_username": "ana", "dashboard_role": perfil})
    return c


# ── Estado del pago en el encabezado del pedido ─────────────────────────────

def _vista(pedido, pagos=None, facturas=None):
    base = {"id": "p1", "status": "cerrado", "created_at": "2026-11-16", "entry_channel": "portal"}
    return pedidos_vista.agrupar([{**base, **pedido}], [], pagos, facturas)["pedidos"][0]


def test_el_pedido_muestra_como_va_su_pago_en_linea():
    aprobado = _vista({"payment_method": "pago_linea"},
                      {"p1": {"status": "approved", "amount_in_cents": 1600000, "url": "https://x/l/1"}})
    assert aprobado["pago"] == {"estado": "approved", "texto": "Pagado en línea", "monto": 16000, "url": None}
    pendiente = _vista({"payment_method": "pago_linea"},
                       {"p1": {"status": "pending", "amount_in_cents": 4800000, "url": "https://x/l/2"}})
    assert pendiente["pago"]["texto"] == "Link enviado, sin pagar" and pendiente["pago"]["url"] == "https://x/l/2"


def test_pago_en_linea_sin_link_se_ve_y_contraentrega_no_muestra_nada():
    assert _vista({"payment_method": "pago_linea"})["pago"]["estado"] == "sin_link"
    assert _vista({"payment_method": "contraentrega"})["pago"] is None
    assert _vista({"payment_method": "pago_linea", "status": "abierto"})["pago"] is None, "el link nace al cerrar"


def test_el_pedido_sabe_si_su_factura_ya_fue_emitida():
    borrador = _vista({"status": "facturado", "alegra_invoice_id": 77}, facturas={"77": {"status": "draft"}})
    assert borrador["emitida"] is False and borrador["factura_numero"] is None
    emitida = _vista({"status": "facturado", "alegra_invoice_id": 77},
                     facturas={"77": {"status": "open", "number": "FE-120", "is_stamped": True}})
    assert emitida["emitida"] is True and emitida["factura_numero"] == "FE-120"
    assert _vista({"status": "facturado", "alegra_invoice_id": 78})["emitida"] is False, "sin caché: borrador"


def test_entre_varios_links_manda_el_aprobado_y_si_no_el_ultimo(monkeypatch):
    filas = [{"pedido_id": "p1", "status": "declined", "created_at": "1"},
             {"pedido_id": "p1", "status": "approved", "created_at": "2"},
             {"pedido_id": "p1", "status": "pending", "created_at": "3"},
             {"pedido_id": "p2", "status": "declined", "created_at": "1"},
             {"pedido_id": "p2", "status": "pending", "created_at": "2"}]
    tabla = MagicMock()
    tabla.select.return_value.in_.return_value.order.return_value.execute.return_value = MagicMock(data=filas)
    monkeypatch.setattr(pagos_db._client, "table", lambda nombre: tabla)
    ultimo = pagos_db.por_pedidos(["p1", "p2"])
    assert ultimo["p1"]["status"] == "approved" and ultimo["p2"]["status"] == "pending"
    assert pagos_db.por_pedidos([None, ""]) == {}


# ── Link de pago para el portal y «Nueva Orden» ─────────────────────────────

def _registrar(monkeypatch, forma):
    monkeypatch.setattr(pedido_directo.db, "create_pedido", lambda *a, **k: {"id": "ped-1", "pedido_number": "P-1"})
    monkeypatch.setattr(pedido_directo.db, "close_pedido", lambda *a, **k: None)
    monkeypatch.setattr(pedido_directo.config, "ALEGRA_ENABLED", False)
    creada = {"request_id": "r1", "order_number": "A3-1", "event_payload": {"profile": {"total_estimated": 48000}}}
    with patch.object(pedido_directo.db, "create_request", return_value=creada), \
         patch.object(pedido_directo.pagos, "link_para_pedido", return_value="https://checkout/l/9") as link:
        r = pedido_directo.registrar(client_id="c1", chat_id="portal:c1", canal_pedido="portal",
                                     session={"client_id": "c1"},
                                     fields={"payment_method": forma, "clinic_name": "Vet Demo"})
    return r, link


def test_una_orden_del_portal_con_pago_en_linea_nace_con_su_link(monkeypatch):
    r, link = _registrar(monkeypatch, "pago_linea")
    link.assert_called_once_with("ped-1", 48000, "Vet Demo")
    assert r["pago_url"] == "https://checkout/l/9"


def test_contraentrega_no_pide_link(monkeypatch):
    r, link = _registrar(monkeypatch, "contraentrega")
    assert not link.called and r["pago_url"] is None


@pytest.fixture
def cobro(monkeypatch):
    estado = {"pedido": {"id": "p1", "status": "cerrado", "client_id": "c1"}, "pago": None, "creados": []}
    monkeypatch.setattr(dashboard_cobro.db, "get_pedido", lambda pid: estado["pedido"] if pid == "p1" else None)
    monkeypatch.setattr(dashboard_cobro.db, "get_pedido_profiles",
                        lambda pid: [{"total_estimated": 16000}, {"total_estimated": 24000}])
    monkeypatch.setattr(dashboard_cobro.db, "get_client_by_id", lambda cid: {"clinic_name": "Vet Demo"})
    monkeypatch.setattr(dashboard_cobro.pagos_db, "por_pedidos",
                        lambda ids: {"p1": estado["pago"]} if estado["pago"] else {})
    monkeypatch.setattr(dashboard_cobro.pagos, "link_para_pedido",
                        lambda pid, total, cliente: estado["creados"].append((pid, total, cliente)) or "https://c/l/nuevo")
    return estado


def test_generar_el_link_de_un_pedido_que_quedo_sin_el(cobro):
    r = _cliente("recepcion").post("/api/dashboard/pedido-pago-link", json={"pedido_id": "p1"})
    assert r.get_json() == {"ok": True, "url": "https://c/l/nuevo", "nuevo": True}
    assert cobro["creados"] == [("p1", 40000, "Vet Demo")], "el link es por el total del pedido"


def test_con_un_link_vigente_se_devuelve_ese_y_no_se_crea_otro(cobro):
    cobro["pago"] = {"status": "pending", "url": "https://c/l/viejo"}
    r = _cliente().post("/api/dashboard/pedido-pago-link", json={"pedido_id": "p1"})
    assert r.get_json()["url"] == "https://c/l/viejo" and cobro["creados"] == []


def test_un_pedido_pagado_o_abierto_no_recibe_otro_link(cobro):
    cobro["pago"] = {"status": "approved", "url": "x"}
    assert _cliente().post("/api/dashboard/pedido-pago-link", json={"pedido_id": "p1"}).status_code == 409
    cobro["pago"], cobro["pedido"]["status"] = None, "abierto"
    assert _cliente().post("/api/dashboard/pedido-pago-link", json={"pedido_id": "p1"}).status_code == 409
    assert _cliente().post("/api/dashboard/pedido-pago-link", json={"pedido_id": "otro"}).status_code == 404
    assert cobro["creados"] == []


def test_quien_solo_consulta_no_genera_links(cobro):
    assert _cliente("procesamiento").post("/api/dashboard/pedido-pago-link", json={"pedido_id": "p1"}).status_code == 403


# ── Emisión ante la DIAN ────────────────────────────────────────────────────

PEDIDO = {"id": "p1", "status": "facturado", "alegra_invoice_id": "8812", "pedido_number": "P-2026-020"}


@pytest.fixture
def dian(monkeypatch):
    estado = {"factura": {"id": "8812", "status": "draft", "total": 48000}, "timbradas": [], "historial": [],
              "falla": None}
    monkeypatch.setattr(emision, "ALEGRA_ENABLED", True)
    monkeypatch.setattr(emision, "ALEGRA_EMISSION_ENABLED", True)
    monkeypatch.setattr(emision.alegra, "get_invoice", lambda fid: dict(estado["factura"]))

    def _timbrar(fid):
        if estado["falla"]:
            raise alegra.AlegraError(estado["falla"])
        estado["timbradas"].append(fid)
        estado["factura"] = {"id": fid, "status": "open", "total": 48000, "numberTemplate": {"fullNumber": "FE-120"}}
        return "La factura de venta ha sido emitida exitosamente"

    monkeypatch.setattr(emision.alegra, "stamp_invoice", _timbrar)
    monkeypatch.setattr(emision.audit_db, "registrar",
                        lambda entidad, eid, accion, cambios=None: estado["historial"].append((entidad, eid, accion)))
    monkeypatch.setattr(emision.db, "marcar_factura_emitida", lambda fid, factura: None)
    monkeypatch.setattr(dashboard_cobro.db, "get_pedido", lambda pid: dict(PEDIDO) if pid == "p1" else None)
    return estado


def test_sin_la_variable_la_plataforma_no_emite_nada(dian, monkeypatch):
    monkeypatch.setattr(emision, "ALEGRA_EMISSION_ENABLED", False)
    r = emision.emitir(dict(PEDIDO))
    assert r["ok"] is False and r["codigo"] == 403 and dian["timbradas"] == []
    assert emision.activa() is False


def test_la_emision_nace_apagada_en_la_configuracion_y_en_render():
    import io
    import os
    from importlib import reload

    from app import config
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("ALEGRA_EMISSION_ENABLED", None)
        assert reload(config).ALEGRA_EMISSION_ENABLED is False
    reload(config)
    assert 'ALEGRA_EMISSION_ENABLED\n                value: "false"' in io.open("render.yaml", encoding="utf-8").read()


def test_emitir_un_borrador_revisado_lo_timbra_y_deja_quien_lo_hizo(dian):
    r = _cliente("auxiliar_administrativa").post("/api/dashboard/pedido-emitir", json={"pedido_id": "p1"})
    assert r.status_code == 200 and r.get_json()["numero"] == "FE-120"
    assert dian["timbradas"] == ["8812"] and dian["historial"] == [("invoice", "8812", "emit")]


def test_recepcion_arma_borradores_pero_no_emite(dian):
    for perfil in ("recepcion", "digitacion", "procesamiento"):
        r = _cliente(perfil).post("/api/dashboard/pedido-emitir", json={"pedido_id": "p1"})
        assert r.status_code == 403
    assert dian["timbradas"] == []


@pytest.mark.parametrize("pedido,dice", [
    ({**PEDIDO, "status": "cerrado", "alegra_invoice_id": None}, "no tiene borrador"),
    ({**PEDIDO, "alegra_invoice_id": ""}, "no tiene borrador"),
    (None, "no existe"),
])
def test_sin_borrador_no_hay_nada_que_emitir(dian, pedido, dice):
    r = emision.emitir(pedido)
    assert r["ok"] is False and dice in r["error"] and dian["timbradas"] == []


@pytest.mark.parametrize("factura,dice", [
    ({"id": "8812", "status": "open", "total": 48000}, "ya no es un borrador"),
    ({"id": "8812", "status": "void", "total": 48000}, "ya no es un borrador"),
    ({"id": "8812", "status": "draft", "total": 0}, "no tiene valor"),
])
def test_solo_se_emite_un_borrador_con_valor(dian, factura, dice):
    dian["factura"] = factura
    r = emision.emitir(dict(PEDIDO))
    assert r["ok"] is False and dice in r["error"] and dian["timbradas"] == []


def test_si_no_se_puede_leer_la_factura_no_se_emite_a_ciegas(dian, monkeypatch):
    monkeypatch.setattr(emision.alegra, "get_invoice", MagicMock(side_effect=alegra.AlegraError("red")))
    r = emision.emitir(dict(PEDIDO))
    assert r["codigo"] == 503 and dian["timbradas"] == []


def test_si_alegra_no_emite_queda_el_motivo_en_el_historial(dian):
    dian["falla"] = "La factura no se puede abrir"
    r = emision.emitir(dict(PEDIDO))
    assert r["codigo"] == 502 and "no se puede abrir" in r["error"]
    assert dian["historial"] == [("invoice", "8812", "emit_failed")]


def test_el_doble_clic_no_emite_dos_veces(dian):
    emision._EN_CURSO.add("8812")
    try:
        assert "ya se está emitiendo" in emision.emitir(dict(PEDIDO))["error"] and dian["timbradas"] == []
    finally:
        emision._EN_CURSO.discard("8812")


def test_nada_fuera_del_boton_llama_a_la_emision():
    """La única puerta es `emision.emitir`, y solo la llama la ruta del botón."""
    import pathlib
    usos = {p.name: p.read_text(encoding="utf-8").count("stamp_invoice(") for p in pathlib.Path("app").rglob("*.py")}
    assert {n for n, veces in usos.items() if veces} == {"alegra.py", "emision.py"}
    llamadas = {p.name for p in pathlib.Path("app").rglob("*.py") if "emision.emitir(" in p.read_text(encoding="utf-8")}
    assert llamadas == {"dashboard_cobro.py"}


def test_timbrar_lee_la_respuesta_de_alegra_por_factura(monkeypatch):
    cuerpos = []
    monkeypatch.setattr(alegra, "_request", lambda m, p, body=None: cuerpos.append((m, p, body)) or
                        {"data": [{"id": "8812", "success": True, "message": "emitida"}]})
    assert alegra.stamp_invoice(8812) == "emitida"
    assert cuerpos == [("POST", "/invoices/stamp", {"ids": ["8812"]})]
    monkeypatch.setattr(alegra, "_request", lambda m, p, body=None: {"data": [{"id": "8812", "success": False,
                                                                              "message": "ya esta emitida"}]})
    with pytest.raises(alegra.AlegraError, match="ya esta emitida"):
        alegra.stamp_invoice("8812")

    def _400(m, p, body=None):
        raise alegra.AlegraError('Alegra POST /invoices/stamp -> HTTP 400: {"data":[{"id":"8812","code":905,'
                                 '"message":"La factura no se puede abrir"}]}')
    monkeypatch.setattr(alegra, "_request", _400)
    with pytest.raises(alegra.AlegraError, match="^La factura no se puede abrir$"):
        alegra.stamp_invoice("8812")


# ── El borrador que falla ───────────────────────────────────────────────────

def _factura(monkeypatch, respuestas):
    cuerpos = []
    monkeypatch.setattr(alegra, "get_or_create_contact", lambda *a, **k: {"id": "7"})
    monkeypatch.setattr(alegra, "get_or_create_item", lambda ref, name, price: {"id": "i"})

    def _crear(cid, items, date, anotation=None, pago=None, **k):
        cuerpos.append({"pago": pago, "nota": anotation})
        r = respuestas[len(cuerpos) - 1]
        if isinstance(r, Exception):
            raise r
        return r
    monkeypatch.setattr(alegra, "create_invoice", _crear)
    return cuerpos


LINEA = [{"reference": "1101", "name": "Cuadro Hemático", "price": 16000, "quantity": 1}]
RECHAZO = alegra.AlegraError('Alegra POST /invoices -> HTTP 400: {"message":"medio de pago inválido"}')


def test_si_alegra_rechaza_el_medio_de_pago_el_borrador_sale_como_efectivo_con_la_nota(monkeypatch):
    cuerpos = _factura(monkeypatch, [RECHAZO, {"id": "55"}])
    r = billing.invoice_order("900123456", "Vet", LINEA, "2026-11-16", client_row={}, payment_method="pago_linea")
    assert r["invoice_id"] == "55"
    assert cuerpos[0]["pago"] == {"paymentForm": "CASH", "paymentMethod": "DEBIT_TRANSFER"}
    assert cuerpos[1]["pago"] == {"paymentMethod": "CASH", "paymentForm": "CASH"}
    assert cuerpos[1]["nota"] == "Pago en línea (Wompi)", "Contabilidad ve el medio real al revisar"


def test_un_error_de_red_no_se_reintenta_porque_la_factura_pudo_crearse(monkeypatch):
    cuerpos = _factura(monkeypatch, [alegra.AlegraError("Alegra POST /invoices -> red: timed out")])
    with pytest.raises(alegra.AlegraError):
        billing.invoice_order("900123456", "Vet", LINEA, "2026-11-16", client_row={}, payment_method="pago_linea")
    assert len(cuerpos) == 1


def test_un_rechazo_en_efectivo_no_tiene_a_que_caer(monkeypatch):
    cuerpos = _factura(monkeypatch, [RECHAZO])
    with pytest.raises(alegra.AlegraError):
        billing.invoice_order("900123456", "Vet", LINEA, "2026-11-16", client_row={}, payment_method="contraentrega")
    assert len(cuerpos) == 1


def test_el_motivo_de_un_pedido_sin_factura_queda_en_el_log_y_en_la_orden(monkeypatch, caplog):
    eventos = []
    monkeypatch.setattr(facturar_pedido.db, "list_pedido_requests", lambda pid: [{"id": "r1", "patient_name": "Lola"}])
    monkeypatch.setattr(facturar_pedido.db, "get_pedido_profiles", lambda pid, con_request_id=False: [
        ("r1", {"base_profile": {"code": "152", "name": "Perfil", "price": 24000}, "added_tests": [], "removed_tests": []})])
    monkeypatch.setattr(facturar_pedido.db, "get_client_by_id", lambda cid: {"tax_id": "900123456", "clinic_name": "Vet"})
    monkeypatch.setattr(facturar_pedido.db, "create_request_event", lambda rid, tipo, datos: eventos.append((rid, tipo, datos)))
    monkeypatch.setattr(facturar_pedido.billing, "invoice_order", MagicMock(side_effect=RECHAZO))
    with caplog.at_level(logging.WARNING, logger="app.facturar_pedido"):
        r = facturar_pedido.facturar({"id": "p1", "pedido_number": "P-2026-016", "client_id": "c1"})
    assert r["status"] == "cerrado" and "medio de pago inválido" in r["warning"]
    assert "P-2026-016 cerrado sin factura" in caplog.text
    assert eventos[0][:2] == ("r1", "alegra_failed") and "medio de pago" in eventos[0][2]["motivo"]


# ── Chatwoot: lo derivado queda abierto ─────────────────────────────────────

def test_al_derivar_la_conversacion_pasa_a_abierta_y_se_asigna_al_equipo(monkeypatch):
    llamadas = []
    monkeypatch.setattr(chatwoot, "_post", lambda ruta, cuerpo: llamadas.append((ruta, cuerpo)))
    monkeypatch.setitem(chatwoot._TEAM_MAP, "contabilidad", "3")
    chatwoot.assign_team("41", "contabilidad")
    assert llamadas == [("/conversations/41/toggle_status", {"status": "open"}),
                        ("/conversations/41/assignments", {"team_id": 3})]


def test_si_no_se_pudo_abrir_igual_se_asigna(monkeypatch):
    llamadas = []

    def _post(ruta, cuerpo):
        if "toggle_status" in ruta:
            raise RuntimeError("Chatwoot 500")
        llamadas.append(ruta)
    monkeypatch.setattr(chatwoot, "_post", _post)
    monkeypatch.setitem(chatwoot._TEAM_MAP, "contabilidad", "3")
    chatwoot.assign_team("41", "contabilidad")
    assert llamadas == ["/conversations/41/assignments"]


def test_sin_equipo_configurado_igual_queda_abierta(monkeypatch):
    llamadas = []
    monkeypatch.setattr(chatwoot, "_post", lambda ruta, cuerpo: llamadas.append(ruta))
    monkeypatch.setitem(chatwoot._TEAM_MAP, "tecnico", "")
    chatwoot.assign_team("41", "tecnico")
    assert llamadas == ["/conversations/41/toggle_status"]


# ── Lo que se ve en la pantalla de Pedidos ──────────────────────────────────

def _pedidos_html(rol, emision_activa, emitida=False):
    from tests.test_dashboard import _base_context

    pedidos = [{"id": "p1", "pedido_number": "P-2026-020", "status": "facturado", "alegra_invoice_id": "8812",
                "created_at": "2026-11-16", "client_name": "Vet A", "orders": [], "orders_count": 0,
                "entry_channel": "portal", "payment_method": "pago_linea"}]
    facturas = {"8812": {"status": "open", "number": "FE-120", "is_stamped": True}} if emitida else {}
    contexto = _base_context(requests=[], couriers_options=[], request_status_options=[])
    with patch("app.dashboard.build_dashboard_context", return_value=contexto), \
         patch("app.dashboard.db.list_pedidos_for_dashboard", return_value=pedidos), \
         patch("app.dashboard.pagos_db.por_pedidos",
               return_value={"p1": {"status": "pending", "amount_in_cents": 4800000, "url": "https://c/l/1"}}), \
         patch("app.dashboard.db.facturas_de_pedidos", return_value=facturas), \
         patch("app.dashboard.emision.activa", return_value=emision_activa):
        return _cliente(rol).get("/pedidos").get_data(as_text=True)


def test_pedidos_muestra_el_pago_pendiente_y_deja_copiar_el_link():
    html = _pedidos_html("recepcion", False)
    assert "Link enviado, sin pagar" in html and "$48.000" in html
    assert 'data-pago-link="p1"' in html and "Copiar link de pago" in html


def test_con_la_emision_apagada_nadie_ve_el_boton_de_emitir():
    assert "data-pedido-emitir=" not in _pedidos_html("administrador", False)


def test_con_la_emision_encendida_solo_facturacion_ve_el_boton():
    assert 'data-pedido-emitir="p1"' in _pedidos_html("administrador", True)
    assert 'data-pedido-emitir="p1"' in _pedidos_html("auxiliar_administrativa", True)
    assert "data-pedido-emitir=" not in _pedidos_html("recepcion", True)


def test_una_factura_ya_emitida_no_ofrece_emitirla_otra_vez():
    html = _pedidos_html("administrador", True, emitida=True)
    assert "Factura emitida FE-120" in html and "data-pedido-emitir=" not in html
