"""Cargas masivas: precios, clientes, portafolio y motorizados (pedido de A3, llamada 4;
cualquier archivo, cierre v1).

Siempre en pasos: se sube el archivo (CSV con cualquier separador o .xlsx), se eligen
las columnas (ya vienen reconocidas por nombre), se MUESTRA el plan (qué se crea, qué se
actualiza, qué queda igual, qué no se pudo leer) y recién con la confirmación se escribe.
Una carga a ciegas puede pisar cientos de precios sin que nadie lo note.

El plan viaja al paso de confirmación en un campo oculto, pero no se aplica tal cual: al
confirmar se vuelve a validar contra la base. Lo que llega del navegador no manda. Cada
tipo exige además poder gestionar su módulo (precios, clientes o motorizados).
"""
import json

from flask import Blueprint, Response, flash, redirect, render_template, request, session, url_for

from app import access, imports, imports_aplicar, imports_archivo as archivo
from app import imports_exportar
from app import permissions as P
from app.services import audit_db, db, maestros_db

dashboard_import = Blueprint("dashboard_import", __name__)

TIPOS = {"precios": "Precios del catálogo", "clientes": "Clientes",
         "portafolio": "Portafolio nuevo", "motorizados": "Motorizados"}
MAX_CSV_BYTES = 5 * 1024 * 1024
_aplicar_clientes = imports_aplicar.aplicar_clientes  # nombre histórico (tests)


_login_required = access.login_requerido


def _tipos_permitidos() -> dict:
    perfil = access.perfil_actual()
    return {t: n for t, n in TIPOS.items() if P.puede(perfil, P.MODULO_DE_CARGA[t], P.GESTION)}


def _armar_plan(tipo: str, filas: list[dict], actualizar: bool = False) -> dict:
    if tipo == "clientes":
        couriers = db.list_active_couriers()
        return imports.plan_clientes(filas, db.list_clients_basic(), db.client_name_matches, actualizar,
                                     {imports.norm(c.get("name")): c["id"] for c in couriers},
                                     maestros_db.asignaciones())
    if tipo == "motorizados":
        return imports_aplicar.plan_motorizados(filas, db.list_couriers())
    tests, profiles = db.list_catalog_tests(limit=2000), db.list_catalog_profiles(limit=2000)
    if tipo == "portafolio":
        return imports.plan_portafolio(filas, tests, profiles)
    return imports.plan_precios(filas, tests, profiles)


def _pagina(**extra):
    contexto = {"plan": None, "mapeo": None, **extra}
    return render_template("dashboard_import.html", tipos=_tipos_permitidos(), etiquetas=archivo.ETIQUETAS,
                           username=session.get("dashboard_username", ""), **contexto)


def _vista_previa(tipo, nombre, encabezados, filas_brutas, mapa, actualizar):
    tabla = {"encabezados": encabezados, "filas": filas_brutas, "archivo": nombre}
    contexto = {"tipo": tipo, "tabla_json": json.dumps(tabla), "encabezados": encabezados,
                "mapa": mapa, "campos": archivo.CAMPOS[tipo], "actualizar": actualizar, "archivo": nombre,
                "ejemplo": filas_brutas[:3]}
    falta = archivo.faltantes(mapa, tipo)
    if falta:
        return _pagina(mapeo=contexto, falta=falta)
    filas = archivo.filas_con_mapa(filas_brutas, mapa)
    plan = _armar_plan(tipo, filas, actualizar)
    usadas = set(mapa.values())
    plan.update({"leidas": len(filas), "archivo": nombre, "titulo": TIPOS[tipo], "actualizar_activo": actualizar,
                 "ignorados": [h for i, h in enumerate(encabezados) if i not in usadas and h]})
    return _pagina(mapeo=contexto, plan=plan, plan_json=json.dumps(plan))


@dashboard_import.get("/cargas")
@_login_required
def cargas_page():
    return _pagina()


@dashboard_import.post("/cargas/previsualizar")
@_login_required
def previsualizar():
    tipo = (request.form.get("tipo") or "auto").strip()
    if tipo != "auto" and tipo not in _tipos_permitidos():
        flash("Elige qué tipo de carga es el archivo", "error")
        return redirect(url_for("dashboard_import.cargas_page"))
    subido = request.files.get("csv")
    data = subido.read(MAX_CSV_BYTES + 1) if subido else b""
    if not data or len(data) > MAX_CSV_BYTES:
        flash("Archivo inválido: debe ser un CSV o Excel (.xlsx) de máximo 5 MB", "error")
        return redirect(url_for("dashboard_import.cargas_page"))
    try:
        encabezados, filas = archivo.leer_tabla(data, subido.filename or "")
    except Exception:  # noqa: BLE001 — archivo dañado o de otro formato
        encabezados, filas = [], []
    if not filas:
        flash("No se encontraron filas con datos en el archivo", "error")
        return redirect(url_for("dashboard_import.cargas_page"))
    # «1101 - Cuadro Hemático | 14.000»: el código viene pegado al nombre. Se separa en su
    # propia columna antes de detectar, para precios y portafolio.
    for con_codigo in ("precios", "portafolio"):
        encabezados, filas = archivo.separar_codigo_del_nombre(encabezados, filas, con_codigo)
    # El tipo elegido manda solo si el archivo trae lo que ese tipo necesita; si no, se
    # detecta por las columnas (un archivo de clientes cargado como «precios» por dejar
    # el desplegable como venía no puede terminar en «faltan Código y Precio»).
    elegido = tipo
    if tipo == "auto" or archivo.faltantes(archivo.mapa_automatico(encabezados, tipo), tipo):
        detectado = archivo.detectar_tipo(encabezados, list(_tipos_permitidos()))
        # Solo nombre y teléfono calza con motorizados Y con clientes: no se adivina (una
        # lista de clientes aplicada como motorizados crea motorizados). Se pregunta.
        if tipo == "auto" and detectado == "motorizados" and \
                set(archivo.mapa_automatico(encabezados, "clientes")) <= {"name", "phone"}:
            flash("El archivo trae solo nombre y teléfono: elige si son clientes o motorizados y vuelve a subirlo", "error")
            return redirect(url_for("dashboard_import.cargas_page"))
        if detectado:
            tipo = detectado
        elif tipo == "auto":
            flash("No se pudo reconocer qué trae el archivo: elige el tipo de carga y vuelve a subirlo", "error")
            return redirect(url_for("dashboard_import.cargas_page"))
    if tipo != elegido:
        flash(f"Por sus columnas, el archivo se leyó como «{TIPOS[tipo]}».", "ok")
    return _vista_previa(tipo, subido.filename, encabezados, filas,
                         archivo.mapa_automatico(encabezados, tipo), request.form.get("actualizar") == "on")


@dashboard_import.post("/cargas/columnas")
@_login_required
def remapear():
    tipo = (request.form.get("tipo") or "").strip()
    try:
        tabla = json.loads(request.form.get("tabla") or "{}")
    except json.JSONDecodeError:
        tabla = {}
    if tipo not in _tipos_permitidos() or not tabla.get("filas"):
        flash("Vuelve a subir el archivo", "error")
        return redirect(url_for("dashboard_import.cargas_page"))
    total = len(tabla.get("encabezados") or [])
    mapa = {}
    for campo in archivo.CAMPOS[tipo]:
        valor = request.form.get(f"col_{campo}", "")
        if valor.isdigit() and int(valor) < total and int(valor) not in mapa.values():
            mapa[campo] = int(valor)
    return _vista_previa(tipo, tabla.get("archivo") or "archivo", tabla["encabezados"], tabla["filas"],
                         mapa, request.form.get("actualizar") == "on")


@dashboard_import.post("/cargas/aplicar")
@_login_required
def aplicar():
    try:
        plan = json.loads(request.form.get("plan") or "{}")
    except json.JSONDecodeError:
        plan = {}
    tipo = plan.get("tipo")
    if tipo not in _tipos_permitidos():
        flash("No hay un plan que aplicar", "error")
        return redirect(url_for("dashboard_import.cargas_page"))

    quien = session.get("dashboard_username") or "operator"
    if tipo == "precios":
        hechos, fallidos = imports_aplicar.aplicar_precios(plan.get("actualizar") or [], quien)
        resumen = f"{hechos} precio(s) actualizado(s)"
    elif tipo == "portafolio":
        hechos, fallidos = imports_aplicar.aplicar_portafolio(plan.get("crear") or [], quien)
        resumen = f"{hechos} ítem(s) agregado(s) al catálogo"
    elif tipo == "motorizados":
        creados, actualizados, fallidos = imports_aplicar.aplicar_motorizados(plan)
        resumen = f"{creados} motorizado(s) creado(s) y {actualizados} actualizado(s)"
    else:
        creados, actualizados, fallidos = imports_aplicar.aplicar_clientes(plan)
        resumen = f"{creados} cliente(s) creado(s) y {actualizados} actualizado(s)"
    audit_db.registrar("import", tipo, "import", {"archivo": plan.get("archivo"), "resultado": resumen,
                                                  "con_problemas": len(fallidos)})
    flash(resumen, "ok")
    for problema in fallidos[:20]:
        flash(problema, "error")
    return redirect(url_for("dashboard_import.cargas_page"))


@dashboard_import.get("/cargas/plantilla/<tipo>")
@_login_required
def plantilla(tipo):
    """Plantilla en Excel con desplegables y hoja «Cómo usar» (pedido del usuario, 29/10);
    `?formato=csv` conserva la plantilla de una fila para quien no tenga Excel."""
    if tipo not in TIPOS:
        return redirect(url_for("dashboard_import.cargas_page"))
    if request.args.get("formato") == "csv":
        return _csv(imports_exportar.plantilla(tipo), f"plantilla-{tipo}.csv")
    from app import imports_plantillas

    motorizados: list[str] = []
    if tipo == "clientes":
        try:
            motorizados = [c.get("name") for c in db.list_active_couriers()]
        except Exception:  # noqa: BLE001 — sin la lista, la plantilla sale sin ese desplegable
            motorizados = []
    return _xlsx(imports_plantillas.plantilla_xlsx(tipo, motorizados), f"plantilla-{tipo}.xlsx")


@dashboard_import.get("/cargas/ejemplo/<tipo>")
@_login_required
def ejemplo(tipo):
    """Excel de ejemplo con 20 filas (pedido del usuario, 29/10): se puede subir tal cual."""
    if tipo not in TIPOS:
        return redirect(url_for("dashboard_import.cargas_page"))
    from app import imports_ejemplo

    return _xlsx(imports_ejemplo.ejemplo_xlsx(tipo), f"ejemplo-{tipo}.xlsx")


@dashboard_import.get("/cargas/exportar/<tipo>")
@_login_required
def exportar(tipo):
    if tipo not in TIPOS or not P.puede(access.perfil_actual(), P.MODULO_DE_CARGA[tipo], P.CONSULTA):
        flash("Tu perfil no puede exportar esa lista", "error")
        return redirect(url_for("dashboard_import.cargas_page"))
    return _csv(imports_exportar.exportar(tipo), f"{tipo}-a3.csv")


def _xlsx(contenido: bytes, nombre: str) -> Response:
    return Response(contenido, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{nombre}"'})


def _csv(contenido: str, nombre: str) -> Response:
    # BOM + punto y coma: Excel en español lo abre en columnas sin preguntar.
    return Response("﻿" + contenido, mimetype="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{nombre}"'})
