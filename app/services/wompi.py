"""Cliente de Wompi (pagos en línea). Solo I/O: crear un link de pago y validar la firma de
un evento. Documentación: https://docs.wompi.co/docs/colombia/links-de-pago/ y /eventos/."""
import hashlib
import hmac
import json
import urllib.request

from app.config import WOMPI_BASE_URL, WOMPI_EVENTS_SECRET, WOMPI_PRIVATE_KEY

_TIMEOUT = 20
CHECKOUT = "https://checkout.wompi.co/l/"


class WompiError(Exception):
    pass


def crear_link(nombre: str, descripcion: str, centavos: int) -> dict:
    """Link de un solo uso por el monto exacto. Devuelve {"id", "url"}."""
    if not WOMPI_PRIVATE_KEY:
        raise WompiError("falta WOMPI_PRIVATE_KEY")
    cuerpo = {"name": nombre[:120], "description": descripcion[:250], "single_use": True,
              "collect_shipping": False, "currency": "COP", "amount_in_cents": int(centavos)}
    req = urllib.request.Request(
        f"{WOMPI_BASE_URL}/payment_links", data=json.dumps(cuerpo).encode(), method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {WOMPI_PRIVATE_KEY}"})
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
            datos = json.loads(r.read() or b"{}").get("data") or {}
    except Exception as exc:  # noqa: BLE001 — se re-lanza con contexto
        raise WompiError(f"no se pudo crear el link de pago: {exc}") from exc
    if not datos.get("id"):
        raise WompiError("Wompi no devolvió el id del link")
    return {"id": str(datos["id"]), "url": CHECKOUT + str(datos["id"])}


def _valor(evento: dict, ruta: str):
    actual = evento.get("data") or {}
    for parte in ruta.split("."):
        actual = actual.get(parte) if isinstance(actual, dict) else None
    return "" if actual is None else actual


def firma_valida(evento: dict) -> bool:
    """SHA256 de los valores que lista `signature.properties`, más el timestamp y el secreto
    de eventos. Las propiedades pueden cambiar: se leen del propio evento."""
    firma = evento.get("signature") if isinstance(evento.get("signature"), dict) else {}
    propiedades, recibido = firma.get("properties"), str(firma.get("checksum") or "")
    if not WOMPI_EVENTS_SECRET or not isinstance(propiedades, list) or not recibido:
        return False
    cadena = ("".join(str(_valor(evento, p)) for p in propiedades)
              + str(evento.get("timestamp") or "") + WOMPI_EVENTS_SECRET)
    esperado = hashlib.sha256(cadena.encode()).hexdigest()
    return hmac.compare_digest(esperado, recibido.lower())
