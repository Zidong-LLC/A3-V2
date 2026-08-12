"""
Barrido de pedidos abandonados (decisión 011).

El cliente que carga órdenes y se va sin cerrar deja el pedido abierto y sin facturar.
Decisión del usuario (2026-08-12): pasada **una hora** sin actividad, el pedido se cierra
como si hubiera terminado y se avisa a operaciones.

El disparo es oportunista —al inicio de un turno, no por cron— porque el proyecto no tiene
scheduler. Lo que estos tests fijan es que ese disparo no pueda hacer daño: que se
autolimite, que no explote nunca y que avise siempre.
"""
from unittest.mock import MagicMock

import pytest

from app import agent


PEDIDO_VIEJO = {"id": "ped-1", "pedido_number": "P-2026-001", "status": "abierto",
                "external_chat_id": "chat-9", "payment_method": None}


@pytest.fixture(autouse=True)
def sin_memoria_de_barrido():
    """El limitador es estado de módulo: se limpia entre tests."""
    agent._ultimo_barrido.clear()
    yield
    agent._ultimo_barrido.clear()


def test_cierra_el_pedido_abandonado(monkeypatch):
    cerrados = []
    monkeypatch.setattr(agent.db, "list_stale_pedidos", lambda horas=1, limit=20: [PEDIDO_VIEJO])
    monkeypatch.setattr(agent.db, "list_pedido_requests", lambda pid: [{"order_number": "A3-1"}])
    monkeypatch.setattr(agent.db, "close_pedido", lambda pid, pago=None: cerrados.append(pid))

    agent._sweep_stale_pedidos()
    assert cerrados == ["ped-1"]


def test_avisa_a_operaciones_con_el_numero_y_las_ordenes(monkeypatch, caplog):
    """Operaciones tiene que enterarse: el cliente nunca confirmó el cierre."""
    monkeypatch.setattr(agent.db, "list_stale_pedidos", lambda horas=1, limit=20: [PEDIDO_VIEJO])
    monkeypatch.setattr(agent.db, "list_pedido_requests", lambda pid: [{"o": 1}, {"o": 2}])
    monkeypatch.setattr(agent.db, "close_pedido", lambda pid, pago=None: None)

    with caplog.at_level("WARNING"):
        agent._sweep_stale_pedidos()
    mensaje = caplog.text
    assert "P-2026-001" in mensaje
    assert "operaciones" in mensaje.lower()
    assert "2 orden" in mensaje


def test_no_barre_dos_veces_seguidas(monkeypatch):
    """Se autolimita: si corriera en cada mensaje sería una consulta por turno."""
    llamadas = []
    monkeypatch.setattr(agent.db, "list_stale_pedidos",
                        lambda horas=1, limit=20: llamadas.append(1) or [])
    agent._sweep_stale_pedidos()
    agent._sweep_stale_pedidos()
    agent._sweep_stale_pedidos()
    assert len(llamadas) == 1


def test_un_fallo_de_la_base_no_tumba_el_turno(monkeypatch):
    """Está en el camino de un cliente que escribe: no puede lanzar nunca."""
    def _explota(*_a, **_k):
        raise RuntimeError("supabase caído")

    monkeypatch.setattr(agent.db, "list_stale_pedidos", _explota)
    agent._sweep_stale_pedidos()  # no debe lanzar


def test_un_pedido_que_falla_no_frena_a_los_demas(monkeypatch):
    otro = dict(PEDIDO_VIEJO, id="ped-2", pedido_number="P-2026-002")
    cerrados = []

    def _close(pid, pago=None):
        if pid == "ped-1":
            raise RuntimeError("error puntual")
        cerrados.append(pid)

    monkeypatch.setattr(agent.db, "list_stale_pedidos", lambda horas=1, limit=20: [PEDIDO_VIEJO, otro])
    monkeypatch.setattr(agent.db, "list_pedido_requests", lambda pid: [])
    monkeypatch.setattr(agent.db, "close_pedido", _close)

    agent._sweep_stale_pedidos()
    assert cerrados == ["ped-2"], "el fallo de uno no puede dejar sin cerrar a los siguientes"


def test_la_consulta_pide_solo_abiertos_y_viejos(monkeypatch):
    """Contrato de `list_stale_pedidos`: status abierto + updated_at anterior al corte."""
    from app.services import db

    registro = {}

    class _Q:
        def select(self, *_a, **_k): return self
        def eq(self, c, v): registro[c] = v; return self
        def lt(self, c, v): registro["lt"] = (c, v); return self
        def order(self, *_a, **_k): return self
        def limit(self, *_a, **_k): return self
        def execute(self): return MagicMock(data=[])

    monkeypatch.setattr(db._client, "table", lambda _n: _Q())
    db.list_stale_pedidos(horas=1)
    assert registro.get("status") == "abierto"
    assert registro.get("lt", (None,))[0] == "updated_at"
