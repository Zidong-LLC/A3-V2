"""ERR-067d/e (chat real 2026-07-17, conversación Chatwoot #4): el pedido MIXTO en la
PRIMERA captura de análisis (no en la oferta '¿agregás otro?') perdía datos.
  - ERR-067d: 'Sodio potasio y orina' como primer pedido → `_enforce_multiple_tests_capture`
    absorbía sodio/potasio pero SE TRAGABA orina (ni la ofrecía ni la encolaba).
  - ERR-067e: 'perfil prequirúrgico' (categoría con 6 variantes) dado por NOMBRE → el
    early-return de `_looks_like_catalog_profile` lo dejaba como texto suelto sin código ni
    precio (se perdía del resumen). Un perfil ESPECÍFICO ('...I', '152') sí sigue su camino.
Tests de lógica pura sobre los mensajes reales, sin fingir el modelo (L51)."""
from unittest.mock import patch

from app.enforcers import orden as eorden

POTASIO = {"code": "1404", "name": "Potasio", "price": 12000, "category": "Minerales"}
SODIO = {"code": "1405", "name": "Sodio", "price": 12000, "category": "Minerales"}
URO = [{"code": "1601", "name": "Parcial de Orina (14 parámetros)", "price": 16000,
        "category": "Uroanálisis", "sample": "Orina Fresca"},
       {"code": "1602", "name": "Lectura Sedimento Urinario", "price": 7000,
        "category": "Uroanálisis", "sample": "Orina Fresca"}]
CATALOGO = [POTASIO, SODIO] + URO
PREQ = [{"code": "152", "name": "Perfil Prequirúrgico I", "price": 24000, "category": "Prequirúrgico"},
        {"code": "153", "name": "Perfil Prequirúrgico II", "price": 36000, "category": "Prequirúrgico"}]
SESSION = {"client_id": "c1"}


def _area(term, species=None, limit=10):
    return ("Uroanálisis", URO) if "orina" in term.lower() else (None, [])


def test_first_capture_mixed_absorbs_singles_and_offers_area():
    """ERR-067d: 'Sodio potasio y orina' de primer pedido → sodio y potasio quedan
    registrados con precio, y orina se OFRECE paso a paso (no se pierde)."""
    ai = {"intent": "route_scheduling",
          "captured_fields": {"_client_found": True, "exam_type": "Sodio potasio y orina"}}
    with patch.object(eorden.db, "list_catalog_tests", return_value=CATALOGO), \
         patch.object(eorden.db, "find_tests_by_area", side_effect=_area), \
         patch.object(eorden.db, "list_catalog_profiles_matching_category", return_value=[]):
        out = eorden._enforce_multiple_tests_capture(SESSION, ai, {})
    cf = out["captured_fields"]
    assert {"1404", "1405"} <= set(cf.get("selected_tests") or [])      # de opción única: absorbidos
    assert "ahora vamos con lo siguiente" in out["reply"].lower()        # el área se ofrece
    assert "uroanálisis" in out["reply"].lower() or "1601" in out["reply"]


def test_first_capture_only_singles_goes_straight_on():
    """Sin término de área ('Sodio y potasio') no debe inventar ningún menú: sigue el flujo."""
    ai = {"intent": "route_scheduling",
          "captured_fields": {"_client_found": True, "exam_type": "Sodio y potasio"}}
    with patch.object(eorden.db, "list_catalog_tests", return_value=CATALOGO), \
         patch.object(eorden.db, "find_tests_by_area", side_effect=_area), \
         patch.object(eorden.db, "list_catalog_profiles_matching_category", return_value=[]):
        out = eorden._enforce_multiple_tests_capture(SESSION, ai, {})
    cf = out["captured_fields"]
    assert {"1404", "1405"} <= set(cf.get("selected_tests") or [])
    assert "ahora vamos con lo siguiente" not in out["reply"].lower()
    assert not cf.get("_pending_ambiguous_items")


def test_first_capture_profile_category_by_name_offers_variants():
    """ERR-067e: 'perfil prequirúrgico' por nombre (6 variantes) ofrece los perfiles reales
    a elegir, en vez de quedar como texto suelto sin código ni precio."""
    ai = {"intent": "route_scheduling",
          "captured_fields": {"_client_found": True, "exam_type": "perfil prequirúrgico"}}
    with patch.object(eorden.db, "list_catalog_tests", return_value=CATALOGO), \
         patch.object(eorden.db, "list_catalog_profiles_matching_category", return_value=PREQ):
        out = eorden._enforce_loose_exam_catalog_resolution(ai, {})
    cf = out["captured_fields"]
    assert cf.get("_profile_menu_options")
    assert "152" in out["reply"] and "153" in out["reply"]


def test_first_capture_specific_profile_does_not_open_menu():
    """Un perfil ESPECÍFICO ('perfil prequirúrgico I') NO abre menú: sigue su anclaje propio."""
    ai = {"intent": "route_scheduling",
          "captured_fields": {"_client_found": True, "exam_type": "perfil prequirúrgico I"}}
    with patch.object(eorden.db, "list_catalog_tests", return_value=CATALOGO), \
         patch.object(eorden.db, "list_catalog_profiles_matching_category", return_value=PREQ):
        out = eorden._enforce_loose_exam_catalog_resolution(ai, {})
    cf = out["captured_fields"]
    assert not cf.get("_profile_menu_options")
    assert cf.get("exam_type")   # queda para _resolve_profile_base_if_missing
