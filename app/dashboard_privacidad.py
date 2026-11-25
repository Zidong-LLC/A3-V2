"""Evidencia de la autorización de datos por WhatsApp (pedido de A3, 2026-11-25).

El bot ya guardaba cada pregunta y cada respuesta en `privacy_consents` (quién, cuándo,
qué contestó, versión y enlace de la política), pero no había dónde verlo. Esta sección
lo muestra y lo descarga en CSV. Solo lectura: la evidencia no se edita ni se borra.
"""
import csv
import io
from datetime import datetime

from flask import Blueprint, Response, render_template, request

from app import access
from app.config import APP_TIMEZONE
from app.services import privacy_db

dashboard_privacidad = Blueprint("dashboard_privacidad", __name__)
EVENTOS = {"asked": "Se le preguntó", "accepted": "Aceptó", "rejected": "Rechazó"}
COLUMNAS = ("Fecha y hora (Bogotá)", "Número", "Cliente", "Evento", "Respuesta",
            "Versión de la política", "Enlace de la política", "Canal", "Conversación")


def _fecha(valor) -> str:
    try:
        momento = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
        return momento.astimezone(APP_TIMEZONE).strftime("%d/%m/%Y %H:%M:%S")
    except (TypeError, ValueError):
        return str(valor or "")


def filas(eventos: list[dict], clientes: dict[str, str], busqueda: str = "") -> list[dict]:
    """Eventos listos para mostrar; `busqueda` filtra por número o nombre del cliente."""
    busqueda = (busqueda or "").strip().lower()
    digitos_busqueda = "".join(ch for ch in busqueda if ch.isdigit())
    salida = []
    for ev in eventos:
        numero = str(ev.get("contact_key") or "")
        cliente = clientes.get("".join(ch for ch in numero if ch.isdigit())[-10:], "")
        if busqueda and not ((digitos_busqueda and digitos_busqueda in numero)
                             or busqueda in cliente.lower()):
            continue
        salida.append({"fecha": _fecha(ev.get("created_at")), "numero": numero, "cliente": cliente,
                       "evento": EVENTOS.get(ev.get("event"), ev.get("event") or ""),
                       "clave": ev.get("event"), "respuesta": ev.get("response_text") or "",
                       "version": ev.get("policy_version") or "", "url": ev.get("policy_url") or "",
                       "canal": ev.get("channel") or "", "conversacion": ev.get("external_chat_id") or ""})
    return salida


def resumen(eventos: list[dict]) -> dict:
    """Estado de cada número según su último evento (la lista llega del más nuevo al más viejo)."""
    ultimo = {}
    for ev in eventos:
        ultimo.setdefault(ev.get("contact_key"), ev.get("event"))
    estados = list(ultimo.values())
    return {"aceptaron": estados.count("accepted"), "rechazaron": estados.count("rejected"),
            "sin_responder": estados.count("asked"), "contactos": len(estados)}


def _leer() -> tuple[list[dict], dict[str, str], str | None]:
    try:
        return privacy_db.listar(), privacy_db.clientes_por_telefono(), None
    except Exception:  # noqa: BLE001 — la pantalla avisa en vez de romperse
        return [], {}, "No se pudo leer la evidencia. Intenta de nuevo en un momento."


@dashboard_privacidad.get("/autorizaciones")
@access.login_requerido
def autorizaciones_page():
    eventos, clientes, error = _leer()
    busqueda = request.args.get("q", "")
    return render_template("dashboard_privacidad.html", filas=filas(eventos, clientes, busqueda),
                           resumen=resumen(eventos), busqueda=busqueda, error=error)


@dashboard_privacidad.get("/autorizaciones.csv")
@access.login_requerido
def autorizaciones_csv():
    eventos, clientes, _ = _leer()
    salida = io.StringIO()
    escritor = csv.writer(salida, delimiter=";")  # Excel en español lo abre en columnas
    escritor.writerow(COLUMNAS)
    for f in filas(eventos, clientes, request.args.get("q", "")):
        escritor.writerow([f["fecha"], f["numero"], f["cliente"], f["evento"], f["respuesta"],
                           f["version"], f["url"], f["canal"], f["conversacion"]])
    return Response("\ufeff" + salida.getvalue(), mimetype="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="autorizaciones-datos-a3.csv"'})
