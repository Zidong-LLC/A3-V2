"""Login/logout del portal de clientes y decorador de acceso.

La veterinaria entra con el nombre de su clínica + NIT (decisión 2026-08-18:
reemplaza el login por email/contraseña de Supabase Auth, que nunca se
configuró). El NIT es la llave de búsqueda; el nombre solo VALIDA contra las
filas de ese NIT — nunca busca libre (anti enumeración). La sesión Flask usa
claves portal_* para no colisionar con las del dashboard.
"""
import re
import time
from collections import deque
from functools import wraps

from flask import current_app, abort, redirect, render_template, request, session, url_for

from app.portal import portal_bp
from app.services.db import client_name_matches, find_clients_by_tax_id, get_client_by_id
from app.config import PORTAL_DEMO_MODE, PORTAL_DEMO_CLIENT_ID

_SESSION_KEYS = ("portal_user_id", "portal_client_id", "portal_email", "portal_clinic_name")

# Mensaje único para todo fallo de identificación: no revela si el NIT existe.
_GENERIC_ERROR = "El nombre y el NIT no coinciden con un cliente registrado. Verifica los datos."

# Rate limit en memoria: máx. intentos de login por IP dentro de la ventana.
_MAX_ATTEMPTS = 10
_WINDOW_SECONDS = 300
_login_attempts: dict[str, deque] = {}


def _start_demo_session():
    """Inicia sesión de demo (sin credenciales) para mostrar el portal en una
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


def _rate_limited(ip: str) -> bool:
    now = time.monotonic()
    attempts = _login_attempts.setdefault(ip, deque())
    while attempts and now - attempts[0] > _WINDOW_SECONDS:
        attempts.popleft()
    if len(attempts) >= _MAX_ATTEMPTS:
        return True
    attempts.append(now)
    return False


def _find_sedes(nit: str, name: str) -> list[dict]:
    """Sedes activas cuyo NIT coincide (con las variantes que db ya normaliza)
    y cuyo nombre matchea lo tipeado. El nombre filtra SOLO dentro del NIT."""
    rows = find_clients_by_tax_id(nit)
    return [row for row in rows if client_name_matches(name, row.get("clinic_name"))]


def _start_client_session(client: dict, nit: str) -> None:
    nit_clean = re.sub(r"[^0-9]", "", nit) or nit.strip()
    session["portal_user_id"] = f"nit:{nit_clean}"
    session["portal_client_id"] = client["id"]
    # Con login real no hay email de acceso (se entra con clínica + NIT). El menú del
    # portal muestra el nombre de la sede: con el modo demo ahí iba el correo ficticio.
    session["portal_clinic_name"] = client.get("clinic_name") or ""
    session.pop("portal_email", None)


def _render_login(error=None, sedes=None, clinic_name="", nit=""):
    return render_template(
        "portal/login.html", error=error, sedes=sedes or [], clinic_name=clinic_name, nit=nit
    )


@portal_bp.route("/login", methods=["GET", "POST"])
def login():
    if PORTAL_DEMO_MODE and _start_demo_session():
        return redirect(url_for("portal.client_requests_page"))
    if request.method != "POST":
        return _render_login()

    if _rate_limited(request.remote_addr or "?"):
        return _render_login(error="Demasiados intentos. Espera unos minutos y vuelve a probar.")

    clinic_name = (request.form.get("clinic_name") or "").strip()
    nit = (request.form.get("nit") or "").strip()
    if not clinic_name or not nit:
        return _render_login(error="Escribe el nombre de la veterinaria y el NIT.",
                             clinic_name=clinic_name, nit=nit)

    try:
        sedes = _find_sedes(nit, clinic_name)
    except Exception:  # noqa: BLE001 — base caida: aviso amable, nunca un traceback (ERR-174)
        current_app.logger.exception("portal login: fallo la consulta de sedes")
        return _render_login(error="No pudimos verificar los datos en este momento. "
                                   "Intente de nuevo en unos minutos.",
                             clinic_name=clinic_name, nit=nit)
    if not sedes:
        return _render_login(error=_GENERIC_ERROR, clinic_name=clinic_name, nit=nit)

    chosen_id = (request.form.get("client_id") or "").strip()
    if chosen_id:
        # Re-validación server-side: el client_id del form debe pertenecer al NIT.
        chosen = next((row for row in sedes if row.get("id") == chosen_id), None)
        if not chosen:
            return _render_login(error=_GENERIC_ERROR, clinic_name=clinic_name, nit=nit)
        _start_client_session(chosen, nit)
        return redirect(url_for("portal.client_requests_page"))

    if len(sedes) == 1:
        _start_client_session(sedes[0], nit)
        return redirect(url_for("portal.client_requests_page"))

    # Varias sedes comparten el NIT: elegir cuál (el POST siguiente re-valida).
    return _render_login(sedes=sedes, clinic_name=clinic_name, nit=nit)


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
