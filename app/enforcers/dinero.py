"""Enforcers de DINERO: invariantes duras antes de registrar una orden."""
from app.text import as_text_items
from app.services import db


def enforce_selected_tests_are_catalog_codes(ai_response: dict) -> dict:
    """Invariante I1 (red dura, corre justo antes de registrar): todo `selected_tests` es un
    CÓDIGO que existe en el catálogo. Descarta cualquier valor que no sea un código válido
    (texto libre o código inventado que se haya colado). Fail-safe: si no se puede leer el
    catálogo, no toca nada. Garantiza que ninguna orden se cree con un análisis fantasma
    ni un payload en $0, pase lo que pase en los guardrails anteriores."""
    fields = ai_response.get("captured_fields", {})
    codes = as_text_items(fields.get("selected_tests"))
    if not codes:
        return ai_response
    try:
        valid = {str(r.get("code")) for r in db.list_catalog_tests(limit=5000) if r.get("code")}
    except Exception:
        return ai_response
    if not valid:
        return ai_response
    kept = [c for c in codes if c in valid]
    if kept != codes:
        fields["selected_tests"] = kept
    return ai_response
