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
