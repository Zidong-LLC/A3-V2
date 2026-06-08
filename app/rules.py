from datetime import datetime, date, timedelta, timezone
from app.config import APP_TIMEZONE, CUTOFF_HOUR, CUTOFF_MINUTE, DISCOUNT_TIERS, CONVENIO_LABELS


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
    """Descuento por volumen según los tramos de DISCOUNT_TIERS.
    Aplica el porcentaje del mayor tramo cuyo mínimo de pruebas se alcanza.
    Si no hay tramos configurados, no hay descuento."""
    pct = 0.0
    for min_tests, tier_pct in sorted(DISCOUNT_TIERS):
        if num_tests >= min_tests:
            pct = tier_pct
    return int(round(subtotal * pct))


def is_convenio_test(row: dict) -> bool:
    """Las pruebas de convenio (parte final del portafolio) no reciben descuento
    por volumen ni cuentan para el tramo. Se identifican por su categoría o nombre."""
    text = f"{row.get('category') or ''} {row.get('name') or ''}".lower()
    return any(label.lower() in text for label in CONVENIO_LABELS)


def calculate_custom_profile_total(rows: list[dict]) -> dict:
    """Total de un perfil personalizado. El descuento por volumen solo aplica a
    las pruebas que NO son de convenio (estas se cobran a precio pleno)."""
    discountable = [r for r in rows if not is_convenio_test(r)]
    subtotal = sum(int(r.get("price") or 0) for r in rows)
    discountable_subtotal = sum(int(r.get("price") or 0) for r in discountable)
    discount = calculate_discount(len(discountable), discountable_subtotal)
    return {
        "count":    len(rows),
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
