"""Usuarios del personal de A3 (tabla `dashboard_users`, migración 033).

El hash de la contraseña solo sale de este módulo en `get_user_by_username`, que usa el
login para verificarla; el resto de las lecturas no lo trae.
"""
from datetime import datetime, timezone

from app.services.db import _client

_CAMPOS = "id, username, full_name, email, role, is_active, created_at, last_login_at"


def normalizar_usuario(username: str | None) -> str:
    return (username or "").strip().lower()


def list_users() -> list[dict]:
    return _client.table("dashboard_users").select(_CAMPOS).order("username").execute().data or []


def get_user(user_id: str) -> dict | None:
    filas = _client.table("dashboard_users").select(_CAMPOS).eq("id", user_id).limit(1).execute().data
    return filas[0] if filas else None


def get_user_by_username(username: str) -> dict | None:
    nombre = normalizar_usuario(username)
    if not nombre:
        return None
    filas = (_client.table("dashboard_users").select(_CAMPOS + ", password_hash")
             .eq("username", nombre).limit(1).execute().data)
    return filas[0] if filas else None


def create_user(payload: dict) -> dict | None:
    datos = {**payload, "username": normalizar_usuario(payload.get("username"))}
    filas = _client.table("dashboard_users").insert(datos).execute().data
    return filas[0] if filas else None


def update_user(user_id: str, cambios: dict) -> bool:
    datos = {**cambios, "updated_at": datetime.now(timezone.utc).isoformat()}
    filas = _client.table("dashboard_users").update(datos).eq("id", user_id).execute().data
    return bool(filas)


def touch_login(user_id: str) -> None:
    _client.table("dashboard_users").update(
        {"last_login_at": datetime.now(timezone.utc).isoformat()}).eq("id", user_id).execute()
