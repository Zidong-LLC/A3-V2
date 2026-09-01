"""Avisos de error al Telegram del responsable técnico.

Cuando la plataforma está en producción, un error que hoy solo va al log es un cliente
esperando una respuesta que no llega. Esto manda el aviso al chat de `ADMIN_TELEGRAM_CHAT_ID`
para poder reaccionar sin estar mirando los logs.

Tres cuidados, todos deliberados:
1. **Nunca rompe lo que estaba pasando.** Si el aviso falla, se loggea y sigue: un bug en
   el avisador no puede tumbar el turno del cliente.
2. **Anti-spam obligatorio.** Un error en bucle mandaría cientos de mensajes y Telegram
   cortaría el bot. Cada firma de error avisa UNA vez por ventana y después informa
   cuántas veces se repitió.
3. **No filtra datos del cliente.** Va el tipo de error, el mensaje y dónde ocurrió; no
   el contenido de la conversación.

Sin `ADMIN_TELEGRAM_CHAT_ID` configurado no hace nada — así el entorno local no avisa.
"""
import logging
import threading
import time

logger = logging.getLogger(__name__)

# Una firma de error avisa una vez cada 15 minutos. Lo suficiente para enterarse rápido
# sin convertir una caída de la base en 400 mensajes.
VENTANA_SEGUNDOS = 900
_MAX_FIRMAS = 200

_estado: dict[str, dict] = {}
_lock = threading.Lock()


def _registrar(firma: str) -> int | None:
    """Devuelve cuántas repeticiones acumuladas informar, o None si toca callarse."""
    ahora = time.monotonic()
    with _lock:
        if len(_estado) > _MAX_FIRMAS:          # el dict no crece para siempre
            _estado.clear()
        dato = _estado.get(firma)
        if dato is None:
            _estado[firma] = {"ultimo": ahora, "repetidos": 0}
            return 0
        if ahora - dato["ultimo"] < VENTANA_SEGUNDOS:
            dato["repetidos"] += 1
            return None
        repetidos = dato["repetidos"]
        dato.update({"ultimo": ahora, "repetidos": 0})
        return repetidos


def _enviar(chat_id: str, token: str, texto: str) -> None:
    """Manda el aviso por el bot de AVISOS (@A3newsbot). No usa services/telegram a
    proposito: ese habla con el bot de los CLIENTES, y un aviso de error no tiene nada
    que ver con las conversaciones de las veterinarias."""
    import json
    import urllib.request

    datos = json.dumps({"chat_id": chat_id, "text": texto}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=datos,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        r.read()


def notify_error(contexto: str, exc: BaseException, detalle: str = "") -> bool:
    """Avisa de un error. Devuelve si el mensaje salió."""
    from app.config import ADMIN_TELEGRAM_CHAT_ID, ALERT_TELEGRAM_BOT_TOKEN, APP_ENV

    if not (ADMIN_TELEGRAM_CHAT_ID and ALERT_TELEGRAM_BOT_TOKEN):
        return False

    firma = f"{contexto}:{type(exc).__name__}:{str(exc)[:80]}"
    repetidos = _registrar(firma)
    if repetidos is None:
        return False

    lineas = [
        f"🔴 Error en la plataforma A3 ({APP_ENV})",
        f"Dónde: {contexto}",
        f"Qué: {type(exc).__name__}: {str(exc)[:300]}",
    ]
    if detalle:
        lineas.append(f"Detalle: {detalle[:200]}")
    if repetidos:
        lineas.append(f"(se repitió {repetidos} vez/veces más desde el último aviso)")

    try:
        _enviar(ADMIN_TELEGRAM_CHAT_ID, ALERT_TELEGRAM_BOT_TOKEN, chr(10).join(lineas))
        return True
    except Exception:  # noqa: BLE001 — el avisador jamás rompe lo que estaba pasando
        logger.exception("No se pudo avisar del error por Telegram")
        return False
