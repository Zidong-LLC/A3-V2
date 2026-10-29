"""Eventos del sistema y costos fijos (tablas `system_events` y `system_costs`, migración 035).

Registrar NUNCA frena lo que estaba pasando: va en un hilo aparte y, si la base no
responde, se pierde la línea (queda en el log). En los tests queda apagado salvo que el
test lo encienda a propósito.
"""
import logging
import os
import threading
from datetime import datetime, timedelta, timezone

from app.services.db import _client, _paginado

log = logging.getLogger(__name__)
_ACTIVO = os.environ.get("APP_ENV", "") != "test"
# Supabase corta cada request en 1000 filas: las lecturas del panel van paginadas (ERR-187).
# 2000 por lectura: con 5000 x 6 lecturas cada 2 min, el panel abierto era una de las
# cargas que saturó la base el 29/10 (ERR-196).
LIMITE = 2000


def _insertar(fila: dict) -> None:
    try:
        _client.table("system_events").insert(fila).execute()
    except Exception:  # noqa: BLE001 — el registro jamás rompe el flujo
        log.warning("system_events: no se pudo registrar %s/%s", fila.get("kind"), fila.get("component"))


def registrar(kind: str, component: str, level: str = "info", message: str = "",
              context: str = "", details: dict | None = None, chat_id: str | None = None) -> None:
    if not _ACTIVO:
        return
    fila = {"kind": kind, "component": component, "level": level, "message": (message or "")[:500],
            "context": (context or "")[:300], "details": details or {}, "chat_id": chat_id}
    threading.Thread(target=_insertar, args=(fila,), daemon=True).start()


def _desde(dias: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=dias)).isoformat()


def eventos(kind: str, dias: int = 7, limit: int = LIMITE) -> list[dict]:
    """Eventos de un tipo, del más nuevo al más viejo."""
    return _paginado(lambda: _client.table("system_events")
                     .select("created_at, component, level, message, context, details, chat_id")
                     .eq("kind", kind).gte("created_at", _desde(dias))
                     .order("created_at", desc=True).order("id"), limit)


def sesiones_recientes(dias: int = 7) -> list[dict]:
    return _paginado(lambda: _client.table("telegram_sessions")
                     .select("external_chat_id, channel, phase_current, requires_handoff, handoff_area, updated_at, captured_fields")
                     .gte("updated_at", _desde(dias)).order("updated_at", desc=True).order("id"), LIMITE)


def mensajes_recientes(dias: int = 7) -> list[dict]:
    return _paginado(lambda: _client.table("conversation_messages").select("external_chat_id, role, created_at")
                     .gte("created_at", _desde(dias)).order("created_at", desc=True).order("id"), LIMITE)


def solicitudes_recientes(dias: int = 7) -> list[dict]:
    return _paginado(lambda: _client.table("requests").select("created_at, entry_channel, status")
                     .gte("created_at", _desde(dias)).order("created_at", desc=True).order("id"), LIMITE)


def costos() -> list[dict]:
    return _client.table("system_costs").select("*").order("service").execute().data or []


def guardar_costo(service: str, monthly_usd: float, note: str) -> bool:
    filas = (_client.table("system_costs").update({"monthly_usd": monthly_usd, "note": note[:200],
                                                   "updated_at": datetime.now(timezone.utc).isoformat()})
             .eq("service", service).execute().data)
    return bool(filas)
