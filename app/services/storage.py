"""Supabase Storage: PDFs de resultados en el bucket privado del portal.

El bucket nunca es público: la descarga siempre pasa por una signed URL de
vida corta y la service role key jamás llega al navegador.
"""
import uuid

from app.config import PORTAL_RESULTS_BUCKET
from app.services.db import _client


def upload_result_pdf(client_id: str, order_ref: str | None, data: bytes) -> str:
    """Sube el PDF y devuelve el path dentro del bucket.
    Prefijo por client_id para auditoría y RLS futura de Storage."""
    safe_ref = (order_ref or "sin-orden").replace("/", "-")
    path = f"{client_id}/{safe_ref}/{uuid.uuid4().hex}.pdf"
    _client.storage.from_(PORTAL_RESULTS_BUCKET).upload(
        path, data, {"content-type": "application/pdf"}
    )
    return path


def result_signed_url(path: str, expires_in: int = 300) -> str:
    """URL firmada temporal para ver/descargar un PDF del bucket."""
    result = _client.storage.from_(PORTAL_RESULTS_BUCKET).create_signed_url(path, expires_in)
    return result.get("signedURL") or result.get("signedUrl") or ""


def download_result_pdf(path: str) -> bytes:
    """Bytes del PDF. Se usa para armar el ZIP de la descarga masiva: el
    servidor baja del bucket privado y entrega un solo archivo al cliente,
    sin exponer una signed URL por cada resultado."""
    return _client.storage.from_(PORTAL_RESULTS_BUCKET).download(path)
