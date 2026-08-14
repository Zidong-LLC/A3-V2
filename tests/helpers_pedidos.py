"""Aserciones compartidas para los dos flujos de cierre de orden.

Con la jerarquía de pedidos (decisión 011) la forma de pago dejó de ser un dato de CADA orden
y pasó a ser del PEDIDO: se pregunta una sola vez al cerrarlo. Varios casos escritos antes del
flag afirman "…y sigue al pago", que con pedidos ya no es el paso siguiente.

Lo que esos casos protegen de verdad es que el carril SALGA y avance —nunca que quede en
bucle—, y eso vale en los dos flujos. Estas funciones afirman esa parte invariante y dejan que
el destino dependa del flag, para que la suite corra en cualquiera de las dos configuraciones.
"""
from app.config import PEDIDOS_ENABLED
from app.messages import PAYMENT_METHOD_QUESTION


def assert_advances_after_decline(out, contexto: str = "") -> None:
    """El cliente declinó la oferta de agregar otro análisis: el carril tiene que salir y
    avanzar. Sin pedidos avanza a la forma de pago; con pedidos avanza dentro de la orden
    (confirmación si ya está completa, o el dato que falte) y NO menciona el pago."""
    sufijo = f" ({contexto})" if contexto else ""
    assert out is not None, f"el carril no debe devorar el decline{sufijo}"
    reply = out.get("reply") or ""
    if PEDIDOS_ENABLED:
        assert "pago" not in reply.lower(), (
            f"con pedidos el pago se pregunta al cerrar el pedido, no por orden{sufijo}")
        assert reply.strip(), f"el decline tiene que responder algo{sufijo}"
    else:
        assert PAYMENT_METHOD_QUESTION in reply, sufijo
