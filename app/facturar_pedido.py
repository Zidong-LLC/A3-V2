"""Arma el BORRADOR de Alegra de un pedido ya cerrado: una factura con una línea por análisis
de cada orden (y el paciente de esa orden). Nunca emite a la DIAN: con
ALEGRA_PRODUCTION=false Alegra deja borradores y A3 los revisa y emite desde allá.

Vivía dentro del botón «Facturar» de Pedidos; se separó para que lo usen también las órdenes
del portal y de «Nueva Orden», que antes no abrían pedido y nunca se facturaban (ERR-194).
Quien llama decide si Alegra está habilitado (el dashboard lo lee de su propio módulo).
"""
from datetime import datetime

from app import billing
from app.config import APP_TIMEZONE
from app.services import db


def _cerrado(aviso: str) -> dict:
    return {"status": "cerrado", "invoice": None, "warning": aviso}


def facturar(pedido: dict) -> dict:
    """{status: 'facturado'|'cerrado', invoice: número o None, warning: texto o None}.
    No lanza: si Alegra falla el pedido queda cerrado y el aviso dice por qué."""
    pedido_id = pedido.get("id")
    try:
        lineas = []
        ordenes = {o["id"]: o for o in db.list_pedido_requests(pedido_id)}
        for request_id, perfil in db.get_pedido_profiles(pedido_id, con_request_id=True):
            paciente = (ordenes.get(request_id) or {}).get("patient_name")
            lineas.extend(billing.build_invoice_lines(perfil, paciente))
        if not lineas:
            return _cerrado("El pedido no tiene líneas facturables; quedó cerrado.")
        cliente = db.get_client_by_id(pedido.get("client_id")) or {}
        nit = cliente.get("tax_id")
        if not nit:
            return _cerrado("El cliente no tiene NIT; el pedido quedó cerrado sin facturar.")
        factura = billing.invoice_order(
            nit, cliente.get("clinic_name") or "Cliente A3", lineas,
            datetime.now(APP_TIMEZONE).date().isoformat(),
            {k: v for k, v in {"email": cliente.get("email")}.items() if v},
            client_row=cliente,  # la sede exacta: entre sedes con el mismo NIT puede cambiar
        )
        if factura and factura.get("invoice_id"):
            db.mark_pedido_invoiced(pedido_id, str(factura["invoice_id"]))
            return {"status": "facturado", "invoice": factura.get("number") or factura["invoice_id"],
                    "warning": None}
        return _cerrado("Alegra no devolvió factura; el pedido quedó cerrado.")
    except Exception as exc:  # noqa: BLE001
        return _cerrado(f"Cerrado, pero la factura falló: {str(exc)[:120]}")
