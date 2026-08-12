"""Vistas cliente del portal: resultados publicados (ver/descargar/filtrar)
y notificaciones del laboratorio.

Solo se muestran resultados published=true del client_id de la sesión.
"""
import io
import re
import zipfile
from datetime import datetime

from flask import (
    abort, flash, redirect, render_template, request, send_file, session, url_for,
)

from app.config import APP_TIMEZONE
from app.portal import portal_bp
from app.portal.auth import client_required
from app.services import portal_db, storage

# Tope de la descarga masiva: el ZIP se arma en memoria, así que no puede crecer
# sin límite. Con más resultados, el cliente acota por fecha.
BULK_DOWNLOAD_LIMIT = 200


def _zip_entry_name(result: dict, used: set[str]) -> str:
    """Nombre legible y único dentro del ZIP.

    El nombre sale de datos que escribe el usuario, así que se saca todo lo que
    no sea alfanumérico: un `pdf_path` o un paciente con `../` no puede terminar
    escribiendo fuera de la carpeta al descomprimir.
    """
    parts = [result.get("order_number"), result.get("patient_name")]
    raw = "-".join(str(p) for p in parts if p) or "resultado"
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", raw).strip("-.") or "resultado"
    name = f"{safe}.pdf"
    counter = 2
    while name in used:
        name = f"{safe}-{counter}.pdf"
        counter += 1
    used.add(name)
    return name


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


@portal_bp.get("/mis/resultados/descargar")
@client_required
def client_results_bulk_download():
    """Descarga en ZIP todos los resultados que coincidan con el filtro actual.

    Respeta los mismos filtros que la tabla, así que el cliente descarga
    exactamente lo que está viendo. Los PDFs se bajan del bucket privado en el
    servidor: nunca se emite una signed URL por resultado.
    """
    filters = {
        "patient": (request.args.get("patient") or "").strip(),
        "order_number": (request.args.get("order_number") or "").strip(),
        "date_from": (request.args.get("date_from") or "").strip(),
        "date_to": (request.args.get("date_to") or "").strip(),
    }
    results = portal_db.list_lab_results(
        filters, client_id=session["portal_client_id"], only_published=True,
        limit=BULK_DOWNLOAD_LIMIT,
    )
    if not results:
        flash("No hay resultados para descargar con ese filtro", "error")
        return redirect(url_for("portal.client_results_page", **filters))

    buffer = io.BytesIO()
    used_names: set[str] = set()
    failed = 0
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as bundle:
        for result in results:
            try:
                data = storage.download_result_pdf(result["pdf_path"])
            except Exception:  # noqa: BLE001 — un PDF ilegible no anula el resto
                failed += 1
                continue
            bundle.writestr(_zip_entry_name(result, used_names), data)

    if not used_names:
        flash("No se pudo descargar ninguno de los resultados, intente de nuevo", "error")
        return redirect(url_for("portal.client_results_page", **filters))
    if failed:
        flash(f"{failed} resultado(s) no se pudieron incluir en el archivo", "error")

    buffer.seek(0)
    stamp = datetime.now(APP_TIMEZONE).strftime("%Y%m%d")
    return send_file(
        buffer, mimetype="application/zip", as_attachment=True,
        download_name=f"resultados-a3-{stamp}.zip",
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
