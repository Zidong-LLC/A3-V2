"""Tramos del descuento por volumen leídos de Supabase, con cache y fallback.

`calculate_discount` (app/rules.py) corre en cada turno del agente: no puede
pegarle a Supabase cada vez. Este módulo cachea los tramos 60 segundos y los
invalida explícitamente cuando el dashboard los edita (mismo proceso Flask →
efecto inmediato; con más workers el TTL acota el desfase a 1 minuto).

Fallback duro: tabla vacía o Supabase caído → tramos de config.DISCOUNT_TIERS.
El agente nunca cotiza sin descuento por un fallo de infraestructura.

Al importarse registra el provider en rules (rules no importa pricing: la
dependencia va en un solo sentido y rules sigue siendo puro).
"""
import logging
import time

from app import rules
from app.config import DISCOUNT_TIERS

logger = logging.getLogger(__name__)

_TTL_SECONDS = 60
_cache: dict = {"tiers": None, "loaded_at": 0.0}


def get_discount_tiers() -> list[tuple[int, float]]:
    """Tramos vigentes como [(min_tests, pct)]. Nunca lanza."""
    now = time.monotonic()
    if _cache["tiers"] is not None and now - _cache["loaded_at"] < _TTL_SECONDS:
        return _cache["tiers"]
    try:
        from app.services import db

        rows = db.list_discount_tiers()
        tiers = [(int(r["min_tests"]), float(r["pct"])) for r in rows]
    except Exception as exc:
        logger.warning("no se pudieron leer los tramos de descuento: %s", exc)
        tiers = []
    if not tiers:
        # El fallback también se cachea: si Supabase está caído no se reintenta
        # la query en cada turno del agente.
        tiers = list(DISCOUNT_TIERS)
    _cache["tiers"] = tiers
    _cache["loaded_at"] = now
    return tiers


def invalidate_discount_tiers_cache() -> None:
    _cache["tiers"] = None
    _cache["loaded_at"] = 0.0


rules.set_discount_tiers_provider(get_discount_tiers)
