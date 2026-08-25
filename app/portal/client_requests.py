"""Vistas cliente del portal: solicitar retiro de muestras, estado e
historial de solicitudes, y perfil de la cuenta (solo lectura).

El client_id sale SIEMPRE de la sesión; nunca de query/form.
"""
from flask import abort, flash, redirect, render_template, request, session, url_for

from app.portal import portal_bp
from app.portal.auth import client_required
from app.services import db, portal_db
# La traducción de un formulario a campos de orden vive en app/orders.py: el dashboard
# tiene su propio formulario de carga manual (2026-08-25) y ambos deben aplicar la MISMA
# regla de dinero (ERR-097). Se reexportan para no romper los imports existentes.
from app.orders import PAYMENT_METHOD_OPTIONS, resolve_catalog_selection  # noqa: F401

# Labels propios del portal (copiados, no importados de dashboard.py: el
# dashboard es intocable y no debe volverse dependencia del portal).
REQUEST_STATUS_LABELS = {
    "received": "Recibida",
    "assigned": "Asignada",
    "on_route": "En ruta",
    "picked_up": "Retirada",
    "in_lab": "En laboratorio",
    "processed": "Procesada",
    "sent": "Enviada",
    "cancelled": "Cancelada",
    "error_pending_assignment": "En asignación de motorizado",
}

# Avance de la orden: reemplaza al tracking GPS (sin LiveConnect no hay fuente de
# posición). El cliente ve en qué punto del recorrido está su muestra.
REQUEST_STATUS_FLOW = [
    ("received", "Recibida"),
    ("assigned", "Asignada"),
    ("on_route", "En ruta"),
    ("picked_up", "Retirada"),
    ("in_lab", "En laboratorio"),
    ("processed", "Procesada"),
    ("sent", "Enviada"),
]

# Estados que no avanzan por la línea: se muestran aparte, no como un paso.
REQUEST_STATUS_OFF_FLOW = ("cancelled", "error_pending_assignment")

# El cliente NO ve eventos internos: facturación (alegra_invoiced/alegra_failed)
# ni revisiones de alta de cliente. Lista blanca, no lista negra: un evento nuevo
# es invisible hasta que se decida explícitamente mostrarlo.
CLIENT_VISIBLE_EVENTS = {
    "created": "Solicitud registrada",
    "status_updated": "Actualización de estado",
    # Es el tipo que escriben DE VERDAD los endpoints del dashboard cuando el personal
    # mueve una solicitud o una muestra (`dashboard.py`: request-status y sample-status).
    # Sin él, el cliente veía "Solicitud registrada" y nada más, por más que su muestra
    # hubiera recorrido medio laboratorio.
    "dashboard_status_update": "Actualización de estado",
    "result_published": "Resultado publicado",
}


def build_status_progress(status: str) -> list[dict]:
    """Pasos del recorrido marcando los ya cumplidos según el estado actual."""
    if status in REQUEST_STATUS_OFF_FLOW:
        return []
    keys = [key for key, _ in REQUEST_STATUS_FLOW]
    current = keys.index(status) if status in keys else -1
    return [
        {
            "key": key,
            "label": label,
            "done": index < current,
            "current": index == current,
        }
        for index, (key, label) in enumerate(REQUEST_STATUS_FLOW)
    ]




def build_timeline(events: list[dict]) -> list[dict]:
    """Eventos visibles para el cliente, del más reciente al más antiguo.

    Solo se expone el estado nuevo del payload: el resto del `event_payload`
    lleva datos internos que no deben salir del laboratorio.
    """
    timeline = []
    for event in events:
        label = CLIENT_VISIBLE_EVENTS.get(event.get("event_type"))
        if not label:
            continue
        payload = event.get("event_payload") or {}
        new_status = payload.get("status") if isinstance(payload, dict) else None
        timeline.append({
            "label": label,
            "created_at": event.get("created_at") or "",
            "status_label": REQUEST_STATUS_LABELS.get(new_status, new_status or ""),
        })
    return timeline


def with_result_step(progress: list[dict], request_id: str, client_id: str) -> list[dict]:
    """Agrega el paso final "Resultado disponible" cuando ya se le publicó el informe.

    Va acá y no dentro de `build_status_progress` a propósito: esa función es pura y su
    contrato está fijado por tests. El recorrido de la muestra (recibida → … → enviada) es
    del laboratorio; que el resultado esté publicado es un hecho aparte, y solo se marca
    cuando existe de verdad — nunca se promete un resultado que el cliente no puede abrir.
    """
    if not progress:
        return progress
    try:
        publicados = portal_db.list_lab_results(
            {"request_id": request_id}, client_id=client_id, only_published=True, limit=1)
    except Exception:
        return progress
    listo = bool(publicados)
    if listo:
        for paso in progress:
            paso["done"], paso["current"] = True, False
    return progress + [{
        "key": "result_ready",
        "label": "Resultado disponible",
        "done": False,
        "current": listo,
    }]


@portal_bp.get("/mis/solicitudes")
@client_required
def client_requests_page():
    filters = {
        "patient": (request.args.get("patient") or "").strip(),
        "order_number": (request.args.get("order_number") or "").strip(),
        "status": (request.args.get("status") or "").strip(),
        "date_from": (request.args.get("date_from") or "").strip(),
        "date_to": (request.args.get("date_to") or "").strip(),
    }
    # Un estado desconocido devolvería vacío sin explicación: se descarta.
    if filters["status"] not in REQUEST_STATUS_LABELS:
        filters["status"] = ""
    requests_list = portal_db.list_client_requests(
        session["portal_client_id"], filters=filters
    )
    return render_template(
        "portal/client_requests.html",
        requests=requests_list,
        filters=filters,
        status_labels=REQUEST_STATUS_LABELS,
        active_tab="solicitudes",
    )


@portal_bp.get("/mis/solicitudes/<uuid:request_id>")
@client_required
def client_request_detail(request_id):
    order = portal_db.get_client_request(str(request_id), session["portal_client_id"])
    if not order:
        abort(404)
    events = db.list_request_events(str(request_id), limit=50)
    return render_template(
        "portal/client_request_detail.html",
        order=order,
        progress=with_result_step(
            build_status_progress(order.get("status")), str(request_id),
            session["portal_client_id"]),
        timeline=build_timeline(events),
        status_labels=REQUEST_STATUS_LABELS,
        active_tab="solicitudes",
        back_url=url_for("portal.client_requests_page"),
    )


@portal_bp.route("/mis/solicitudes/nueva", methods=["GET", "POST"])
@client_required
def client_new_request():
    client = db.get_client_by_id(session["portal_client_id"])
    catalog = {
        "profiles": db.list_catalog_profiles(),
        "tests": db.list_catalog_tests(),
    }
    if request.method == "POST":
        fields = {
            key: (request.form.get(key) or "").strip() or None
            for key in (
                "patient_name", "species", "patient_age", "owner_name",
                "pickup_address", "observations", "payment_method", "requesting_doctor",
            )
        }
        # El análisis sale del catálogo, no de texto libre (ERR-097).
        selected_test_codes = request.form.getlist("test_codes")
        fields.update(resolve_catalog_selection(
            (request.form.get("profile_code") or "").strip(), selected_test_codes,
        ))
        if not fields["patient_name"] or not fields["exam_type"]:
            flash(
                "Indique el paciente y al menos un perfil o análisis del catálogo",
                "error",
            )
            return render_template(
                "portal/client_new_request.html", client=client, form=request.form,
                catalog=catalog, selected_test_codes=selected_test_codes,
                payment_options=PAYMENT_METHOD_OPTIONS, active_tab="solicitudes",
            )
        fields["pickup_address"] = fields["pickup_address"] or (client or {}).get("address")
        fields["clinic_name"] = (client or {}).get("clinic_name")
        fields["clinic_phone"] = (client or {}).get("phone")

        created = db.create_request(
            chat_id=f"portal:{session['portal_client_id']}",
            session={"client_id": session["portal_client_id"], "channel": "portal"},
            ai_response={"intent": "route_scheduling", "captured_fields": fields},
        )
        if not created:
            flash("No se pudo registrar la solicitud, intente de nuevo", "error")
            return redirect(url_for("portal.client_new_request"))

        order_number = created.get("order_number")
        portal_db.insert_notification(
            session["portal_client_id"],
            "request_created",
            f"Solicitud de retiro registrada ({order_number or 'sin número'})",
            f"Paciente {fields['patient_name']} — {fields['exam_type']}",
            request_id=created.get("request_id"),
        )
        flash(
            f"Solicitud registrada con número de orden {order_number}"
            if order_number else "Solicitud registrada",
            "ok",
        )
        return redirect(url_for("portal.client_requests_page"))

    return render_template(
        "portal/client_new_request.html", client=client, form={}, catalog=catalog,
        selected_test_codes=[], payment_options=PAYMENT_METHOD_OPTIONS,
        active_tab="solicitudes",
    )


@portal_bp.get("/mis/perfil")
@client_required
def client_profile_page():
    client = db.get_client_by_id(session["portal_client_id"])
    return render_template("portal/client_profile.html", client=client, active_tab="perfil")
