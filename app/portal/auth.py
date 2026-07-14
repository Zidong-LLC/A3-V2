"""Login/logout del portal de clientes y decorador de acceso.

La identidad viene de Supabase Auth (app/services/portal_auth.py); la sesión
Flask usa claves portal_* para no colisionar con las del dashboard.
"""
from functools import wraps

from flask import abort, redirect, render_template, request, session, url_for

from app.portal import portal_bp
from app.services import portal_auth
from app.services.db import get_client_by_id
from app.config import PORTAL_DEMO_MODE, PORTAL_DEMO_CLIENT_ID

_SESSION_KEYS = ("portal_user_id", "portal_client_id", "portal_email")


def _start_demo_session():
    """Inicia sesión de demo (sin contraseña) para mostrar el portal en una
    llamada. Devuelve el cliente si el PORTAL_DEMO_CLIENT_ID es válido, o None."""
    client = get_client_by_id(PORTAL_DEMO_CLIENT_ID) if PORTAL_DEMO_CLIENT_ID else None
    if not client:
        return None
    session["portal_user_id"] = "demo"
    session["portal_client_id"] = PORTAL_DEMO_CLIENT_ID
    session["portal_email"] = "demo@a3test.com"
    return client


def client_required(view_func):
    """Exige sesión de cliente. Regla de oro del portal: las vistas solo
    usan session["portal_client_id"]; jamás un client_id de query/form."""
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if not session.get("portal_user_id"):
            return redirect(url_for("portal.login"))
        if not session.get("portal_client_id"):
            abort(403)
        return view_func(*args, **kwargs)

    return wrapped


@portal_bp.route("/login", methods=["GET", "POST"])
def login():
    if PORTAL_DEMO_MODE and _start_demo_session():
        return redirect(url_for("portal.client_requests_page"))
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        try:
            identity = portal_auth.sign_in(email, password)
        except portal_auth.PortalAuthError as exc:
            return render_template("portal/login.html", error=str(exc))
        if not get_client_by_id(identity["client_id"]):
            return render_template(
                "portal/login.html", error="La cuenta no tiene un cliente válido asociado"
            )
        session["portal_user_id"] = identity["user_id"]
        session["portal_client_id"] = identity["client_id"]
        session["portal_email"] = identity.get("email")
        return redirect(url_for("portal.client_requests_page"))
    return render_template("portal/login.html", error=None)


@portal_bp.get("/logout")
def logout():
    for key in _SESSION_KEYS:
        session.pop(key, None)
    return redirect(url_for("portal.login"))


@portal_bp.get("/")
def home():
    if session.get("portal_user_id") and session.get("portal_client_id"):
        return redirect(url_for("portal.client_requests_page"))
    return redirect(url_for("portal.login"))
