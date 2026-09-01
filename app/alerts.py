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


def _rastro(exc: BaseException, maximo: int = 4) -> list[str]:
    """Las lineas de NUESTRO codigo donde paso el error, de la mas profunda hacia atras.

    Se filtran los frames de librerias: cuando algo revienta dentro de httpx u openai,
    esos frames no dicen nada util — lo que hace falta es en que linea nuestra empezo.
    Si no hay ningun frame propio (raro), se muestran los ultimos tal cual."""
    import os
    import traceback

    frames = traceback.extract_tb(exc.__traceback__)
    if not frames:
        return []
    propios = [f for f in frames
               if f"{os.sep}app{os.sep}" in f.filename or f"{os.sep}tools{os.sep}" in f.filename]
    elegidos = (propios or frames)[-maximo:]

    salida = []
    for f in elegidos:
        # Ruta corta: desde app/ o tools/ en adelante, que es lo que se busca en el repo.
        partes = f.filename.replace(os.sep, "/").split("/")
        corta = "/".join(partes[-3:]) if len(partes) > 3 else f.filename
        linea = f"  {corta}:{f.lineno} en {f.name}"
        if f.line:
            linea += chr(10) + "      " + f.line.strip()[:90]
        salida.append(linea)
    return salida


def _version() -> str:
    """Que codigo esta corriendo. En Render sale gratis de sus variables; en local, del
    git de la maquina. Sin esto, un aviso no dice CONTRA QUE codigo mirar."""
    import os
    import subprocess

    commit = os.environ.get("RENDER_GIT_COMMIT", "")
    rama = os.environ.get("RENDER_GIT_BRANCH", "")
    if not commit:
        try:
            commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                                    text=True, timeout=3).stdout.strip()
            rama = subprocess.run(["git", "branch", "--show-current"], capture_output=True,
                                  text=True, timeout=3).stdout.strip()
        except Exception:  # noqa: BLE001
            return "version desconocida"
    etiqueta = commit[:7] if commit else "?"
    return f"{etiqueta} ({rama})" if rama else etiqueta


def notify_error(contexto: str, exc: BaseException, detalle: str = "") -> bool:
    """Avisa de un error. Devuelve si el mensaje salió."""
    from app.config import ADMIN_TELEGRAM_CHAT_ID, ALERT_TELEGRAM_BOT_TOKEN, APP_ENV

    if not (ADMIN_TELEGRAM_CHAT_ID and ALERT_TELEGRAM_BOT_TOKEN):
        return False

    firma = f"{contexto}:{type(exc).__name__}:{str(exc)[:80]}"
    repetidos = _registrar(firma)
    if repetidos is None:
        return False

    from datetime import datetime

    from app.config import APP_TIMEZONE

    lineas = [
        f"🔴 A3 · {contexto}",
        f"{type(exc).__name__}: {str(exc)[:250]}",
    ]

    # La causa raíz: cuando un error envuelve a otro ("falló X" porque abajo falló Y),
    # el de abajo es el que dice qué arreglar.
    causa = exc.__cause__ or exc.__context__
    if causa is not None and type(causa) is not type(exc):
        lineas.append(f"  causado por {type(causa).__name__}: {str(causa)[:120]}")

    rastro = _rastro(exc)
    if rastro:
        lineas.append("")
        lineas.append("Dónde falló:")
        lineas.extend(rastro)

    lineas.append("")
    if detalle:
        lineas.append(f"Contexto: {detalle[:200]}")
    lineas.append(f"Versión: {_version()} · {APP_ENV}")
    lineas.append(datetime.now(APP_TIMEZONE).strftime("%d/%m %H:%M:%S"))
    if repetidos:
        lineas.append(f"⚠ se repitió {repetidos} vez/veces más desde el último aviso")

    try:
        _enviar(ADMIN_TELEGRAM_CHAT_ID, ALERT_TELEGRAM_BOT_TOKEN, chr(10).join(lineas))
        return True
    except Exception:  # noqa: BLE001 — el avisador jamás rompe lo que estaba pasando
        logger.exception("No se pudo avisar del error por Telegram")
        return False
