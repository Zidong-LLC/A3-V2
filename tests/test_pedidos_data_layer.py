"""
Capa de datos de PEDIDOS (decisión 011).

El pedido agrupa las órdenes de una sesión de carga y es la unidad que se factura. Estos
tests fijan el contrato de la capa de datos y —lo más importante— el invariante de
retrocompatibilidad: sin `pedido_id`, `create_request` se comporta exactamente como antes,
porque las órdenes del portal y las históricas no tienen pedido.
"""
from unittest.mock import MagicMock

import pytest

from app.services import db


class _TablaFalsa:
    """Mock de infraestructura: registra lo que se le manda a Supabase."""

    def __init__(self, registro, nombre, respuesta):
        self.registro, self.nombre, self.respuesta = registro, nombre, respuesta
        self.filtros = {}

    def insert(self, payload):
        self.registro.append((self.nombre, "insert", payload))
        return self

    def update(self, payload):
        self.registro.append((self.nombre, "update", payload))
        return self

    def select(self, *_a, **_k):
        return self

    def eq(self, campo, valor):
        self.filtros[campo] = valor
        return self

    def order(self, *_a, **_k):
        return self

    def limit(self, *_a, **_k):
        return self

    def execute(self):
        return MagicMock(data=self.respuesta)


@pytest.fixture
def supabase(monkeypatch):
    registro = []
    respuestas = {
        "pedidos": [{"id": "ped-1", "pedido_number": "P-2026-001", "status": "abierto"}],
        "requests": [{"id": "req-1", "order_number": "A3-2026-001"}],
        "request_events": [{}],
    }

    def _table(nombre):
        return _TablaFalsa(registro, nombre, respuestas.get(nombre, []))

    monkeypatch.setattr(db._client, "table", _table)
    return registro


def _payload(registro, tabla, accion):
    return [p for (t, a, p) in registro if t == tabla and a == accion]


def test_create_pedido_devuelve_numero_legible(supabase):
    pedido = db.create_pedido("cli-1", "chat-9", "telegram")
    assert pedido == {"id": "ped-1", "pedido_number": "P-2026-001"}
    enviado = _payload(supabase, "pedidos", "insert")[0]
    assert enviado["status"] == "abierto"
    assert enviado["external_chat_id"] == "chat-9"


def test_close_pedido_guarda_la_forma_de_pago(supabase):
    """La forma de pago es del PEDIDO: se registra al cerrarlo, una sola vez."""
    db.close_pedido("ped-1", "contraentrega")
    enviado = _payload(supabase, "pedidos", "update")[0]
    assert enviado["status"] == "cerrado"
    assert enviado["payment_method"] == "contraentrega"
    assert enviado["closed_at"]


def test_cerrar_y_facturar_son_dos_pasos(supabase):
    """Un pedido puede quedar cerrado y SIN facturar si Alegra falla: tiene que verse."""
    db.close_pedido("ped-1")
    assert _payload(supabase, "pedidos", "update")[0]["status"] == "cerrado"
    supabase.clear()
    db.mark_pedido_invoiced("ped-1", "inv-77")
    marcado = _payload(supabase, "pedidos", "update")[0]
    assert marcado["status"] == "facturado"
    assert marcado["alegra_invoice_id"] == "inv-77"


def test_create_request_sin_pedido_no_manda_la_columna(supabase):
    """INVARIANTE de retrocompatibilidad: sin pedido, el INSERT es el de siempre."""
    ai = {"intent": "route_scheduling", "captured_fields": {}}
    db.create_request("chat-9", {"client_id": None}, ai)
    enviado = _payload(supabase, "requests", "insert")[0]
    assert "pedido_id" not in enviado


def test_create_request_con_pedido_lo_asocia(supabase):
    ai = {"intent": "route_scheduling", "captured_fields": {}}
    db.create_request("chat-9", {"client_id": None}, ai, pedido_id="ped-1")
    enviado = _payload(supabase, "requests", "insert")[0]
    assert enviado["pedido_id"] == "ped-1"
    # Agregar una orden es actividad: sin esto el pedido parecería abandonado desde que nació.
    assert _payload(supabase, "pedidos", "update"), "no se marcó actividad en el pedido"


def test_las_funciones_toleran_id_vacio(supabase):
    """Nunca deben explotar por un id ausente: se llaman desde el cierre del turno."""
    assert db.get_open_pedido("") is None
    assert db.close_pedido("") is None
    assert db.list_pedido_requests("") == []
    db.touch_pedido("")
    db.mark_pedido_invoiced("", "inv-1")
    assert supabase == [], "no debió tocar la base con ids vacíos"
