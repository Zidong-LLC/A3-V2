"""Emisión ante la DIAN del borrador de un pedido (propuesta del 28/09; decisión 016).

Hasta el 2026-11-16 la plataforma solo dejaba borradores y A3 emitía desde Alegra. El usuario
pidió sumar la emisión. `emitir` es la ÚNICA puerta a la DIAN y la usan dos cosas: el botón
«Emitir» de una persona de Facturación y, desde el 2026-11-25, la emisión automática de los
pedidos que el cliente confirmó (`app/emision_automatica.py`, decisión 017, con su propio
interruptor apagado por defecto).

Candados, todos obligatorios:
- `ALEGRA_EMISSION_ENABLED` apagado por defecto: sin la variable, esto no hace nada.
- Solo la llaman el botón y `emision_automatica` (un test lo vigila).
- Antes de emitir se lee la factura en Alegra: tiene que existir, ser borrador y tener total.
- Quién y qué queda en el historial (`audit_log`), salga bien o mal.

Una factura emitida no se deshace: se corrige con nota crédito en Alegra.
"""
import logging
import threading

from app.config import ALEGRA_EMISSION_ENABLED, ALEGRA_ENABLED
from app.services import alegra, audit_db, db

log = logging.getLogger(__name__)
_EN_CURSO: set[str] = set()
_CANDADO = threading.Lock()


def activa() -> bool:
    return bool(ALEGRA_ENABLED and ALEGRA_EMISSION_ENABLED)


def _no(mensaje: str, codigo: int = 409) -> dict:
    return {"ok": False, "error": mensaje, "codigo": codigo}


def emitir(pedido: dict | None) -> dict:
    """{ok, numero, mensaje} o {ok: False, error, codigo}. No lanza."""
    if not activa():
        return _no("La emisión desde la plataforma está apagada: se emite desde Alegra.", 403)
    if not pedido:
        return _no("El pedido no existe", 404)
    factura_id = str(pedido.get("alegra_invoice_id") or "")
    if pedido.get("status") != "facturado" or not factura_id:
        return _no("El pedido todavía no tiene borrador en Alegra: primero hay que facturarlo.")
    with _CANDADO:
        if factura_id in _EN_CURSO:  # doble clic o dos pestañas
            return _no("Esa factura ya se está emitiendo")
        _EN_CURSO.add(factura_id)
    try:
        return _emitir(pedido, factura_id)
    finally:
        with _CANDADO:
            _EN_CURSO.discard(factura_id)


def _emitir(pedido: dict, factura_id: str) -> dict:
    numero = pedido.get("pedido_number") or ""
    try:
        factura = alegra.get_invoice(factura_id)
    except Exception as exc:  # noqa: BLE001 — sin leerla no se emite a ciegas
        log.warning("emision: no se pudo leer la factura %s: %s", factura_id, exc)
        return _no("No pude leer la factura en Alegra. Intenta de nuevo en un momento.", 503)
    estado = str(factura.get("status") or "").lower()
    if estado != "draft":
        return _no(f"La factura {factura_id} ya no es un borrador en Alegra (estado: {estado or 'desconocido'}).")
    if float(factura.get("total") or 0) <= 0:
        return _no("El borrador no tiene valor: revísalo en Alegra antes de emitir.")
    traza = {"pedido": numero, "total": factura.get("total")}
    try:
        mensaje = alegra.stamp_invoice(factura_id)
    except Exception as exc:  # noqa: BLE001
        log.warning("emision: Alegra no emitió la factura %s del pedido %s: %s", factura_id, numero, exc)
        audit_db.registrar("invoice", factura_id, "emit_failed", {**traza, "motivo": str(exc)[:300]})
        return _no(f"Alegra no emitió la factura: {str(exc)[:200]}", 502)
    audit_db.registrar("invoice", factura_id, "emit", {**traza, "respuesta": mensaje})
    try:  # el caché se pone al día solo para que la pantalla lo muestre ya; la sync lo completa
        nueva = alegra.get_invoice(factura_id)
        db.marcar_factura_emitida(factura_id, nueva)
    except Exception:  # noqa: BLE001 — la factura ya salió: esto es solo la vista
        log.warning("emision: factura %s emitida, pero no se pudo refrescar el caché", factura_id)
        nueva = {}
    visible = (nueva.get("numberTemplate") or {}).get("fullNumber") or nueva.get("number") or factura_id
    log.info("emision: factura %s (pedido %s) emitida por %s", visible, numero, audit_db.usuario_actual())
    return {"ok": True, "numero": str(visible), "mensaje": mensaje}
