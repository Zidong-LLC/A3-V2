"""Vistas cliente del portal: solicitar retiro de muestras, estado e
historial de solicitudes, y perfil de la cuenta (solo lectura).

El client_id sale SIEMPRE de la sesión; nunca de query/form.
"""
from flask import flash, redirect, render_template, request, session, url_for

from app.portal import portal_bp
from app.portal.auth import client_required
from app.services import db, portal_db

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

PAYMENT_METHOD_OPTIONS = [
    ("contraentrega", "Contra entrega"),
    ("pago_linea", "Pago en línea"),
]


@portal_bp.get("/mis/solicitudes")
@client_required
def client_requests_page():
    requests_list = portal_db.list_client_requests(session["portal_client_id"])
    return render_template(
        "portal/client_requests.html",
        requests=requests_list,
        status_labels=REQUEST_STATUS_LABELS,
        active_tab="solicitudes",
    )


@portal_bp.route("/mis/solicitudes/nueva", methods=["GET", "POST"])
@client_required
def client_new_request():
    client = db.get_client_by_id(session["portal_client_id"])
    if request.method == "POST":
        fields = {
            key: (request.form.get(key) or "").strip() or None
            for key in (
                "patient_name", "species", "patient_age", "owner_name",
                "exam_type", "pickup_address", "observations",
                "payment_method", "requesting_doctor",
            )
        }
        if not fields["patient_name"] or not fields["exam_type"]:
            flash("Paciente y análisis solicitado son obligatorios", "error")
            return render_template(
                "portal/client_new_request.html", client=client, form=request.form,
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
        "portal/client_new_request.html", client=client, form={},
        payment_options=PAYMENT_METHOD_OPTIONS, active_tab="solicitudes",
    )


@portal_bp.get("/mis/perfil")
@client_required
def client_profile_page():
    client = db.get_client_by_id(session["portal_client_id"])
    return render_template("portal/client_profile.html", client=client, active_tab="perfil")
