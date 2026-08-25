"""HTML → PDF con Chromium headless (Anarvet Fase 2).

Por qué un navegador y no una librería de PDF: la plantilla del informe usa flexbox y
grid, que WeasyPrint no soporta — devolvería el informe roto, no distinto. El PDF que se
publica al portal tiene que ser el mismo documento que el personal ya aprobó imprimiendo.

Regla de degradación: si el navegador no está, este módulo levanta `PdfUnavailable` rápido
y con un mensaje claro. **Nunca cuelga el request de Flask, y nunca afecta a ver o imprimir
el informe** — eso sigue funcionando desde el navegador del personal, pase lo que pase acá.
"""
import logging
import threading

from app.config import (PDF_CHROME_CHANNEL, PDF_ENABLED, PDF_EXECUTABLE_PATH,
                        PDF_TIMEOUT_MS)

logger = logging.getLogger(__name__)


class PdfUnavailable(RuntimeError):
    """No se pudo generar el PDF en el servidor (navegador ausente, caído o lento)."""


# Chromium usa 150-300 MB mientras renderiza y el plan de Render tiene 512. Dos informes a
# la vez no tumban el PDF: tumban la INSTANCIA, con el bot de Telegram adentro. Uno por
# proceso; el segundo espera su turno en vez de competir por la memoria.
_UN_RENDER_A_LA_VEZ = threading.Semaphore(1)
_DISPONIBLE: bool | None = None  # cache: /health no paga un arranque de navegador por chequeo

_ARGS = [
    "--no-sandbox",             # el contenedor no tiene user namespaces
    "--disable-dev-shm-usage",  # /dev/shm son 64 MB en contenedores: sin esto, crashea
    "--disable-gpu",
]


def _destino() -> dict:
    """Windows: el Chrome ya instalado. Linux: el Chromium del entorno."""
    if PDF_EXECUTABLE_PATH:
        return {"executable_path": PDF_EXECUTABLE_PATH}
    if PDF_CHROME_CHANNEL:
        return {"channel": PDF_CHROME_CHANNEL}
    return {}


def html_to_pdf(html: str, *, timeout_ms: int | None = None) -> bytes:
    """HTML ya renderizado por Jinja → bytes de un PDF A4.

    Recibe el HTML, no una URL de la propia app, a propósito: con gunicorn en modo sync,
    pedirle al navegador una página nuestra bloquea al worker que debería servirla, y el
    request se cuelga hasta el timeout. Funciona porque la plantilla lleva el CSS adentro.
    """
    if not PDF_ENABLED:
        raise PdfUnavailable("La generación de PDF está apagada (PDF_ENABLED=false)")
    timeout_ms = timeout_ms or PDF_TIMEOUT_MS
    try:
        # Import perezoso: que falte playwright no puede romper el arranque de Flask.
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise PdfUnavailable(f"playwright no está instalado: {exc}") from exc

    if not _UN_RENDER_A_LA_VEZ.acquire(timeout=timeout_ms / 1000):
        raise PdfUnavailable("Hay otro informe generándose; probá de nuevo en unos segundos")
    try:
        # El context manager cierra navegador y driver pase lo que pase, timeout incluido.
        # Sin él quedan Chromium huérfanos comiéndose la memoria hasta el próximo deploy.
        with sync_playwright() as p:
            navegador = p.chromium.launch(args=_ARGS, timeout=timeout_ms, **_destino())
            try:
                pagina = navegador.new_page()
                pagina.set_default_timeout(timeout_ms)
                pagina.emulate_media(media="print")  # aplica @media print: esconde los botones
                pagina.set_content(html, wait_until="load")
                # La plantilla trae su tipografía de Google Fonts. Si no llega, Chromium usa
                # el fallback y cambia la métrica: el informe que ajustamos a una página
                # vuelve a desbordarse. Se la espera, pero no se muere por ella.
                try:
                    pagina.wait_for_function("document.fonts.status === 'loaded'", timeout=5000)
                except PlaywrightError:
                    logger.warning("pdf: la tipografía no cargó, se usa la de respaldo")
                return pagina.pdf(
                    format="A4",
                    print_background=True,      # sin esto se pierde el vino de la cabecera
                    prefer_css_page_size=True,  # respeta el @page A4 de la plantilla
                )
            finally:
                navegador.close()
    except PlaywrightError as exc:
        raise PdfUnavailable(f"Chromium no disponible o falló el render: {str(exc)[:300]}") from exc
    finally:
        _UN_RENDER_A_LA_VEZ.release()


def available() -> bool:
    """Para /health. Cachea el resultado: arrancar un navegador por chequeo sería absurdo."""
    global _DISPONIBLE
    if _DISPONIBLE is not None:
        return _DISPONIBLE
    if not PDF_ENABLED:
        return False
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            p.chromium.launch(args=_ARGS, timeout=10000, **_destino()).close()
        _DISPONIBLE = True
    except Exception as exc:  # noqa: BLE001 — cualquier fallo significa "no disponible"
        logger.warning("pdf: navegador no disponible: %s", str(exc)[:200])
        _DISPONIBLE = False
    return _DISPONIBLE
