"""Ficha de la veterinaria en la plataforma: todo lo de un cliente en una pantalla.

Nace de un problema concreto de la pantalla de Resultados: para subir un informe había que
escribir de memoria el número de orden o el NIT, sin ver a quién le estaba llegando. Acá se
busca la veterinaria por nombre, se abre su ficha y desde ahí se ve —y se hace— todo lo suyo:
sus solicitudes, los informes que se le subieron y qué le falta pagar.

Blueprint aparte, como `dashboard_results` y `dashboard_anarvet`: usa la MISMA sesión del
dashboard y no agranda `app/dashboard.py`, que ya es enorme.
"""


from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for

from app import access
from app import permissions as P
from app.dashboard import REQUEST_STATUS_LABELS
from app.services import audit_db, db, maestros_db, portal_db

dashboard_client = Blueprint("dashboard_client", __name__)

# Tope del autocompletar: suficiente para elegir, corto para que la lista se lea de un vistazo.
SUGERENCIAS = 12


_login_required = access.login_requerido


@dashboard_client.get("/clientes/buscar")
@_login_required
def buscar_clientes():
    """Autocompletar por nombre o NIT. Devuelve JSON para el buscador de la ficha."""
    termino = (request.args.get("q") or "").strip()
    if len(termino) < 2:
        return jsonify({"resultados": []})
    filas = db.search_clients_for_dashboard(termino, limit=SUGERENCIAS)
    return jsonify({"resultados": [
        {
            "id": f["id"],
            "nombre": f.get("clinic_name") or "",
            "nit": f.get("tax_id") or "",
            "zona": f.get("zone") or "",
            "activo": bool(f.get("is_active")),
        }
        for f in filas
    ]})


@dashboard_client.get("/clientes/<uuid:client_id>")
@_login_required
def ficha_cliente(client_id):
    """Ficha 360: datos, solicitudes, informes subidos y estado de cuenta."""
    cliente = maestros_db.get_client_any(str(client_id))
    if not cliente:
        return redirect(url_for("dashboard.clients_page"))
    motorizados = db.list_active_couriers()
    motorizado_id = maestros_db.courier_de_cliente(str(client_id))
    historial = audit_db.listar("client", str(client_id), limit=30)

    solicitudes = portal_db.list_client_requests(str(client_id), limit=50)
    informes = portal_db.list_lab_results({}, client_id=str(client_id), limit=50)

    # La cartera vive en el cache de Alegra y se cruza por NIT, no por client_id. Es
    # información de Facturación: un perfil sin ese módulo no la ve (docx de perfiles).
    ver_cartera = P.puede(access.perfil_actual(), "facturacion")
    nit = (cliente.get("tax_id") or "").strip()
    facturas = db.list_cartera(client_nit=nit) if nit and ver_cartera else []
    cartera = db.cartera_totales(facturas)

    return render_template(
        "dashboard_client.html",
        cliente=cliente,
        solicitudes=solicitudes,
        informes=informes,
        facturas=facturas[:30],
        facturas_total=len(facturas),
        cartera=cartera,
        ver_cartera=ver_cartera,
        publicados=sum(1 for i in informes if i.get("published")),
        username=session.get("dashboard_username", ""),
        active_tab="clientes",
        status_labels=REQUEST_STATUS_LABELS,
        motorizados=motorizados,
        motorizado_id=motorizado_id,
        historial=historial,
    )
