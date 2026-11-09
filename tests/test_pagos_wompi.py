"""Pago en línea por pedido con Wompi (propuesta del 28/09): link de un solo uso por el
total, webhook con firma, estados sin repetir avisos y cierre intacto si está apagado."""
import hashlib
from unittest.mock import patch

import pytest

from app import agent, main, pagos
from app.services import wompi

SECRETO = "test_events_abc"
PEDIDO = {"id": "ped-1", "pedido_number": "P-2026-009", "external_chat_id": "7", "entry_channel": "whatsapp"}


def _evento(estado="APPROVED", monto=7134000, link="L1", secreto=SECRETO):
    tx = {"id": "tx-1", "status": estado, "amount_in_cents": monto, "payment_link_id": link}
    props = ["transaction.id", "transaction.status", "transaction.amount_in_cents"]
    cadena = f"{tx['id']}{estado}{monto}1700000000{secreto}"
    return {"event": "transaction.updated", "data": {"transaction": tx}, "timestamp": 1700000000,
            "signature": {"properties": props, "checksum": hashlib.sha256(cadena.encode()).hexdigest().upper()}}


@pytest.fixture
def mundo(monkeypatch):
    estado = {"pago": {"id": "pg-1", "pedido_id": "ped-1", "payment_link_id": "L1", "amount_in_cents": 7134000,
                       "status": "pending", "url": "https://checkout.wompi.co/l/L1"},
              "mensajes": [], "notas": [], "cambios": []}
    monkeypatch.setattr(wompi, "WOMPI_EVENTS_SECRET", SECRETO)
    monkeypatch.setattr(pagos.pagos_db, "por_link", lambda l: estado["pago"] if l == "L1" else None)

    def actualizar(pid, est, tx, crudo):
        estado["cambios"].append(est)
        estado["pago"]["status"] = est

    monkeypatch.setattr(pagos.pagos_db, "actualizar", actualizar)
    monkeypatch.setattr(pagos.db, "get_pedido", lambda pid: PEDIDO)
    monkeypatch.setattr(pagos.db, "save_message", lambda *a: None)
    monkeypatch.setattr(pagos.chatwoot, "send_message", lambda c, t: estado["mensajes"].append(t))
    monkeypatch.setattr(pagos.chatwoot, "send_private_note", lambda c, t: estado["notas"].append(t))
    return estado


def test_pago_aprobado_actualiza_y_avisa_al_cliente_y_a_contabilidad(mundo):
    assert pagos.procesar_evento(_evento()) == "approved"
    assert mundo["cambios"] == ["approved"]
    assert "P-2026-009" in mundo["mensajes"][0] and "$71.340" in mundo["mensajes"][0]
    assert "APROBADO" in mundo["notas"][0] and "tx-1" in mundo["notas"][0]


def test_el_reintento_de_wompi_no_avisa_dos_veces(mundo):
    pagos.procesar_evento(_evento())
    assert pagos.procesar_evento(_evento()) == "repetido"
    assert len(mundo["mensajes"]) == 1


def test_firma_invalida_no_toca_nada(mundo):
    assert pagos.procesar_evento(_evento(secreto="otro")) == "firma_invalida"
    assert mundo["cambios"] == [] and mundo["mensajes"] == []


def test_monto_distinto_no_se_da_por_pagado(mundo):
    with patch.object(pagos, "notify_error") as aviso:
        assert pagos.procesar_evento(_evento(monto=100)) == "monto_distinto"
    assert mundo["cambios"] == ["mismatch"] and mundo["mensajes"] == [] and aviso.call_count == 1


def test_pago_rechazado_ofrece_el_mismo_enlace(mundo):
    assert pagos.procesar_evento(_evento("DECLINED")) == "declined"
    assert "https://checkout.wompi.co/l/L1" in mundo["mensajes"][0]


def test_link_desconocido_y_otros_eventos_se_ignoran(mundo):
    assert pagos.procesar_evento(_evento(link="X9")) == "desconocido"
    assert pagos.procesar_evento({"event": "nequi_token.updated"}) == "ignorado"


def test_webhook_responde_200_o_401(mundo):
    main.app.config["TESTING"] = True
    c = main.app.test_client()
    assert c.post("/webhooks/wompi", json=_evento()).status_code == 200
    assert c.post("/webhooks/wompi", json=_evento(secreto="otro")).status_code == 401
    assert c.post("/webhooks/wompi", data="x").status_code == 400


def test_crear_link_es_de_un_solo_uso_por_el_monto_exacto(monkeypatch):
    monkeypatch.setattr(wompi, "WOMPI_PRIVATE_KEY", "prv_test_x")
    enviado = {}

    class Resp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b'{"data": {"id": "3Z0Cfi"}}'

    def abrir(req, timeout=0):
        import json
        enviado.update(json.loads(req.data), auth=req.headers["Authorization"], url=req.full_url)
        return Resp()

    monkeypatch.setattr(wompi.urllib.request, "urlopen", abrir)
    link = wompi.crear_link("A3 · P-1", "desc", 7134000)
    assert link == {"id": "3Z0Cfi", "url": "https://checkout.wompi.co/l/3Z0Cfi"}
    assert enviado["single_use"] is True and enviado["amount_in_cents"] == 7134000 and enviado["currency"] == "COP"
    assert enviado["auth"] == "Bearer prv_test_x" and enviado["url"].endswith("/payment_links")


def test_apagado_no_crea_link(monkeypatch):
    monkeypatch.setattr(pagos, "WOMPI_ENABLED", False)
    with patch.object(pagos.wompi, "crear_link") as crear:
        assert pagos.link_para_pedido("ped-1", 71340) is None
    assert crear.call_count == 0


def test_si_wompi_falla_el_pedido_se_cierra_igual_y_avisa(monkeypatch):
    monkeypatch.setattr(pagos, "WOMPI_ENABLED", True)
    monkeypatch.setattr(pagos.db, "get_pedido", lambda pid: PEDIDO)
    monkeypatch.setattr(pagos.wompi, "crear_link", lambda *a: (_ for _ in ()).throw(wompi.WompiError("caído")))
    with patch.object(pagos, "notify_error") as aviso:
        assert pagos.link_para_pedido("ped-1", 71340) is None
    assert aviso.call_count == 1


# ── Cierre del pedido ───────────────────────────────────────────────────────────────

FIELDS = {"_pedido_id": "ped-1", "clinic_name": "Vet Norte", "tax_id": "900",
          "_pedido_ordenes": [{"order_number": "A3-1", "patient_name": "Coco", "total": 71340}]}


def _cerrar(monkeypatch, metodo, enlace):
    monkeypatch.setattr(agent, "ALEGRA_ENABLED", False)
    monkeypatch.setattr(agent.db, "close_pedido", lambda *a: None)
    monkeypatch.setattr(agent.db, "list_pedido_requests", lambda pid: [{}])
    llamadas = []
    monkeypatch.setattr(agent.pagos, "link_para_pedido", lambda pid, total, cli="", nit=None: llamadas.append((pid, total)) or enlace)
    return agent._close_pedido_turn({}, dict(FIELDS), metodo)["reply"], llamadas


def test_pago_en_linea_manda_el_link_por_el_total(monkeypatch):
    reply, llamadas = _cerrar(monkeypatch, "pago_linea", "https://checkout.wompi.co/l/L1")
    assert llamadas == [("ped-1", 71340)]
    assert "https://checkout.wompi.co/l/L1" in reply and "TOTAL DEL PEDIDO: $71.340" in reply


def test_contraentrega_no_pide_link(monkeypatch):
    reply, llamadas = _cerrar(monkeypatch, "contraentrega", "https://x")
    assert llamadas == [] and reply.endswith("Quedamos atentos. 🙂")


def test_sin_link_el_cierre_queda_como_antes(monkeypatch):
    reply, _ = _cerrar(monkeypatch, "pago_linea", None)
    assert reply.endswith("Quedamos atentos. 🙂")


def test_modo_prueba_solo_da_link_al_cliente_de_prueba(monkeypatch):
    monkeypatch.setattr(pagos, "WOMPI_ENABLED", True)
    monkeypatch.setattr(pagos, "WOMPI_ONLY_NITS", {"900296338"})
    monkeypatch.setattr(pagos.db, "get_pedido", lambda pid: PEDIDO)
    creados = []
    monkeypatch.setattr(pagos.pagos_db, "crear", lambda *a: creados.append(a))
    monkeypatch.setattr(pagos.wompi, "crear_link", lambda *a: {"id": "L9", "url": "https://checkout.wompi.co/l/L9"})
    assert pagos.link_para_pedido("ped-1", 71340, "Vet Real", "800111222-1") is None and creados == []
    assert pagos.link_para_pedido("ped-1", 71340, "A3", "900296338-9") == "https://checkout.wompi.co/l/L9"
    assert creados == [("ped-1", "L9", 7134000, "https://checkout.wompi.co/l/L9")]


def test_en_modo_prueba_el_nit_sale_del_cliente_del_pedido_si_el_estado_no_lo_trae(monkeypatch):
    """Prueba real del 09/11: al cerrar, el estado ya no traía el NIT y el link no salió."""
    monkeypatch.setattr(pagos, "WOMPI_ENABLED", True)
    monkeypatch.setattr(pagos, "WOMPI_ONLY_NITS", {"900296338"})
    monkeypatch.setattr(pagos.db, "get_pedido", lambda pid: dict(PEDIDO, client_id="cli-9"))
    monkeypatch.setattr(pagos.db, "get_client_by_id", lambda cid: {"tax_id": "900296338-9"} if cid == "cli-9" else None)
    monkeypatch.setattr(pagos.pagos_db, "crear", lambda *a: None)
    monkeypatch.setattr(pagos.wompi, "crear_link", lambda *a: {"id": "L9", "url": "https://checkout.wompi.co/l/L9"})
    assert pagos.link_para_pedido("ped-1", 16000, "A3", None) == "https://checkout.wompi.co/l/L9"


def test_el_resumen_dice_pago_en_linea_y_no_el_valor_interno(monkeypatch):
    reply, _ = _cerrar(monkeypatch, "pago_linea", None)
    assert "Forma de pago: pago en línea" in reply and "pago_linea" not in reply
