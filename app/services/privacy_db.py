"""Evidencia de autorización de datos (tabla `privacy_consents`, migración 040).

Solo se agregan filas: lo que pasó con cada contacto queda como historia y la última
decide. No hay update ni delete a propósito.
"""
from app.services.db import _client


def ultimo_evento(contacto: str) -> str | None:
    filas = (_client.table("privacy_consents").select("event").eq("contact_key", contacto)
             .order("created_at", desc=True).limit(1).execute().data)
    return filas[0]["event"] if filas else None


def registrar(contacto: str, canal: str, chat_id: str, evento: str, version: str, url: str,
              respuesta: str | None = None) -> None:
    _client.table("privacy_consents").insert({
        "contact_key": contacto, "channel": canal, "external_chat_id": chat_id, "event": evento,
        "response_text": respuesta, "policy_version": version, "policy_url": url,
    }).execute()


def listar(limite: int = 5000) -> list[dict]:
    """Toda la evidencia, la más nueva primero (pantalla «Autorizaciones» del dashboard)."""
    return (_client.table("privacy_consents").select("*")
            .order("created_at", desc=True).limit(limite).execute().data) or []


def clientes_por_telefono() -> dict[str, str]:
    """Últimos 10 dígitos del teléfono → nombre de la clínica, para decir quién autorizó."""
    filas = _client.table("clients").select("clinic_name, phone").execute().data or []
    mapa = {}
    for fila in filas:
        digitos = "".join(ch for ch in str(fila.get("phone") or "") if ch.isdigit())[-10:]
        if len(digitos) == 10 and fila.get("clinic_name"):
            mapa.setdefault(digitos, fila["clinic_name"])
    return mapa
