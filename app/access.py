"""Ingreso del personal de A3 y control de acceso por perfil en cada pedido.

El usuario del .env (DASHBOARD_ADMIN_USER/PASSWORD) sigue entrando como Administrador:
es el respaldo para que nadie quede afuera si la tabla de usuarios no responde. Las
sesiones anteriores a los perfiles (solo `dashboard_authenticated`) eran de ese único
usuario, así que se leen como Administrador.
"""
import hmac
import logging
import threading
import time
from functools import wraps

from flask import jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from app import permissions as P
from app.services import users_db

log = logging.getLogger(__name__)

BLUEPRINTS = frozenset({"dashboard", "dashboard_results", "dashboard_client", "dashboard_anarvet",
                        "dashboard_agenda", "dashboard_import", "dashboard_users",
                        "dashboard_maestros"})
_REVALIDAR_SEGUNDOS = 300
_CLAVES = ("dashboard_authenticated", "dashboard_username", "dashboard_user_id",
           "dashboard_role", "dashboard_full_name", "dashboard_role_checked")
# Hash de una clave al azar que nadie conoce: un usuario que no existe tarda lo mismo que
# una clave equivocada, así el tiempo de respuesta no delata qué usuarios existen.
_HASH_RELLENO = ("scrypt:32768:8:1$zPmIarRiX9ZzcxMM$e4a60fe99cf074ac4126f7bbcd41e4b3f21aa09f1bbc5f69"
                 "dd7f0ee9677cfa2d5607ecd1e2e4dd6f13d51b3288cfabdb22f471360f054c16b5932012b7829a31")
# Límite de claves equivocadas por IP y usuario (en memoria: Render corre un solo proceso).
_INTENTOS_MAX, _VENTANA_SEGUNDOS = 5, 600
_fallidos: dict[tuple[str, str], list[float]] = {}
_candado = threading.Lock()


def _igual(a: str, b: str) -> bool:
    # compare_digest con str solo acepta ASCII: una clave con tilde daba error 500.
    return hmac.compare_digest(a.encode(), b.encode())


def _recientes(clave: tuple[str, str], ahora: float) -> list[float]:
    return [t for t in _fallidos.get(clave, []) if ahora - t < _VENTANA_SEGUNDOS]


def bloqueado(ip: str, username: str | None) -> bool:
    """¿Ya van 5 claves equivocadas en 10 minutos desde esta IP para este usuario?"""
    with _candado:
        return len(_recientes((ip, (username or "").strip().lower()), time.time())) >= _INTENTOS_MAX


def anotar_intento(ip: str, username: str | None, ok: bool) -> None:
    clave, ahora = (ip, (username or "").strip().lower()), time.time()
    with _candado:
        if ok:
            _fallidos.pop(clave, None)
            return
        _fallidos[clave] = _recientes(clave, ahora) + [ahora]
        if len(_fallidos) > 5000:  # muchos usuarios inventados: se olvidan los vencidos
            for vieja in [k for k in _fallidos if not _recientes(k, ahora)]:
                del _fallidos[vieja]


def autenticar(username: str | None, password: str | None,
               admin_user: str | None, admin_password: str | None) -> dict | None:
    usuario, clave = (username or "").strip(), password or ""
    if admin_password and _igual(usuario, admin_user or "") and _igual(clave, admin_password):
        return {"id": None, "username": usuario, "full_name": "Administrador", "role": "administrador"}
    try:
        fila = users_db.get_user_by_username(usuario)
    except Exception:
        log.exception("login: no se pudo consultar dashboard_users")
        return None
    guardado = (fila or {}).get("password_hash") or _HASH_RELLENO
    clave_ok = check_password_hash(guardado, clave) and guardado != _HASH_RELLENO
    if not fila or not fila.get("is_active") or not clave_ok:
        return None
    try:
        users_db.touch_login(fila["id"])
    except Exception:
        log.warning("login: no se pudo registrar la hora de ingreso de %s", usuario)
    return fila


def login_requerido(view_func):
    """Sin sesión, al login. Era el mismo decorador copiado en seis blueprints; el permiso
    por perfil lo controla `_control_de_acceso` antes de llegar acá."""
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if not session.get("dashboard_authenticated"):
            return redirect(url_for("dashboard.login"))
        return view_func(*args, **kwargs)
    return wrapped


def iniciar_sesion(usuario: dict) -> None:
    session["dashboard_authenticated"] = True
    session["dashboard_username"] = usuario["username"]
    session["dashboard_user_id"] = usuario.get("id")
    session["dashboard_role"] = usuario["role"]
    session["dashboard_full_name"] = usuario.get("full_name") or usuario["username"]
    session["dashboard_role_checked"] = time.time()


def cerrar_sesion() -> None:
    for clave in _CLAVES:
        session.pop(clave, None)


def perfil_actual() -> str | None:
    """Perfil de la sesión. Cada 5 minutos se vuelve a leer el usuario: si lo bloquearon o
    le cambiaron el perfil, se aplica sin esperar a que cierre sesión."""
    if not session.get("dashboard_authenticated"):
        return None
    user_id = session.get("dashboard_user_id")
    if user_id and time.time() - session.get("dashboard_role_checked", 0) > _REVALIDAR_SEGUNDOS:
        try:
            fila = users_db.get_user(user_id)
        except Exception:
            fila = {"is_active": True, "role": session.get("dashboard_role")}  # Supabase caído: se mantiene
        if not fila or not fila.get("is_active"):
            cerrar_sesion()
            return None
        session["dashboard_role"] = fila.get("role")
        session["dashboard_role_checked"] = time.time()
    return session.get("dashboard_role") or "administrador"


def registrar(app) -> None:
    @app.before_request
    def _control_de_acceso():
        endpoint = request.endpoint or ""
        if endpoint.split(".")[0] not in BLUEPRINTS or endpoint in P.LIBRES:
            return None
        if not session.get("dashboard_authenticated"):
            return None  # cada vista manda al login con su propio decorador
        perfil = perfil_actual()
        if perfil is None:
            return redirect(url_for("dashboard.login"))
        requerido = P.CONSULTA if request.method in ("GET", "HEAD") else P.GESTION
        if P.permite(perfil, endpoint, requerido):
            return None
        mensaje = "Tu perfil no tiene permiso para esta acción."
        if request.path.startswith("/api/") or request.is_json:
            return jsonify({"error": mensaje}), 403
        return render_template("sin_permiso.html", mensaje=mensaje,
                               username=session.get("dashboard_username", "")), 403

    @app.context_processor
    def _perfil_en_plantillas():
        if not session.get("dashboard_authenticated"):
            return {"puede": lambda *_a, **_k: False, "perfil_nombre": "", "usuario_nombre": ""}
        perfil = session.get("dashboard_role") or "administrador"
        return {
            "puede": lambda modulo, requerido=P.CONSULTA: P.puede(perfil, modulo, requerido),
            "perfil_nombre": P.PERFILES.get(perfil, ""),
            "usuario_nombre": session.get("dashboard_full_name") or session.get("dashboard_username", ""),
        }
