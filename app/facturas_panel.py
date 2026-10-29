"""Facturas del cache de Alegra para las métricas y gráficos del panel y de Facturación.

Un año de A3 son ~15.000 facturas: leerlas son ~16 consultas de 1000 filas. Se traen solo
las de los últimos 13 meses (lo que usan «mes», «año» y el gráfico de 12 meses) y se
guardan 5 minutos en memoria para no repetir esas consultas en cada carga de pantalla.
Al sincronizar con Alegra se descartan (`invalidar`), así el número nuevo se ve enseguida.
"""
import logging
import threading
import time
from datetime import date, datetime, timedelta

from app.config import APP_TIMEZONE
from app.services import db

logger = logging.getLogger(__name__)
TTL_SEGUNDOS = 300
DIAS_A_REFRESCAR = 60  # pagos y anulaciones de los últimos 2 meses (la cartera de A3 vence a 30)
_guardadas: dict[str, tuple[float, list[dict]]] = {}
_candado = threading.Lock()
_sync_en_curso = threading.Lock()


def desde_hoy(hoy: date | None = None) -> str:
    hoy = hoy or datetime.now(APP_TIMEZONE).date()
    return min(date(hoy.year, 1, 1), date(hoy.year - 1, hoy.month, 1)).isoformat()


def recientes(columnas: str) -> list[dict]:
    with _candado:
        guardado = _guardadas.get(columnas)
        if guardado and time.monotonic() - guardado[0] < TTL_SEGUNDOS:
            return guardado[1]
    filas = db.list_all_cached_invoices(columnas, limit=60000, desde=desde_hoy())
    with _candado:
        _guardadas[columnas] = (time.monotonic(), filas)
    return filas


def invalidar() -> None:
    with _candado:
        _guardadas.clear()


def sincronizar_en_segundo_plano(dias: int = DIAS_A_REFRESCAR) -> str:
    """Refresca desde Alegra (solo lectura) las facturas de los últimos `dias`. Lo dispara el
    cron horario: antes el cache solo se actualizaba con el botón de Facturación y quedó
    congelado en el 26/08, con el panel mostrando «$0 este mes» (ERR-191). En un hilo,
    porque son ~100 consultas a Alegra y el cron no tiene que esperarlas."""
    from app.config import ALEGRA_ENABLED

    if not ALEGRA_ENABLED:
        return "alegra_deshabilitado"
    if not _sync_en_curso.acquire(blocking=False):
        return "en_curso"

    def correr():
        try:
            from app.dashboard import _sync_invoices_from_alegra  # local: dashboard importa este módulo
            desde = (datetime.now(APP_TIMEZONE).date() - timedelta(days=dias)).isoformat()
            resultado = _sync_invoices_from_alegra(max_pages=1000, desde=desde)
            invalidar()
            logger.info("facturas: %s sincronizadas desde %s %s", resultado["synced"], desde,
                        resultado["errors"][:1] or "")
        except Exception as exc:  # noqa: BLE001 — Alegra caído no puede tumbar el proceso
            logger.warning("facturas: falló la sincronización con Alegra: %s", exc)
        finally:
            _sync_en_curso.release()

    threading.Thread(target=correr, name="sync-facturas", daemon=True).start()
    return "lanzada"
