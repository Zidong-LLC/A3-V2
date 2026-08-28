"""Agenda de recogidas: la semana de cada motorizado, con reasignación y
reprogramación.

Blueprint aparte para no agrandar app/dashboard.py; usa la misma sesión del
dashboard. Las escrituras NO se duplican acá: la vista llama a la API que ya
existe (`/api/dashboard/request-operation`), que valida, guarda y deja el evento
de auditoría. Este módulo solo arma la grilla.
"""
from datetime import date, datetime, timedelta
from functools import wraps

from flask import Blueprint, redirect, render_template, request, session, url_for

from app.services import db

dashboard_agenda = Blueprint("dashboard_agenda", __name__)

# Lunes a sábado: A3 no recoge los domingos.
DIAS = ("Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado")
SIN_ASIGNAR = "sin_asignar"


def _login_required(view_func):
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if not session.get("dashboard_authenticated"):
            return redirect(url_for("dashboard.login"))
        return view_func(*args, **kwargs)

    return wrapped


def _lunes(texto: str | None) -> date:
    """Lunes de la semana pedida. Sin fecha válida, la semana en curso."""
    try:
        referencia = datetime.strptime((texto or "").strip(), "%Y-%m-%d").date()
    except ValueError:
        referencia = date.today()
    return referencia - timedelta(days=referencia.weekday())


def _dia_de(pickup: dict) -> str:
    return (pickup.get("scheduled_pickup_date") or "")[:10]


def armar_grilla(pickups: list[dict], couriers: list[dict], dias: list[date]) -> list[dict]:
    """Una fila por motorizado (más la de sin asignar) con sus recogidas por día.

    Las filas salen siempre, aunque el motorizado no tenga nada esa semana: la
    grilla sirve para ver quién está libre, no solo quién está cargado."""
    claves = [d.isoformat() for d in dias]
    filas = []
    for courier in couriers:
        filas.append({"id": courier["id"], "nombre": courier.get("name") or "Sin nombre",
                      # El color que el equipo eligió en Motorizados: el mismo con el que
                      # aparece en el mapa de cobertura.
                      "color": (courier.get("color") or "").strip(),
                      "dias": {clave: [] for clave in claves}, "total": 0})
    filas.append({"id": SIN_ASIGNAR, "nombre": "Sin asignar", "color": "",
                  "dias": {clave: [] for clave in claves}, "total": 0})
    por_id = {fila["id"]: fila for fila in filas}

    for pickup in pickups:
        dia = _dia_de(pickup)
        if dia not in claves:
            continue
        fila = por_id.get(pickup.get("assigned_courier_id") or SIN_ASIGNAR)
        if fila is None:
            # Motorizado inactivo o borrado: su carga no se pierde de vista.
            fila = {"id": pickup["assigned_courier_id"],
                    "nombre": (pickup.get("couriers") or {}).get("name") or "Motorizado inactivo",
                    "color": "",
                    "dias": {clave: [] for clave in claves}, "total": 0}
            por_id[fila["id"]] = fila
            filas.insert(len(filas) - 1, fila)
        fila["dias"][dia].append(pickup)
        fila["total"] += 1
    return filas


@dashboard_agenda.get("/agenda")
@_login_required
def agenda_page():
    lunes = _lunes(request.args.get("semana"))
    dias = [lunes + timedelta(days=i) for i in range(len(DIAS))]
    domingo = lunes + timedelta(days=6)

    pickups = db.list_pickups_between(lunes.isoformat(), domingo.isoformat())
    couriers = db.list_active_couriers()
    filas = armar_grilla(pickups, couriers, dias)

    return render_template(
        "dashboard_agenda.html",
        username=session.get("dashboard_username", ""),
        columnas=[{"clave": d.isoformat(), "nombre": nombre, "dia": d.strftime("%d/%m"),
                   "hoy": d == date.today()}
                  for d, nombre in zip(dias, DIAS)],
        filas=filas,
        couriers=couriers,
        total=len(pickups),
        semana_actual=lunes.isoformat(),
        semana_anterior=(lunes - timedelta(days=7)).isoformat(),
        semana_siguiente=(lunes + timedelta(days=7)).isoformat(),
        rango=f"{lunes.strftime('%d/%m')} al {(lunes + timedelta(days=5)).strftime('%d/%m/%Y')}",
    )
