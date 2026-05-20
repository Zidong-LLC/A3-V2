from datetime import datetime, date, timedelta, timezone
from app.config import APP_TIMEZONE, CUTOFF_HOUR, CUTOFF_MINUTE


def get_scheduled_pickup_date(now: datetime = None) -> date:
    """
    Regla de corte 17:30 hora Colombia:
    - Antes del corte → siguiente día hábil
    - Después del corte → el día hábil que sigue al siguiente
    """
    if now is None:
        now = datetime.now(timezone.utc)
    local = now.astimezone(APP_TIMEZONE)
    cutoff = local.replace(hour=CUTOFF_HOUR, minute=CUTOFF_MINUTE, second=0, microsecond=0)

    base = local.date() + timedelta(days=1)
    pickup = _next_business_day(base)

    if local > cutoff:
        pickup = _next_business_day(pickup + timedelta(days=1))

    return pickup


def _next_business_day(d: date) -> date:
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


INTENT_TO_SERVICE_AREA = {
    "route_scheduling": "route_scheduling",
    "results":          "results",
    "accounting":       "accounting",
    "new_client":       "new_client",
    "unknown":          "unknown",
}

ESCALATED_INTENTS = {"accounting", "new_client"}

DONE_PHASES = {"fase_6_cierre"}
ESCALATED_PHASES = {"fase_7_escalado"}
TERMINAL_PHASES = DONE_PHASES | ESCALATED_PHASES


def calculate_discount(num_tests: int, subtotal: int) -> int:
    # Placeholder: las reglas de descuento por cantidad no están definidas todavía.
    # Cuando lleguen los tramos del cliente, implementar acá.
    return 0


def calculate_custom_profile_total(prices: list[int]) -> dict:
    subtotal = sum(prices)
    discount = calculate_discount(len(prices), subtotal)
    return {
        "count":    len(prices),
        "subtotal": subtotal,
        "discount": discount,
        "total":    subtotal - discount,
    }


def calculate_profile_adjusted_total(base_price: int, added_prices: list[int], removed_prices: list[int]) -> dict:
    added = sum(added_prices)
    removed = sum(removed_prices)
    return {
        "base":    base_price,
        "added":   added,
        "removed": removed,
        "total":   max(base_price + added - removed, 0),
    }
