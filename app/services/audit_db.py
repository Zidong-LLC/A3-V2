"""Historial de cambios en datos maestros (tabla `audit_log`, migración 033).

Quién cambió qué y cuándo en clientes, motorizados, precios y usuarios. Solo se inserta:
el historial no se edita ni se borra. Registrar nunca frena la operación: si falla, el
cambio ya se hizo y solo se pierde la línea del historial (queda en el log del servidor).
"""
import logging

from flask import has_request_context, session

from app.services.db import _client

log = logging.getLogger(__name__)


def usuario_actual() -> str:
    if not has_request_context():
        return "sistema"
    return session.get("dashboard_username") or "sistema"


def registrar(entity: str, entity_id, action: str, changes: dict | None = None,
              username: str | None = None) -> None:
    fila = {"entity": entity, "entity_id": str(entity_id or ""), "action": action,
            "changes": changes or {}, "username": username or usuario_actual()}
    try:
        _client.table("audit_log").insert(fila).execute()
    except Exception:
        log.exception("audit_log: no se pudo registrar %s %s %s", entity, entity_id, action)


def registrar_lote(entity: str, filas: list[tuple], username: str | None = None) -> None:
    """Varias líneas (entity_id, action, changes) en pocos inserts: una carga masiva deja
    su línea por registro sin sumar una ida a la base por cada fila."""
    quien = username or usuario_actual()
    lote = [{"entity": entity, "entity_id": str(eid or ""), "action": accion,
             "changes": cambios or {}, "username": quien} for eid, accion, cambios in filas]
    for inicio in range(0, len(lote), 500):
        try:
            _client.table("audit_log").insert(lote[inicio:inicio + 500]).execute()
        except Exception:
            log.exception("audit_log: no se pudo registrar el lote de %s", entity)


def listar(entity: str, entity_id, limit: int = 50) -> list[dict]:
    try:
        return (_client.table("audit_log").select("action, changes, username, created_at")
                .eq("entity", entity).eq("entity_id", str(entity_id))
                .order("created_at", desc=True).limit(limit).execute().data or [])
    except Exception:
        log.exception("audit_log: no se pudo leer %s %s", entity, entity_id)
        return []
