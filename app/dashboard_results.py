"""Módulo Resultados del dashboard del personal: subir, publicar y compartir
los PDFs de resultados que las veterinarias ven en el Portal Web.

Blueprint separado para no modificar app/dashboard.py: usa la MISMA sesión
del dashboard (session["dashboard_authenticated"]) y su login existente.
Compartir = publicar en el portal + notificación + aviso Telegram si el
cliente tiene chat vinculado (el fallo del aviso no revierte la publicación).
"""
from functools import wraps

from flask import (
    Blueprint, abort, current_app, flash, redirect, render_template, request, session, url_for,
)

from datetime import datetime, timedelta

from app.config import ANARVET_ENABLED, APP_TIMEZONE
from app.services import chatwoot, db, portal_db, storage, telegram
from app.services.db import find_clients_by_tax_id, get_client_by_id

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


def _resolve_client(order_number: str, tax_id: str, client_id: str = "") -> tuple[str | None, dict | None]:
    """Resuelve el cliente destino: id explícito, número de orden o NIT.

    El `client_id` llega cuando se sube desde la ficha del cliente: es unívoco, y evita
    el problema del NIT compartido entre sedes (ERR-157), donde la búsqueda por NIT
    devuelve varias y no resuelve."""
    if client_id and get_client_by_id(client_id):
        return client_id, None
    if order_number:
        req = portal_db.get_request_by_order_number(order_number)
        if req and req.get("client_id"):
            return req["client_id"], req
    if tax_id:
        matches = find_clients_by_tax_id(tax_id)
        if len(matches) == 1:
            return matches[0]["id"], None
    return None, None


def _volver(default_endpoint: str = "dashboard_results.results_page"):
    """Vuelve a la ficha del cliente si la acción se disparó desde ahí.

    `volver_a` lo mandan las acciones sobre un informe ya subido; `client_id`, el
    formulario de carga de la propia ficha.
    """
    client_id = (request.form.get("volver_a") or "").strip()
    if not client_id and (request.form.get("volver_a_ficha") or "").strip():
        client_id = (request.form.get("client_id") or "").strip()
    if client_id:
        return redirect(url_for("dashboard_client.ficha_cliente", client_id=client_id))
    return redirect(url_for(default_endpoint))


def _validated_pdf(file=None) -> bytes | None:
    """Bytes del PDF si el archivo es válido. Sin argumento toma el campo `pdf`
    del formulario (carga de a uno); con archivo, valida ese (carga múltiple)."""
    if file is None:
        file = request.files.get("pdf")
    if file is None or not (file.filename or "").lower().endswith(".pdf"):
        return None
    data = file.read(MAX_PDF_BYTES + 1)
    if len(data) > MAX_PDF_BYTES or not data.startswith(b"%PDF"):
        return None
    return data


def _field(name: str, index: int) -> str:
    """Dato de la fila `index` de la carga múltiple, con el campo suelto de
    la carga de a uno como respaldo."""
    return (request.form.get(f"{name}_{index}") or request.form.get(name) or "").strip()


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
        vinculo = portal_db.chat_for_client(result["client_id"])
        if vinculo:
            chat_id, canal = vinculo
            aviso = (f"A3 Laboratorio: el resultado de {result.get('patient_name') or 'su paciente'}"
                     f" (orden {result.get('order_number') or 's/n'}) ya está disponible en el portal.")
            # El transporte según el canal de la sesión: whatsapp y chatwoot-web viajan
            # ambos por Chatwoot (tapón #2 de WhatsApp — antes solo avisaba a Telegram).
            if canal == "telegram":
                telegram.send_message(chat_id, aviso)
            else:
                chatwoot.send_message(chat_id, aviso)
    except Exception:
        pass


ANARVET_PER_PAGE = 50


def _anarvet_filters() -> dict:
    """Mismos filtros que la pantalla propia del espejo, para que la pestaña y esa
    pantalla se comporten igual."""
    hoy = datetime.now(APP_TIMEZONE).date()
    return {
        "search": (request.args.get("search") or "").strip(),
        "cod_cliente": (request.args.get("cod_cliente") or "").strip(),
        "date_from": (request.args.get("date_from") or "").strip() or str(hoy - timedelta(days=7)),
        "date_to": (request.args.get("date_to") or "").strip(),
    }


@dashboard_results.get("/resultados")
@_dashboard_login_required
def results_page():
    """Dos pestañas: los informes que carga el equipo de A3, y el espejo de Anarvet.

    Se arma SOLO la que se está viendo: el historial de resultados y el espejo son dos
    consultas distintas y no hacen falta las dos para mostrar una."""
    vista = (request.args.get("vista") or "").strip().lower()
    if vista not in ("informes", "anarvet"):
        vista = "informes"

    contexto = {
        "vista": vista,
        "username": session.get("dashboard_username", ""),
        "anarvet_enabled": ANARVET_ENABLED,
        "filters": _search_filters(),
        "results": [],
        "preset_client": None,
        "anarvet_informes": [], "anarvet_total": 0, "anarvet_page": 1, "anarvet_pages": 1,
        "anarvet_filters": _anarvet_filters(),
    }

    if vista == "anarvet":
        try:
            page = max(int(request.args.get("page", "1")), 1)
        except ValueError:
            page = 1
        informes, total = db.list_anarvet_informes(contexto["anarvet_filters"], page=page, per_page=ANARVET_PER_PAGE)
        contexto.update({
            "anarvet_informes": informes, "anarvet_total": total, "anarvet_page": page,
            "anarvet_pages": max((total + ANARVET_PER_PAGE - 1) // ANARVET_PER_PAGE, 1),
        })
    else:
        contexto["results"] = portal_db.list_lab_results(contexto["filters"])
        # Cliente precargado al entrar desde su ficha (?client_id=...): el formulario queda
        # apuntado a esa veterinaria y no hay que buscarla de nuevo.
        client_id = request.args.get("client_id", "").strip()
        contexto["preset_client"] = get_client_by_id(client_id) if client_id else None

    return render_template("dashboard_results.html", **contexto)


def _upload_one(file, index: int, tax_id: str, explicit_client: str) -> tuple[dict | None, str]:
    """Sube un archivo con los datos de SU fila. Devuelve (resultado, error)."""
    order_number = _field("order_number", index)
    client_id, req = _resolve_client(order_number, tax_id, explicit_client)
    if not client_id:
        return None, "No se encontró el cliente: verifique el número de orden o el NIT"

    data = _validated_pdf(file)
    if data is None:
        return None, "Archivo inválido: debe ser un PDF de máximo 10 MB"

    pdf_path = storage.upload_result_pdf(client_id, order_number or None, data)
    result = portal_db.insert_lab_result({
        "client_id": client_id,
        "request_id": req["id"] if req else None,
        "order_number": order_number or None,
        "patient_name": _field("patient_name", index) or (req.get("patient_name") if req else None),
        "owner_name": _field("owner_name", index) or (req.get("owner_name") if req else None),
        "exam_name": _field("exam_name", index) or (req.get("exam_type") if req else None),
        "pdf_path": pdf_path,
        "uploaded_by": session.get("dashboard_username"),
    })
    if not result:
        return None, f"{nombre}: no se pudo guardar"
    return result, ""


@dashboard_results.post("/resultados/subir")
@_dashboard_login_required
def upload_result():
    """Sube uno o varios informes. Con varios archivos, cada uno trae su fila de
    datos (`patient_name_0`, `order_number_0`, …) y se procesa por separado: que
    uno falle no cancela los demás."""
    files = [f for f in request.files.getlist("pdf") if (f.filename or "").strip()]
    if not files:
        flash("Archivo inválido: debe ser un PDF de máximo 10 MB", "error")
        return _volver()

    tax_id = (request.form.get("tax_id") or "").strip()
    explicit_client = (request.form.get("client_id") or "").strip()
    publicar = bool(request.form.get("publish_now"))
    subidos, errores = [], []
    for index, file in enumerate(files):
        result, error = _upload_one(file, index, tax_id, explicit_client)
        if error:
            # Con varios archivos el error dice CUÁL falló; con uno solo sobra el prefijo.
            errores.append(f"{file.filename}: {error}" if len(files) > 1 else error)
            continue
        subidos.append(result)
        if publicar:
            _publish_and_notify(result)

    for error in errores:
        flash(error, "error")
    if len(subidos) == 1:
        flash("Resultado subido y compartido con el cliente" if publicar
              else "Resultado subido como borrador (sin compartir)", "ok")
    elif subidos:
        flash(f"{len(subidos)} resultados subidos" + (" y compartidos con el cliente" if publicar
              else " como borrador (sin compartir)"), "ok")
    return _volver()


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
    return _volver()


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

@dashboard_results.post("/resultados/<uuid:result_id>/dejar-de-compartir")
@_dashboard_login_required
def unpublish_result(result_id):
    """Saca el informe del portal del cliente sin borrarlo.

    Es la marcha atrás del caso más caro: se compartió con la veterinaria equivocada. El
    archivo y la fila quedan, así que se puede revisar qué pasó y volver a compartirlo.
    """
    result = portal_db.get_lab_result(str(result_id))
    if not result:
        abort(404)
    if not result.get("published"):
        flash("Ese informe no estaba compartido", "ok")
    else:
        portal_db.unpublish_lab_result(str(result_id))
        flash("El informe ya no se ve en el portal del cliente", "ok")
    return _volver()


@dashboard_results.post("/resultados/<uuid:result_id>/eliminar")
@_dashboard_login_required
def delete_result(result_id):
    """Borra el informe, su archivo y el aviso que le llegó al cliente.

    Sin vuelta atrás, a propósito: es para el PDF que nunca debió subirse. Si el archivo
    ya no está en el bucket se sigue igual — lo que importa es que deje de estar publicado.
    """
    result = portal_db.get_lab_result(str(result_id))
    if not result:
        abort(404)
    try:
        storage.delete_result_pdf(result.get("pdf_path"))
    except Exception as exc:  # noqa: BLE001 — el borrado del archivo no debe frenar el resto
        current_app.logger.warning("No se pudo borrar el PDF %s: %s", result.get("pdf_path"), exc)
    portal_db.delete_lab_result(str(result_id))
    flash("Informe eliminado", "ok")
    return _volver()
