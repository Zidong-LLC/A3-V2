"""Chequeo de salud real de las dependencias del agente.

Antes /health devolvía {"status": "ok"} fijo: respondía OK aunque Supabase
estuviera caído, así que un monitor externo no se enteraba de nada. Acá se
consulta de verdad cada dependencia y se distingue lo que tumba el servicio
de lo que solo lo degrada.

- Supabase es CRÍTICO: sin base no hay sesión, ni cliente, ni orden.
- OpenAI se reporta como configurado/no configurado: no se le pega en cada
  chequeo porque cada llamada cuesta dinero y agrega latencia.
- Alegra es opcional y solo se chequea si está habilitado; que falle degrada
  la facturación, no la recogida de muestras.
- Anarvet ídem: es una base externa fuera de nuestro control; que caiga degrada
  el sync del espejo de resultados, nunca tumba el servicio.

DOS chequeos, a propósito (2026-09-04):

`check_liveness()` es el que mira Render cada pocos segundos: solo Supabase, que
es lo único sin lo cual el servicio no sirve para nada. Tiene que ser RÁPIDO.

`check_all()` es el completo, para mirar a mano o desde un monitor externo.

Por qué se separaron: el completo tarda 2,5-3 s porque llama a la API de Alegra
(~1,5 s) y abre una conexión a la base de Anarvet en Colombia (~1,1 s). Render
corta a los 5 s: un pico de cualquiera de los dos hacía que diera timeout, Render
daba por muerta la instancia y la REINICIABA — cortando las conversaciones en
curso (el buffer anti-ráfagas vive en memoria del proceso). Además le abríamos una
conexión a Anarvet cada pocos segundos, con un usuario que nos dieron de solo
lectura para un sync esporádico.
"""
import time
from concurrent.futures import ThreadPoolExecutor

from app.config import ALEGRA_ENABLED, ANARVET_ENABLED, APP_ENV, OPENAI_API_KEY, PDF_ENABLED
from app.services import alegra, anarvet, db, pdf

# Un chequeo lento es un chequeo que falla: si Supabase tarda más que esto,
# al monitor le sirve más un aviso que una espera.
_SLOW_MS = 2000


def _timed(check_fn) -> dict:
    started = time.monotonic()
    try:
        check_fn()
        elapsed = int((time.monotonic() - started) * 1000)
        status = "slow" if elapsed > _SLOW_MS else "ok"
        return {"status": status, "latency_ms": elapsed}
    except Exception as e:  # noqa: BLE001 — cualquier fallo es un fallo de salud
        elapsed = int((time.monotonic() - started) * 1000)
        return {"status": "error", "latency_ms": elapsed, "error": str(e)[:200]}


def check_liveness() -> tuple[dict, int]:
    """Chequeo LIVIANO para el health check de Render: ¿está vivo y con base?

    Solo Supabase, que es la única dependencia sin la cual el servicio no puede
    hacer nada. Alegra, Anarvet y el PDF degradan funciones puntuales pero no
    justifican reiniciar el servicio — y son justamente los lentos."""
    supabase = _timed(db.ping)
    caida = supabase["status"] == "error"
    return ({"status": "error" if caida else "ok", "env": APP_ENV,
             "checks": {"supabase": supabase}},
            503 if caida else 200)


def check_all() -> tuple[dict, int]:
    """Devuelve (payload, http_status). 503 solo si cae una dependencia crítica."""
    # Las tres dependencias de red a la vez: en serie sumaban ~3,5 s (Alegra ~1,7 s y
    # Anarvet ~1,4 s); así el completo tarda lo que la más lenta.
    with ThreadPoolExecutor(max_workers=3) as hilos:
        supabase_f = hilos.submit(_timed, db.ping)
        alegra_f = hilos.submit(_timed, alegra.ping) if ALEGRA_ENABLED else None
        anarvet_f = hilos.submit(_timed, anarvet.ping) if ANARVET_ENABLED else None
    checks = {"supabase": supabase_f.result()}

    checks["openai"] = {"status": "ok" if OPENAI_API_KEY else "not_configured"}
    checks["alegra"] = alegra_f.result() if alegra_f else {"status": "disabled"}
    checks["anarvet"] = anarvet_f.result() if anarvet_f else {"status": "disabled"}

    # Solo hace falta para PUBLICAR un informe al portal; ver e imprimir no depende de esto.
    # Degrada, nunca tumba: que no se pueda armar un PDF no puede callar el bot.
    if PDF_ENABLED:
        checks["pdf"] = {"status": "ok" if pdf.available() else "error"}
    else:
        checks["pdf"] = {"status": "disabled"}

    critical_down = checks["supabase"]["status"] == "error"
    degraded = any(c["status"] in ("error", "slow", "not_configured") for c in checks.values())

    if critical_down:
        status = "error"
    elif degraded:
        status = "degraded"
    else:
        status = "ok"

    return {"status": status, "env": APP_ENV, "checks": checks}, (503 if critical_down else 200)
