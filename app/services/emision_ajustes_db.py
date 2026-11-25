"""Modo de emisión a la DIAN que A3 elige en Facturación (tabla `emision_ajustes`, migración 042).

Ante cualquier duda (tabla vacía, error de lectura, valor raro) el modo es 'manual': nada se
emite solo. Así una falla de la base nunca termina en una emisión que nadie pidió.
"""
from datetime import datetime, timezone

from app.services.db import _client

MODOS = ("manual", "clientes", "todos")
MANUAL = {"modo": "manual", "client_ids": []}


def leer() -> dict:
    try:
        filas = _client.table("emision_ajustes").select("modo, client_ids, updated_at, updated_by") \
            .eq("id", 1).limit(1).execute().data
    except Exception:  # noqa: BLE001 — sin poder leer, manual
        return dict(MANUAL)
    fila = (filas or [{}])[0]
    if fila.get("modo") not in MODOS:
        return dict(MANUAL)
    return {**fila, "client_ids": [str(c) for c in fila.get("client_ids") or []]}


def guardar(modo: str, client_ids: list[str], usuario: str) -> None:
    _client.table("emision_ajustes").upsert({
        "id": 1, "modo": modo, "client_ids": client_ids, "updated_by": usuario,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }).execute()


def clientes(client_ids: list[str]) -> list[dict]:
    """Nombre y NIT de los clientes elegidos, para mostrarlos en la pantalla."""
    if not client_ids:
        return []
    return _client.table("clients").select("id, clinic_name, tax_id").in_("id", client_ids).execute().data or []
