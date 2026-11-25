"""Emisión automática «según confirmación del pedido» (decisión 017, 2026-11-25).

A3: «quedó para manualmente, uno a uno, generar la factura», cuando la propuesta del 28/09
decía «pasar de borrador a factura emitida según confirmación del pedido». Se emite solo lo
que el cliente confirmó; lo demás queda en borrador. Doble interruptor, apagado por defecto.
"""
import pytest

from app import emision, emision_automatica as auto, facturar_pedido, pagos
from app.services import wompi
from tests.test_pagos_wompi import SECRETO, _evento

PEDIDO = {"id": "ped-1", "pedido_number": "P-2026-030", "status": "facturado",
          "alegra_invoice_id": "8812", "payment_method": "contraentrega"}


@pytest.fixture
def mundo(monkeypatch):
    estado = {"pedido": dict(PEDIDO), "pago": None, "emitidos": [], "alertas": [], "respuesta": {"ok": True, "numero": "FE-120"}}
    monkeypatch.setattr(emision, "ALEGRA_ENABLED", True)
    monkeypatch.setattr(emision, "ALEGRA_EMISSION_ENABLED", True)
    monkeypatch.setattr(auto.config, "ALEGRA_AUTO_EMISSION", True)
    monkeypatch.setattr(auto.db, "get_pedido", lambda pid: dict(estado["pedido"]))
    monkeypatch.setattr(auto.pagos_db, "por_pedidos",
                        lambda ids: {"ped-1": estado["pago"]} if estado["pago"] else {})
    monkeypatch.setattr(auto.emision, "emitir",
                        lambda pedido: estado["emitidos"].append(pedido["id"]) or dict(estado["respuesta"]))
    monkeypatch.setattr(auto, "notify_error", lambda *a: estado["alertas"].append(a))
    return estado


# ── Qué se emite y qué no ───────────────────────────────────────────────────

def test_contraentrega_con_borrador_se_emite(mundo):
    assert auto.intentar("ped-1", "borrador armado")["ok"] is True
    assert mundo["emitidos"] == ["ped-1"]


def test_pago_en_linea_sin_pagar_queda_en_borrador(mundo):
    mundo["pedido"]["payment_method"] = "pago_linea"
    mundo["pago"] = {"status": "pending"}
    assert auto.intentar("ped-1", "borrador armado") is None and mundo["emitidos"] == []


def test_pago_en_linea_aprobado_se_emite(mundo):
    mundo["pedido"]["payment_method"] = "pago_linea"
    mundo["pago"] = {"status": "approved"}
    auto.intentar("ped-1", "pago aprobado en Wompi")
    assert mundo["emitidos"] == ["ped-1"]


@pytest.mark.parametrize("forma", [None, "", "otra"])
def test_sin_forma_de_pago_confirmada_queda_en_borrador(mundo, forma):
    """El pedido cerrado por inactividad no tiene forma de pago: A3 lo revisa antes."""
    mundo["pedido"]["payment_method"] = forma
    assert auto.intentar("ped-1", "borrador armado") is None and mundo["emitidos"] == []


def test_sin_borrador_no_emite(mundo):
    mundo["pedido"].update(status="cerrado", alegra_invoice_id=None)
    assert auto.intentar("ped-1", "borrador armado") is None and mundo["emitidos"] == []


# ── Interruptores ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("variable, modulo", [("ALEGRA_AUTO_EMISSION", "config"),
                                              ("ALEGRA_EMISSION_ENABLED", "emision"),
                                              ("ALEGRA_ENABLED", "emision")])
def test_cualquier_interruptor_apagado_no_emite_nada(mundo, monkeypatch, variable, modulo):
    monkeypatch.setattr(auto.config if modulo == "config" else emision, variable, False)
    assert auto.activa() is False
    assert auto.intentar("ped-1", "borrador armado") is None and mundo["emitidos"] == []


def test_apagada_ni_siquiera_lanza_el_hilo(mundo, monkeypatch):
    monkeypatch.setattr(auto.config, "ALEGRA_AUTO_EMISSION", False)
    monkeypatch.setattr(auto.threading, "Thread", lambda *a, **k: pytest.fail("no debía lanzar"))
    auto.programar("ped-1", "borrador armado")


def test_nace_apagada():
    """Sin la variable queda apagada, y render.yaml la despliega en false."""
    import inspect
    from app import config
    assert 'os.environ.get("ALEGRA_AUTO_EMISSION", "false")' in inspect.getsource(config)
    texto = open("render.yaml", encoding="utf-8").read()
    assert 'value: "false"' in texto[texto.index("key: ALEGRA_AUTO_EMISSION"):][:80]


# ── Si Alegra no emite ───────────────────────────────────────────────────────

def test_si_alegra_rechaza_queda_en_borrador_y_avisa(mundo):
    mundo["respuesta"] = {"ok": False, "error": "Alegra no emitió la factura: resolución vencida"}
    assert auto.intentar("ped-1", "borrador armado")["ok"] is False
    assert len(mundo["alertas"]) == 1 and "P-2026-030" in mundo["alertas"][0][2]


def test_nunca_lanza(mundo, monkeypatch):
    def explota(pid):
        raise RuntimeError("base caída")
    monkeypatch.setattr(auto.db, "get_pedido", explota)
    assert auto.intentar("ped-1", "borrador armado")["ok"] is False
    assert mundo["alertas"]


# ── Dónde se engancha ────────────────────────────────────────────────────────

def test_al_armar_el_borrador_se_programa_la_emision(monkeypatch):
    llamados = []
    monkeypatch.setattr(facturar_pedido.emision_automatica, "programar", lambda pid, origen: llamados.append(pid))
    monkeypatch.setattr(facturar_pedido.db, "list_pedido_requests", lambda pid: [{"id": "r1", "patient_name": "Leon"}])
    monkeypatch.setattr(facturar_pedido.db, "get_pedido_profiles",
                        lambda pid, con_request_id=False: [("r1", {"total_estimated": 12000})])
    monkeypatch.setattr(facturar_pedido.billing, "build_invoice_lines", lambda perfil, paciente: [{"x": 1}])
    monkeypatch.setattr(facturar_pedido.db, "get_client_by_id", lambda cid: {"tax_id": "900", "clinic_name": "Vet"})
    monkeypatch.setattr(facturar_pedido.billing, "invoice_order", lambda *a, **k: {"invoice_id": 8812, "number": "8812"})
    monkeypatch.setattr(facturar_pedido.db, "mark_pedido_invoiced", lambda pid, fid: None)
    assert facturar_pedido.facturar({"id": "ped-1", "client_id": "c1"})["status"] == "facturado"
    assert llamados == ["ped-1"]


def test_si_el_borrador_falla_no_se_programa_nada(monkeypatch):
    llamados = []
    monkeypatch.setattr(facturar_pedido.emision_automatica, "programar", lambda pid, origen: llamados.append(pid))
    monkeypatch.setattr(facturar_pedido.db, "list_pedido_requests", lambda pid: [])
    monkeypatch.setattr(facturar_pedido.db, "get_pedido_profiles", lambda pid, con_request_id=False: [])
    monkeypatch.setattr(facturar_pedido.db, "create_request_event", lambda *a: None)
    assert facturar_pedido.facturar({"id": "ped-1"})["status"] == "cerrado"
    assert llamados == []


def test_al_aprobarse_el_pago_en_wompi_se_programa_la_emision(monkeypatch):
    llamados = []
    pago = {"id": "pg-1", "pedido_id": "ped-1", "payment_link_id": "L1", "amount_in_cents": 7134000,
            "status": "pending", "url": "https://checkout.wompi.co/l/L1"}
    monkeypatch.setattr(wompi, "WOMPI_EVENTS_SECRET", SECRETO)
    monkeypatch.setattr(pagos.pagos_db, "por_link", lambda l: pago)
    monkeypatch.setattr(pagos.pagos_db, "actualizar", lambda *a: None)
    monkeypatch.setattr(pagos.db, "get_pedido", lambda pid: {"id": "ped-1", "pedido_number": "P-2026-030"})
    monkeypatch.setattr(pagos, "_avisar", lambda *a: None)
    monkeypatch.setattr(pagos.emision_automatica, "programar", lambda pid, origen: llamados.append(pid))
    assert pagos.procesar_evento(_evento()) == "approved"
    assert llamados == ["ped-1"]
    assert pagos.procesar_evento(_evento("DECLINED")) == "declined"
    assert llamados == ["ped-1"]  # un rechazo no emite nada
