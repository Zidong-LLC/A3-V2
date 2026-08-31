"""Cargas masivas por CSV: precios, clientes y portafolio (pedido de A3, llamada 4).

Siempre en dos pasos: se sube el archivo, se MUESTRA el plan (qué se crea, qué se
actualiza, qué queda igual, qué no se pudo leer) y recién con la confirmación se
escribe. Una carga a ciegas puede pisar cientos de precios sin que nadie lo note.

El plan viaja al paso de confirmación en un campo oculto, pero no se aplica tal
cual: al confirmar se vuelve a validar contra la base (tabla en lista blanca, el
código existe, el cliente existe). Lo que llega del navegador no manda.
"""
import json
from functools import wraps

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from app import imports
from app.services import db

dashboard_import = Blueprint("dashboard_import", __name__)

TIPOS = {
    "precios": "Precios del catálogo",
    "clientes": "Clientes",
    "portafolio": "Portafolio nuevo",
}
MAX_CSV_BYTES = 5 * 1024 * 1024


def _login_required(view_func):
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if not session.get("dashboard_authenticated"):
            return redirect(url_for("dashboard.login"))
        return view_func(*args, **kwargs)

    return wrapped


def _armar_plan(tipo: str, filas: list[dict]) -> dict:
    if tipo == "clientes":
        return imports.plan_clientes(filas, db.list_clients_basic(), db.client_name_matches)
    tests, profiles = db.list_catalog_tests(limit=2000), db.list_catalog_profiles(limit=2000)
    if tipo == "portafolio":
        return imports.plan_portafolio(filas, tests, profiles)
    return imports.plan_precios(filas, tests, profiles)


@dashboard_import.get("/cargas")
@_login_required
def cargas_page():
    return render_template("dashboard_import.html", tipos=TIPOS, plan=None,
                           username=session.get("dashboard_username", ""))


@dashboard_import.post("/cargas/previsualizar")
@_login_required
def previsualizar():
    tipo = (request.form.get("tipo") or "").strip()
    if tipo not in TIPOS:
        flash("Elige qué tipo de carga es el archivo", "error")
        return redirect(url_for("dashboard_import.cargas_page"))

    archivo = request.files.get("csv")
    data = archivo.read(MAX_CSV_BYTES + 1) if archivo else b""
    if not data or len(data) > MAX_CSV_BYTES:
        flash("Archivo inválido: debe ser un CSV de máximo 5 MB", "error")
        return redirect(url_for("dashboard_import.cargas_page"))

    filas, ignorados = imports.leer_csv(data)
    if not filas:
        flash("El archivo no tiene filas con datos", "error")
        return redirect(url_for("dashboard_import.cargas_page"))

    plan = _armar_plan(tipo, filas)
    plan.update({"leidas": len(filas), "ignorados": ignorados,
                 "archivo": archivo.filename, "titulo": TIPOS[tipo]})
    return render_template("dashboard_import.html", tipos=TIPOS, plan=plan,
                           plan_json=json.dumps(plan), username=session.get("dashboard_username", ""))


def _aplicar_precios(cambios: list[dict], quien: str) -> tuple[int, list[str]]:
    hechos, fallidos = 0, []
    for cambio in cambios:
        tabla, code = cambio.get("tabla"), str(cambio.get("code") or "")
        if tabla not in ("catalog_tests", "catalog_profiles"):
            fallidos.append(f"{code}: tabla inválida")
            continue
        antes = db.get_catalog_item(tabla, code)
        if not antes:
            fallidos.append(f"{code}: ya no existe en el catálogo")
            continue
        despues = db.update_catalog_item(tabla, code, {"price": int(cambio["despues"])})
        if not despues:
            fallidos.append(f"{code}: no se pudo actualizar")
            continue
        db.log_catalog_change(tabla, code, antes, despues, quien)
        hechos += 1
    return hechos, fallidos


def _aplicar_portafolio(nuevos: list[dict], quien: str) -> tuple[int, list[str]]:
    hechos, fallidos = 0, []
    for item in nuevos:
        tabla, code = item.get("tabla"), str(item.get("code") or "")
        if tabla not in ("catalog_tests", "catalog_profiles"):
            fallidos.append(f"{code}: tabla inválida")
            continue
        if db.get_catalog_item(tabla, code):
            fallidos.append(f"{code}: ya existía, no se pisa")
            continue
        payload = {k: item.get(k) for k in ("code", "name", "price", "category", "species")}
        if tabla == "catalog_tests":
            payload["sample"] = item.get("sample")
        creado = db.create_catalog_item(tabla, payload)
        if not creado:
            fallidos.append(f"{code}: no se pudo crear")
            continue
        db.log_catalog_change(tabla, code, {}, creado, quien)
        hechos += 1
    return hechos, fallidos


def _aplicar_clientes(plan: dict) -> tuple[int, int, list[str]]:
    # Cada fila por separado: que una reviente (NIT o teléfono duplicado, restricción
    # de la tabla) no cancela las demás. Con la lista real de terceros v3, un teléfono
    # repetido a mitad de la carga dejó 17 altas hechas y todo lo demás sin aplicar.
    creados, actualizados, fallidos = 0, 0, []
    for nuevo in plan.get("crear") or []:
        try:
            hecho = db.create_client(nuevo)
        except Exception as exc:  # noqa: BLE001 — se informa por fila
            hecho = None
            fallidos.append(f"{nuevo.get('clinic_name')}: {_motivo(exc)}")
        else:
            if not hecho:
                fallidos.append(f"{nuevo.get('clinic_name')}: no se pudo crear")
        creados += 1 if hecho else 0
    for cambio in plan.get("actualizar") or []:
        client_id = cambio.get("id")
        if not client_id or not db.get_client_by_id(client_id):
            fallidos.append(f"{cambio.get('clinic_name')}: el cliente ya no existe")
            continue
        try:
            if db.update_client_profile(client_id, cambio.get("cambios") or {}):
                actualizados += 1
        except Exception as exc:  # noqa: BLE001
            fallidos.append(f"{cambio.get('clinic_name')}: {_motivo(exc)}")
    return creados, actualizados, fallidos


def _motivo(exc: Exception) -> str:
    """El mensaje útil del error de la base, sin el JSON completo."""
    texto = str(getattr(exc, "message", "") or exc)
    if "clients_phone_key" in texto:
        return "el teléfono ya pertenece a otro cliente"
    if "duplicate key" in texto:
        return "ya existía un registro con esa clave"
    return texto[:120]


@dashboard_import.post("/cargas/aplicar")
@_login_required
def aplicar():
    try:
        plan = json.loads(request.form.get("plan") or "{}")
    except json.JSONDecodeError:
        plan = {}
    tipo = plan.get("tipo")
    if tipo not in TIPOS:
        flash("No hay un plan que aplicar", "error")
        return redirect(url_for("dashboard_import.cargas_page"))

    quien = session.get("dashboard_username") or "operator"
    if tipo == "precios":
        hechos, fallidos = _aplicar_precios(plan.get("actualizar") or [], quien)
        resumen = f"{hechos} precio{'' if hechos == 1 else 's'} actualizado{'' if hechos == 1 else 's'}"
    elif tipo == "portafolio":
        hechos, fallidos = _aplicar_portafolio(plan.get("crear") or [], quien)
        resumen = f"{hechos} ítem{'' if hechos == 1 else 's'} agregado{'' if hechos == 1 else 's'} al catálogo"
    else:
        creados, actualizados, fallidos = _aplicar_clientes(plan)
        resumen = f"{creados} cliente(s) creado(s) y {actualizados} completado(s)"

    flash(resumen, "ok")
    for problema in fallidos[:20]:
        flash(problema, "error")
    return redirect(url_for("dashboard_import.cargas_page"))
