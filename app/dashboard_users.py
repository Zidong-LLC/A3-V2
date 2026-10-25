"""Administración de usuarios del personal de A3. Solo el perfil Administrador entra acá
(lo controla `app/access.py` con el módulo «usuarios»)."""
import re

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from werkzeug.security import generate_password_hash

from app import access
from app import permissions as P
from app.config import DASHBOARD_ADMIN_USER
from app.services import audit_db, users_db

dashboard_users = Blueprint("dashboard_users", __name__)
MIN_CLAVE = 8
_USUARIO_VALIDO = re.compile(r"^[a-z0-9._-]{3,40}$")
_NIVELES = {P.GESTION: "Gestionar", P.CONSULTA: "Consultar", P.NINGUNO: "—"}
_ETIQUETAS = {"dashboard": "Panel", "operacion": "Operación", "clientes": "Clientes",
              "solicitudes": "Solicitudes", "pedidos": "Pedidos", "facturacion": "Facturación",
              "motorizados": "Motorizados", "agenda": "Agenda", "muestras": "Muestras",
              "resultados": "Resultados", "cargas": "Cargas", "precios": "Precios del catálogo",
              "usuarios": "Usuarios"}


_login_required = access.login_requerido


def _datos(form, nuevo: bool) -> tuple[dict, str | None]:
    datos = {"full_name": (form.get("full_name") or "").strip()[:120],
             "email": (form.get("email") or "").strip().lower()[:160] or None,
             "role": (form.get("role") or "").strip()}
    clave = form.get("password") or ""
    if datos["role"] not in P.PERFILES:
        return datos, "Elige un perfil válido."
    if not datos["full_name"]:
        return datos, "Escribe el nombre de la persona."
    if nuevo:
        usuario = users_db.normalizar_usuario(form.get("username"))
        if not _USUARIO_VALIDO.match(usuario):
            return datos, "El usuario debe tener de 3 a 40 letras, números, punto, guion o guion bajo."
        if usuario == users_db.normalizar_usuario(DASHBOARD_ADMIN_USER):
            return datos, "Ese usuario está reservado."
        datos["username"] = usuario
    if nuevo or clave:
        if len(clave) < MIN_CLAVE:
            return datos, f"La contraseña debe tener al menos {MIN_CLAVE} caracteres."
        datos["password_hash"] = generate_password_hash(clave)
    if not nuevo:
        datos["is_active"] = form.get("is_active") == "on"
    return datos, None


def _matriz() -> list[dict]:
    return [{"modulo": _ETIQUETAS[m],
             "niveles": [_NIVELES[P.nivel(perfil, m)] for perfil in P.PERFILES]} for m in P.MODULOS]


@dashboard_users.get("/usuarios")
@_login_required
def usuarios_page():
    try:
        usuarios, error = users_db.list_users(), None
    except Exception:
        usuarios, error = [], "No se pudo leer la lista de usuarios. Intenta de nuevo en un momento."
    return render_template("dashboard_users.html", usuarios=usuarios, error=error, perfiles=P.PERFILES,
                           matriz=_matriz(), min_clave=MIN_CLAVE, username=session.get("dashboard_username", ""))


@dashboard_users.post("/usuarios")
@_login_required
def crear_usuario():
    datos, error = _datos(request.form, nuevo=True)
    if not error and users_db.get_user_by_username(datos["username"]):
        error = f"Ya existe el usuario «{datos['username']}»."
    if error:
        flash(error, "error")
        return redirect(url_for("dashboard_users.usuarios_page"))
    creado = users_db.create_user(datos)
    if creado:
        audit_db.registrar("user", creado["id"], "create",
                           {"username": datos["username"], "role": datos["role"], "full_name": datos["full_name"]})
        flash(f"Usuario «{datos['username']}» creado con el perfil {P.PERFILES[datos['role']]}.", "ok")
    else:
        flash("No se pudo crear el usuario. Intenta de nuevo.", "error")
    return redirect(url_for("dashboard_users.usuarios_page"))


@dashboard_users.post("/usuarios/<uuid:user_id>")
@_login_required
def editar_usuario(user_id):
    datos, error = _datos(request.form, nuevo=False)
    if not error and str(user_id) == str(session.get("dashboard_user_id")) and not datos.get("is_active"):
        error = "No puedes bloquear tu propio usuario."
    if error:
        flash(error, "error")
        return redirect(url_for("dashboard_users.usuarios_page"))
    if users_db.update_user(str(user_id), datos):
        registro = {k: v for k, v in datos.items() if k != "password_hash"}
        if "password_hash" in datos:
            registro["password"] = "cambiada"
        audit_db.registrar("user", user_id, "update", registro)
        flash("Cambios guardados.", "ok")
    else:
        flash("No se pudieron guardar los cambios.", "error")
    return redirect(url_for("dashboard_users.usuarios_page"))
