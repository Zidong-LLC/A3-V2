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
"""
import time

from app.config import ALEGRA_ENABLED, APP_ENV, OPENAI_API_KEY
from app.services import alegra, db

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


def check_all() -> tuple[dict, int]:
    """Devuelve (payload, http_status). 503 solo si cae una dependencia crítica."""
    checks = {"supabase": _timed(db.ping)}

    checks["openai"] = {"status": "ok" if OPENAI_API_KEY else "not_configured"}

    if ALEGRA_ENABLED:
        checks["alegra"] = _timed(alegra.ping)
    else:
        checks["alegra"] = {"status": "disabled"}

    critical_down = checks["supabase"]["status"] == "error"
    degraded = any(c["status"] in ("error", "slow", "not_configured") for c in checks.values())

    if critical_down:
        status = "error"
    elif degraded:
        status = "degraded"
    else:
        status = "ok"

    return {"status": status, "env": APP_ENV, "checks": checks}, (503 if critical_down else 200)
