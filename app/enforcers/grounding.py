"""Enforcers de ANCLAJE (grounding): lo capturado debe estar anclado a lo dicho."""
import re

from app.text import (
    tokenize as _tokenize, catalog_item_key as _catalog_item_key,
    strip_price_text as _strip_price_text,
)
from app.flow import (
    age_has_unit as _age_has_unit, missing_route_field_question as _missing_route_field_question,
)
from app.detectors import _is_same_as_previous



_EXAM_GROUNDING_STOPWORDS = frozenset({
    "perfil", "perfiles", "analisis", "análisis", "examen", "prueba", "pruebas",
    "canino", "canina", "felino", "felina", "completo", "completa", "test", "panel",
})


_AGE_UNIT_TOKENS = frozenset({
    "año", "años", "anio", "anios", "ano", "anos", "mes", "meses",
    "dias", "días", "semanas",
})



def enforce_exam_type_grounding(ai_response: dict, prev_fields: dict,
                                 user_message: str, history: list[dict]) -> dict:
    """QA-5 (2026-07-05): el modelo capturó un perfil que el cliente NUNCA nombró
    ('Perfil Senior Canino V' — $130.000 — ante un 'sin observaciones') y la orden se
    confirmó así. Un exam_type NUEVO debe estar anclado a lo que el cliente dijo (este
    mensaje o sus turnos recientes): si ningún token significativo del análisis aparece
    en el texto del cliente, se descarta y se pregunta el análisis en vez de inventarlo."""
    if ai_response.get("intent") != "route_scheduling":
        return ai_response
    fields = ai_response.get("captured_fields", {})
    exam = fields.get("exam_type")
    prev = prev_fields or {}
    if (not exam or exam == prev.get("exam_type")
            or fields.get("_diagnostic_label")
            or prev.get("_test_menu_options") or prev.get("_profile_menu_options")
            or prev.get("_selected_profile_code")
            or prev.get("selected_tests") is not None
            or prev.get("_profile_customizing")
            or _is_same_as_previous(user_message)):
        return ai_response
    snapshot = prev.get("_prev_order_snapshot") or {}
    if exam == snapshot.get("exam_type"):
        return ai_response
    user_text = " ".join(
        [user_message] + [m.get("content", "") for m in history if m.get("role") == "user"]
    )
    user_key = _catalog_item_key(user_text)
    tokens = [
        t for t in _catalog_item_key(_strip_price_text(str(exam))).split("_")
        if len(t) >= 4 and t not in _EXAM_GROUNDING_STOPWORDS
    ]
    if not tokens or any(t in user_key for t in tokens):
        return ai_response
    fields["exam_type"] = None
    fields["selected_tests"] = None
    fields["removed_tests"] = None
    reply = ai_response.get("reply") or ""
    if "análisis" not in reply.lower() and "perfil" not in reply.lower():
        ai_response["reply"] = _missing_route_field_question("exam_type")
    return ai_response



def enforce_age_unit_grounding(ai_response: dict, prev_fields: dict, user_message: str,
                                history: list[dict] | None = None) -> dict:
    """QA-3 (2026-07-05): el cliente dio la edad SIN unidad ('hembra, 2') y el modelo
    registró '2 años' inventando la unidad. Si la unidad no vino del cliente (ni en este
    mensaje ni en sus turnos recientes), se guarda solo el número y la regla existente
    (#10) la re-pregunta con ejemplos."""
    if ai_response.get("intent") != "route_scheduling":
        return ai_response
    fields = ai_response.get("captured_fields", {})
    age = fields.get("patient_age")
    if not age or age == (prev_fields or {}).get("patient_age"):
        return ai_response
    match = re.match(r"^\s*(\d{1,3})\s*(años?|anios?|meses?|d[ií]as?|semanas?)\s*$",
                     str(age), re.IGNORECASE)
    if not match:
        return ai_response
    user_texts = [user_message] + [
        m.get("content", "") for m in (history or []) if m.get("role") == "user"
    ]
    tokens = set()
    for text in user_texts:
        tokens |= set(_tokenize(text))
    if tokens & _AGE_UNIT_TOKENS:
        return ai_response
    if match.group(1) not in tokens:
        return ai_response  # el número no vino del cliente: no tocar
    fields["patient_age"] = match.group(1)
    return ai_response
