"""Resolución de motorizado por zona territorial — pura, sin I/O.

Recibe los datos del cliente (dirección y zona en texto libre) y las filas ya
leídas de Supabase; devuelve el motorizado que cubre esa ubicación o None.
Precedencia espejo del mapa del dashboard: la cobertura manual por localidad
(courier_locality_coverage) pisa al motorizado base de la zona
(territorial_zones). Sin geocoding: solo la cascada determinista de
territory.suggest_zone_for_location (barrio → dirección → localidad → zona).
"""
from app import territory


def _courier_id_from_coverage(locality_code: str | None, coverage_rows: list[dict]) -> str | None:
    if not locality_code:
        return None
    for row in coverage_rows or []:
        if str(row.get("locality_code") or "") == str(locality_code):
            payload = row.get("couriers") if isinstance(row.get("couriers"), dict) else {}
            courier_id = str(row.get("courier_id") or payload.get("id") or "").strip()
            return courier_id or None
    return None


def _courier_id_from_zone(zone_number: int | None, zone_rows: list[dict]) -> str | None:
    if not zone_number:
        return None
    for row in zone_rows or []:
        if row.get("zone_number") == zone_number:
            courier_id = str(row.get("courier_id") or "").strip()
            return courier_id or None
    return None


def resolve_zone_courier(
    *,
    address: str | None,
    zone_text: str | None,
    coverage_rows: list[dict],
    zone_rows: list[dict],
) -> dict | None:
    """Devuelve {courier_id, zone_number, locality_code, match_type, confidence,
    source} o None si la ubicación no se reconoce o la zona no tiene motorizado."""
    suggestion = territory.suggest_zone_for_location(
        locality=zone_text, zone=zone_text, address=address
    )
    if suggestion.get("match_type") == "none":
        return None

    locality_code = suggestion.get("locality_code")
    zone_number = suggestion.get("zone_number")

    courier_id = _courier_id_from_coverage(locality_code, coverage_rows)
    source = "coverage"
    if not courier_id:
        courier_id = _courier_id_from_zone(zone_number, zone_rows)
        source = "zone"
    if not courier_id:
        return None

    return {
        "courier_id": courier_id,
        "zone_number": zone_number,
        "locality_code": locality_code,
        "match_type": suggestion.get("match_type"),
        "confidence": suggestion.get("confidence"),
        "source": source,
    }
