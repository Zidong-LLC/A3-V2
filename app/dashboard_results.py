"""Módulo Resultados del dashboard del personal: subir, publicar y compartir
los PDFs de resultados que las veterinarias ven en el Portal Web.

Blueprint separado para no modificar app/dashboard.py: usa la MISMA sesión
del dashboard (session["dashboard_authenticated"]) y su login existente.
Compartir = publicar en el portal + notificación + aviso Telegram si el
cliente tiene chat vinculado (el fallo del aviso no revierte la publicación).
"""
from functools import wraps

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for

from app.config import ANARVET_ENABLED
from app.services import portal_db, storage, telegram
from app.services.db import find_clients_by_tax_id

dashboard_results = Blueprint("dashboard_results", __name__)

MAX_PDF_BYTES = 10 * 1024 * 1024  # 10 MB


def _dashboard_login_required(view_func):
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if not session.get("dashboard_authenticated"):
            return redirect(url_for("dashboard.login"))
        return view_func(*args, **kwargs)

    return wrapped


def _search_filters() -> dict:
    return {
        "patient": (request.args.get("patient") or "").strip(),
        "owner": (request.args.get("owner") or "").strip(),
        "clinic": (request.args.get("clinic") or "").strip(),
        "order_number": (request.args.get("order_number") or "").strip(),
        "date_from": (request.args.get("date_from") or "").strip(),
        "date_to": (request.args.get("date_to") or "").strip(),
    }


def _resolve_client(order_number: str, tax_id: str) -> tuple[str | None, dict | None]:
    """Resuelve el cliente destino por número de orden o por NIT."""
    if order_number:
        req = portal_db.get_request_by_order_number(order_number)
        if req and req.get("client_id"):
            return req["client_id"], req
    if tax_id:
        matches = find_clients_by_tax_id(tax_id)
        if len(matches) == 1:
            return matches[0]["id"], None
    return None, None


def _validated_pdf() -> bytes | None:
    file = request.files.get("pdf")
    if file is None or not (file.filename or "").lower().endswith(".pdf"):
        return None
    data = file.read(MAX_PDF_BYTES + 1)
    if len(data) > MAX_PDF_BYTES or not data.startswith(b"%PDF"):
        return None
    return data


def _publish_and_notify(result: dict) -> None:
    updated = portal_db.publish_lab_result(result["id"])
    if not updated:
        return
    title = f"Resultado disponible: {result.get('patient_name') or 'paciente'}"
    body = f"Orden {result.get('order_number') or 'sin número'} — {result.get('exam_name') or 'análisis'}"
    portal_db.insert_notification(
        result["client_id"], "result_published", title, body, result_id=result["id"]
    )
    try:
        chat_id = portal_db.telegram_chat_for_client(result["client_id"])
        if chat_id:
            telegram.send_message(
                chat_id,
                f"A3 Laboratorio: el resultado de {result.get('patient_name') or 'su paciente'}"
                f" (orden {result.get('order_number') or 's/n'}) ya está disponible en el portal.",
            )
    except Exception:
        pass


@dashboard_results.get("/resultados")
@_dashboard_login_required
def results_page():
    filters = _search_filters()
    results = portal_db.list_lab_results(filters)
    return render_template(
        "dashboard_results.html", results=results, filters=filters,
        username=session.get("dashboard_username", ""),
        anarvet_enabled=ANARVET_ENABLED,
    )


@dashboard_results.post("/resultados/subir")
@_dashboard_login_required
def upload_result():
    order_number = (request.form.get("order_number") or "").strip()
    tax_id = (request.form.get("tax_id") or "").strip()
    client_id, req = _resolve_client(order_number, tax_id)
    if not client_id:
        flash("No se encontró el cliente: verifique el número de orden o el NIT", "error")
        return redirect(url_for("dashboard_results.results_page"))

    data = _validated_pdf()
    if data is None:
        flash("Archivo inválido: debe ser un PDF de máximo 10 MB", "error")
        return redirect(url_for("dashboard_results.results_page"))

    pdf_path = storage.upload_result_pdf(client_id, order_number or None, data)
    result = portal_db.insert_lab_result({
        "client_id": client_id,
        "request_id": req["id"] if req else None,
        "order_number": order_number or None,
        "patient_name": (request.form.get("patient_name") or "").strip()
                        or (req.get("patient_name") if req else None),
        "owner_name": (request.form.get("owner_name") or "").strip()
                      or (req.get("owner_name") if req else None),
        "exam_name": (request.form.get("exam_name") or "").strip()
                     or (req.get("exam_type") if req else None),
        "pdf_path": pdf_path,
        "uploaded_by": session.get("dashboard_username"),
    })
    if result and request.form.get("publish_now"):
        _publish_and_notify(result)
        flash("Resultado subido y compartido con el cliente", "ok")
    else:
        flash("Resultado subido como borrador (sin compartir)", "ok")
    return redirect(url_for("dashboard_results.results_page"))


@dashboard_results.post("/resultados/<uuid:result_id>/publicar")
@_dashboard_login_required
def publish_result(result_id):
    result = portal_db.get_lab_result(str(result_id))
    if not result:
        abort(404)
    if result.get("published"):
        flash("El resultado ya estaba compartido", "ok")
    else:
        _publish_and_notify(result)
        flash("Resultado compartido con el cliente", "ok")
    return redirect(url_for("dashboard_results.results_page"))


@dashboard_results.get("/resultados/<uuid:result_id>/pdf")
@_dashboard_login_required
def result_pdf(result_id):
    result = portal_db.get_lab_result(str(result_id))
    if not result:
        abort(404)
    url = storage.result_signed_url(result["pdf_path"])
    if not url:
        abort(502)
    return redirect(url)
