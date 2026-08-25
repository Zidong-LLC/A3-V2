"""Vista del espejo Anarvet en el dashboard del personal (decisión 013).

Lista los informes sincronizados (un informe = un paciente en una fecha) y muestra
el detalle de cada uno con sus analitos agrupados por examen, como el documento
del resultado. Blueprint separado (misma razón que dashboard_results): usa la MISMA
sesión del dashboard y no toca app/dashboard.py. Solo LECTURA del espejo local:
nunca le pega a Anarvet — para traer datos nuevos está el botón de sync.
"""
from datetime import datetime, timedelta
from functools import wraps

from flask import Blueprint, abort, redirect, render_template, request, session, url_for

from app.config import ANARVET_ENABLED, APP_TIMEZONE
from app.services import db

dashboard_anarvet = Blueprint("dashboard_anarvet", __name__)

PER_PAGE = 50


def _login_required(view_func):
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if not session.get("dashboard_authenticated"):
            return redirect(url_for("dashboard.login"))
        if not ANARVET_ENABLED:
            abort(404)  # con el flag apagado la sección no existe
        return view_func(*args, **kwargs)

    return wrapped


def _filters() -> dict:
    hoy = datetime.now(APP_TIMEZONE).date()
    return {
        "search": (request.args.get("search") or "").strip(),
        "cod_cliente": (request.args.get("cod_cliente") or "").strip(),
        "date_from": (request.args.get("date_from") or "").strip() or str(hoy - timedelta(days=7)),
        "date_to": (request.args.get("date_to") or "").strip(),
    }


@dashboard_anarvet.get("/resultados/anarvet")
@_login_required
def informes_page():
    filters = _filters()
    try:
        page = max(int(request.args.get("page", "1")), 1)
    except ValueError:
        page = 1
    informes, total = db.list_anarvet_informes(filters, page=page, per_page=PER_PAGE)
    pages = max((total + PER_PAGE - 1) // PER_PAGE, 1)
    return render_template(
        "dashboard_anarvet.html",
        informes=informes, filters=filters, total=total, page=page, pages=pages,
        username=session.get("dashboard_username", ""),
    )


@dashboard_anarvet.get("/resultados/anarvet/<codigo>/<fecha>")
@_login_required
def informe_detalle(codigo: str, fecha: str):
    analitos = db.get_anarvet_informe(codigo, fecha)
    if not analitos:
        abort(404)
    # Agrupar por examen respetando el orden de la consulta (dict conserva inserción).
    examenes: dict[str, list[dict]] = {}
    for fila in analitos:
        examenes.setdefault(fila.get("examen_cod") or "—", []).append(fila)
    return render_template(
        "dashboard_anarvet_detalle.html",
        paciente=analitos[0], examenes=examenes, total_analitos=len(analitos),
        username=session.get("dashboard_username", ""),
    )
