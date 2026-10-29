"""Actividad REAL del laboratorio para el Panel (ERR-191).

Las tarjetas del Panel salen de las órdenes del bot y, sin conversaciones nuevas, todas
quedaban en 0 como si A3 no estuviera trabajando. Los informes de Anarvet sí reflejan lo
que pasa cada día: acá se cuentan los de hoy, la semana y el mes (consultas de conteo, sin
traer filas) y se dice cuándo fue la última conversación del bot.
"""
from datetime import date, datetime, timedelta

from app.config import ANARVET_ENABLED, APP_TIMEZONE
from app.services import db


def _contar(desde: date, hasta: date) -> int:
    _filas, total = db.list_anarvet_informes(
        {"date_from": desde.isoformat(), "date_to": hasta.isoformat()}, page=1, per_page=1)
    return total


def _fecha_corta(valor) -> str:
    """«2026-10-20» o un timestamp UTC de Supabase → «20/10/2026» en hora de Bogotá."""
    texto = str(valor or "")
    try:
        if "T" in texto:
            return datetime.fromisoformat(texto.replace("Z", "+00:00")).astimezone(APP_TIMEZONE).strftime("%d/%m/%Y")
        return datetime.strptime(texto[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        return ""


def resumen(leer_en_paralelo, hoy: date | None = None) -> dict:
    """{informes_hoy, informes_semana, informes_mes, ultimo_informe, ultima_conversacion}.
    Lo que no se pudo leer queda en None y la plantilla lo muestra como «—»."""
    hoy = hoy or datetime.now(APP_TIMEZONE).date()
    lecturas = {"ultima_conversacion": (lambda: (db.list_sessions(limit=1) or [{}])[0].get("updated_at"), None)}
    if ANARVET_ENABLED:
        lecturas.update(
            informes_hoy=(lambda: _contar(hoy, hoy), None),
            informes_semana=(lambda: _contar(hoy - timedelta(days=6), hoy), None),
            informes_mes=(lambda: _contar(hoy.replace(day=1), hoy), None),
            ultimo_informe=(db.max_anarvet_fecha_solicitud, None),
        )
    leido = leer_en_paralelo(**lecturas)
    return {
        "anarvet": ANARVET_ENABLED,
        "informes_hoy": leido.get("informes_hoy"),
        "informes_semana": leido.get("informes_semana"),
        "informes_mes": leido.get("informes_mes"),
        "ultimo_informe": _fecha_corta(leido.get("ultimo_informe")),
        "ultima_conversacion": _fecha_corta(leido.get("ultima_conversacion")),
    }
