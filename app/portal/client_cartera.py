"""Vista cliente del portal: su estado de cuenta (análisis pagados y sin pagar).

Solo lectura. Los pagos se registran en Alegra y cualquier gestión de cobro escala a
contabilidad (regla de negocio 4): acá el cliente ve qué le facturaron, qué ya pagó y
qué le queda pendiente, sin poder tocar nada.

El filtro es por el NIT del cliente de la sesión — nunca por un NIT que venga del
request, para que nadie pueda mirar la cartera de otra veterinaria.
"""

from flask import render_template, session

from app.portal import portal_bp
from app.portal.auth import client_required
from app.services import db


@portal_bp.get("/mis/cuenta")
@client_required
def client_cartera_page():
    client = db.get_client_by_id(session["portal_client_id"]) or {}
    nit = (client.get("tax_id") or "").strip()

    facturas = db.list_cartera(client_nit=nit) if nit else []
    totales = db.cartera_totales(facturas)

    # Las pendientes primero: es lo que el cliente viene a ver.
    facturas.sort(key=lambda f: (int(f.get("balance") or 0) == 0, f.get("invoice_date") or ""), reverse=False)
    pendientes = [f for f in facturas if int(f.get("balance") or 0) > 0]
    pagadas = [f for f in facturas if int(f.get("balance") or 0) == 0]

    return render_template(
        "portal/client_cartera.html",
        active_tab="cuenta",
        client=client,
        totales=totales,
        pendientes=pendientes,
        pagadas=pagadas[:50],
        pagadas_total=len(pagadas),
        sin_nit=not nit,
    )
