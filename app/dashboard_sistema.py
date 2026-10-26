"""Panel de sistema (/sistema): acceso APARTE de la plataforma, solo para el responsable
técnico. No es una sección del CRM ni un perfil de A3: tiene su propia dirección, su
propio usuario y clave (`SISTEMA_USER` / `SISTEMA_PASSWORD`) y su propia sesión.

Lo que antes se veía únicamente en el Telegram de avisos y en los logs: estado en vivo de
cada servicio, fallas por componente, cuánta gente habla con el bot y cómo le va, tokens
del modelo y gasto del mes por servicio (decisión del usuario, 2026-10-26).
"""
import hmac
from concurrent.futures import ThreadPoolExecutor
from functools import wraps

from flask import Blueprint, flash, jsonify, redirect, render_template, request, session, url_for

from app import access, sistema
from app.config import PLATFORM_API_TOKEN, SISTEMA_PASSWORD, SISTEMA_USER
from app.services import system_db

dashboard_sistema = Blueprint("dashboard_sistema", __name__)
CLAVE_SESION = "sistema_authenticated"
DIAS = 7


def _igual(a: str, b: str) -> bool:
    return hmac.compare_digest((a or "").encode(), (b or "").encode())


def _con_sesion(view_func):
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if not session.get(CLAVE_SESION):
            return redirect(url_for("dashboard_sistema.login"))
        return view_func(*args, **kwargs)
    return wrapped


@dashboard_sistema.route("/sistema/login", methods=["GET", "POST"])
def login():
    if not SISTEMA_PASSWORD:
        return render_template("sistema_login.html", error="El panel no está configurado: falta SISTEMA_PASSWORD."), 503
    if request.method == "POST":
        ip, usuario = request.remote_addr or "", (request.form.get("username") or "").strip()
        if access.bloqueado(ip, f"sistema:{usuario}"):
            return render_template("sistema_login.html", error="Demasiados intentos. Espera unos minutos."), 429
        ok = _igual(usuario, SISTEMA_USER) and _igual(request.form.get("password") or "", SISTEMA_PASSWORD)
        access.anotar_intento(ip, f"sistema:{usuario}", ok)
        if ok:
            session[CLAVE_SESION] = True
            return redirect(url_for("dashboard_sistema.sistema_page"))
        return render_template("sistema_login.html", error="Usuario o clave incorrectos.")
    return render_template("sistema_login.html", error=None)


@dashboard_sistema.get("/sistema/logout")
def logout():
    session.pop(CLAVE_SESION, None)
    return redirect(url_for("dashboard_sistema.login"))


def _leer(nombre, fn, defecto):
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 — una lectura caída se muestra, no tumba el panel
        return {"error": f"{nombre}: {str(exc)[:120]}"} if isinstance(defecto, dict) else defecto


def _datos() -> dict:
    lecturas = {
        "salud": sistema.estado_servicios,
        "errores": lambda: system_db.eventos("error", DIAS),
        "turnos": lambda: system_db.eventos("turn", DIAS),
        "llm": lambda: system_db.eventos("llm", DIAS),
        "sesiones": lambda: system_db.sesiones_recientes(DIAS),
        "mensajes": lambda: system_db.mensajes_recientes(DIAS),
        "solicitudes": lambda: system_db.solicitudes_recientes(DIAS),
        "costos": system_db.costos,
        "openai": sistema.gasto_openai_mes,
    }
    with ThreadPoolExecutor(max_workers=len(lecturas), thread_name_prefix="sistema") as hilos:
        futuros = {k: hilos.submit(fn) for k, fn in lecturas.items()}
    leido = {k: _leer(k, f.result, {} if k in ("salud", "openai") else []) for k, f in futuros.items()}
    llm = sistema.resumen_llm(leido["llm"])
    traspaso = sistema.servicios_traspaso(leido["costos"], leido["openai"], leido["salud"], llm)
    return {
        "salud": leido["salud"],
        "errores": sistema.resumen_errores(leido["errores"]),
        "turnos": sistema.resumen_turnos(leido["turnos"]),
        "llm": llm,
        "conversaciones": sistema.resumen_conversaciones(leido["sesiones"], leido["mensajes"], leido["solicitudes"]),
        "traspaso": traspaso,
        "openai": leido["openai"],
        "total_mes": round(sum(f["usd"] for f in traspaso), 2),
        "dias": DIAS,
    }


@dashboard_sistema.get("/sistema")
@_con_sesion
def sistema_page():
    return render_template("dashboard_sistema.html", **_datos())


@dashboard_sistema.get("/api/sistema/estado")
def estado_json():
    """Lo mismo que la pantalla, en JSON: con la sesión del panel o con el token de la
    plataforma (para un monitor externo)."""
    token = request.headers.get("X-Platform-Token", "")
    if not session.get(CLAVE_SESION) and not (PLATFORM_API_TOKEN and _igual(token, PLATFORM_API_TOKEN)):
        return jsonify({"error": "unauthorized"}), 401
    return jsonify(_datos())


@dashboard_sistema.post("/sistema/costos")
@_con_sesion
def guardar_costos():
    """Los costos fijos que ningún servicio expone por API: se cargan a mano."""
    guardados = 0
    for clave, valor in request.form.items():
        if not clave.startswith("usd_"):
            continue
        servicio = clave[4:]
        try:
            monto = float((valor or "0").replace(",", "."))
        except ValueError:
            flash(f"Monto inválido para {servicio}", "error")
            continue
        if system_db.guardar_costo(servicio, max(monto, 0), request.form.get(f"nota_{servicio}", "")):
            guardados += 1
    flash(f"{guardados} costo(s) guardado(s)", "ok")
    return redirect(url_for("dashboard_sistema.sistema_page"))
