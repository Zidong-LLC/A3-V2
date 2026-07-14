"""Vistas cliente del portal: resultados publicados (ver/descargar/filtrar)
y notificaciones del laboratorio.

Solo se muestran resultados published=true del client_id de la sesión.
"""
from flask import abort, redirect, render_template, request, session, url_for

from app.portal import portal_bp
from app.portal.auth import client_required
from app.services import portal_db, storage


def _own_published_result(result_id) -> dict:
    """Carga el resultado verificando pertenencia y publicación (404 si no)."""
    result = portal_db.get_lab_result(str(result_id))
    if (
        not result
        or result.get("client_id") != session["portal_client_id"]
        or not result.get("published")
    ):
        abort(404)
    return result


@portal_bp.get("/mis/resultados")
@client_required
def client_results_page():
    filters = {
        "patient": (request.args.get("patient") or "").strip(),
        "order_number": (request.args.get("order_number") or "").strip(),
        "date_from": (request.args.get("date_from") or "").strip(),
        "date_to": (request.args.get("date_to") or "").strip(),
    }
    results = portal_db.list_lab_results(
        filters, client_id=session["portal_client_id"], only_published=True
    )
    return render_template(
        "portal/client_results.html", results=results, filters=filters, active_tab="resultados"
    )


@portal_bp.get("/mis/resultados/<uuid:result_id>")
@client_required
def client_result_detail(result_id):
    result = _own_published_result(result_id)
    pdf_url = storage.result_signed_url(result["pdf_path"])
    return render_template(
        "portal/result_detail.html",
        result=result, pdf_url=pdf_url, active_tab="resultados",
        back_url=url_for("portal.client_results_page"),
    )


@portal_bp.get("/mis/resultados/<uuid:result_id>/pdf")
@client_required
def client_result_pdf(result_id):
    result = _own_published_result(result_id)
    url = storage.result_signed_url(result["pdf_path"])
    if not url:
        abort(502)
    return redirect(url)


@portal_bp.get("/mis/notificaciones")
@client_required
def client_notifications_page():
    notifications = portal_db.list_notifications(session["portal_client_id"])
    return render_template(
        "portal/client_notifications.html", notifications=notifications,
        active_tab="notificaciones",
    )


@portal_bp.post("/mis/notificaciones/<uuid:notification_id>/leer")
@client_required
def client_notification_read(notification_id):
    portal_db.mark_notification_read(str(notification_id), session["portal_client_id"])
    return redirect(url_for("portal.client_notifications_page"))
