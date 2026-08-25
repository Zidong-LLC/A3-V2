"""ERR-067d/e (chat real 2026-07-17, conversación Chatwoot #4): el pedido MIXTO en la
PRIMERA captura de análisis (no en la oferta '¿agregás otro?') perdía datos.
  - ERR-067d: 'Sodio potasio y orina' como primer pedido → `_enforce_multiple_tests_capture`
    absorbía sodio/potasio pero SE TRAGABA orina (ni la ofrecía ni la encolaba).
  - ERR-067e: 'perfil prequirúrgico' (categoría con 6 variantes) dado por NOMBRE → el
    early-return de `_looks_like_catalog_profile` lo dejaba como texto suelto sin código ni
    precio (se perdía del resumen). Un perfil ESPECÍFICO ('...I', '152') sí sigue su camino.
Tests de lógica pura sobre los mensajes reales, sin fingir el modelo (L51)."""
import pytest
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


# ── ERR-076 (QA real 2026-07-21): PERFIL por categoría + análisis sueltos en el MISMO
# mensaje. "necesitamos un pre quirúrgico, un análisis de sodio y uno de potasio" dejaba la
# orden SOLO con sodio+potasio: el Perfil Prequirúrgico ($24.000) se perdía en silencio y el
# resumen previo a confirmar tampoco lo mostraba. Bug de DINERO.
#
# Es el hueco exacto entre los dos casos de arriba: hay cobertura de "sueltos + área"
# (ERR-067d) y de "perfil-categoría sola" (ERR-067e), pero NO de los dos juntos.
MIXTO = "necesitamos un pre quirúrgico, un análisis de sodio y uno de potasio"


def _profiles_by_category(text, species=None, limit=12):
    from app.services.db import filter_profiles_by_category_mention
    return filter_profiles_by_category_mention(PREQ, text)[:limit]


def test_mixed_profile_category_plus_singles_never_loses_the_profile():
    """El caso venenoso: el modelo NORMALIZA exam_type a 'Sodio, Potasio' (el perfil ya no
    figura ahí), así que el rescate tiene que mirar el MENSAJE del cliente, no exam_type.

    La garantía es "no perderlo en silencio": el prequirúrgico queda ofrecido en el menú
    (si se alcanzó a drenar la cola en este turno) o encolado para el turno siguiente."""
    ai = {"intent": "route_scheduling",
          "captured_fields": {"_client_found": True, "exam_type": "Sodio, Potasio"}}
    with patch.object(eorden.db, "list_catalog_tests", return_value=CATALOGO), \
         patch.object(eorden.db, "find_tests_by_area", side_effect=_area), \
         patch.object(eorden.db, "list_catalog_profiles_matching_category", side_effect=_profiles_by_category):
        out = eorden._enforce_multiple_tests_capture(SESSION, ai, {}, MIXTO)
    cf = out["captured_fields"]
    assert {"1404", "1405"} <= set(cf.get("selected_tests") or []), "sodio y potasio se absorben"
    ofrecido = bool(cf.get("_profile_menu_options")) or bool(cf.get("_pending_ambiguous_items"))
    assert ofrecido, "el prequirúrgico NO puede perderse en silencio"
    assert "152" in out["reply"] and "153" in out["reply"], "las variantes se listan para elegir"


def test_mixed_without_a_profile_mention_opens_no_menu():
    """No-regresión: si el cliente NO pidió un perfil, no se inventa ningún menú."""
    ai = {"intent": "route_scheduling",
          "captured_fields": {"_client_found": True, "exam_type": "Sodio, Potasio"}}
    with patch.object(eorden.db, "list_catalog_tests", return_value=CATALOGO), \
         patch.object(eorden.db, "find_tests_by_area", side_effect=_area), \
         patch.object(eorden.db, "list_catalog_profiles_matching_category", side_effect=_profiles_by_category):
        out = eorden._enforce_multiple_tests_capture(SESSION, ai, {}, "sodio y potasio por favor")
    cf = out["captured_fields"]
    assert {"1404", "1405"} <= set(cf.get("selected_tests") or [])
    assert not cf.get("_profile_menu_options")
    assert not cf.get("_pending_ambiguous_items")


def _orden_completa(**extra) -> dict:
    """Orden con TODOS los campos resueltos: así el único motivo posible de no-cierre es
    el residuo pendiente, no un campo faltante."""
    base = {"_client_found": True, "pickup_address": "Cra 15 #80-20",
            "requesting_doctor": "Dra Ana", "patient_name": "Pepe", "species": "Caprino",
            "breed": "Sin determinar", "sex": "Hembra", "patient_age": "3 años",
            "owner_name": "Juan", "sample_taken_date": "hoy", "observations": "ninguna", "exam_type": "Sodio, Potasio",
            "selected_tests": ["1404", "1405"], "payment_method": "contraentrega"}
    base.update(extra)
    return base


def test_a_complete_order_without_pending_items_does_close():
    """Control: sin residuo, la misma orden completa SÍ cierra. Aísla la causa del test siguiente."""
    from app import agent
    fields = _orden_completa()
    ai = {"intent": "route_scheduling", "phase": "fase_6_cierre",
          "reply": "Quedó registrado.", "captured_fields": fields}
    out = agent._prevent_incomplete_route_closure(SESSION, ai, fields)
    assert "quedó registrado" in out["reply"].lower()


def test_mixed_request_never_closes_with_a_pending_item():
    """La garantía de dinero: con residuo encolado la orden NO puede llegar a fase terminal,
    aunque todos los campos estén completos."""
    from app import agent
    fields = _orden_completa(_pending_ambiguous_items=["un pre quirúrgico"])
    ai = {"intent": "route_scheduling", "phase": "fase_6_cierre",
          "reply": "Quedó registrado.", "captured_fields": fields}
    out = agent._prevent_incomplete_route_closure(SESSION, ai, fields)
    assert "quedó registrado" not in out["reply"].lower(), "no puede cerrar con residuo pendiente"


def test_pending_item_is_dropped_after_three_offers():
    """Salida de emergencia: si el cliente nunca resuelve el pendiente, tras 3 ofertas se
    descarta con acuse en vez de trabar la orden para siempre (lección de ERR-074)."""
    from app import agent
    fields = _orden_completa(_pending_ambiguous_items=["un pre quirúrgico"])
    ai = {"intent": "route_scheduling", "phase": "fase_6_cierre",
          "reply": "Quedó registrado.", "captured_fields": fields}
    for _ in range(agent._MAX_PENDING_OFFERS):
        out = agent._prevent_incomplete_route_closure(SESSION, dict(ai, captured_fields=fields), fields)
        assert "quedó registrado" not in out["reply"].lower()
    out = agent._prevent_incomplete_route_closure(SESSION, dict(ai, captured_fields=fields), fields)
    assert "quedó registrado" in out["reply"].lower(), "tras el tope, la orden avanza"
    assert not fields.get("_pending_ambiguous_items")


def test_choosing_the_profile_clears_it_from_the_pending_queue():
    """Bug del propio fix (riesgo R3 del plan): al reaplicar el pedido original tras elegir
    el perfil, se re-escaneaban los términos ambiguos y el prequirúrgico RECIÉN RESUELTO
    volvía a la cola. El guard de cierre entonces trababa la orden pidiendo algo ya elegido."""
    from app import orders
    fields = {"_client_found": True, "selected_tests": [],
              "_pending_ambiguous_items": ["un pre quirúrgico"],
              "_mixed_request_text": MIXTO}
    with patch.object(orders.db, "get_catalog_profiles_by_codes", return_value=[PREQ[0]]), \
         patch.object(orders.db, "list_catalog_tests", return_value=CATALOGO), \
         patch.object(orders.db, "find_tests_by_area", side_effect=_area), \
         patch.object(orders.db, "list_catalog_profiles_matching_category", side_effect=_profiles_by_category):
        orders._capture_profile_menu_selection(SESSION, fields, PREQ[0], "el 1")

    assert not fields.get("_pending_ambiguous_items"), "el perfil elegido sale de la cola"
    assert fields.get("_selected_profile_code") == "152"
    assert {"1404", "1405"} <= set(fields.get("selected_tests") or []), \
        "los sueltos del pedido original se agregan sobre el perfil base"


# ── La REGLA GENERAL, no el caso puntual ──────────────────────────────────────
# Elegir de un menú REEMPLAZA si el menú fue una elección desde cero, pero AGREGA si el menú
# se abrió como residuo de un pedido mixto. La señal es DE DÓNDE VINO el menú, no qué palabra
# se pidió: vale igual para un área ("orina"), una categoría de perfiles ("prequirúrgico") o
# cualquier menú futuro.

def _pedido_mixto(mensaje, exam_type="Sodio, Potasio"):
    ai = {"intent": "route_scheduling",
          "captured_fields": {"_client_found": True, "exam_type": exam_type}}
    with patch.object(eorden.db, "list_catalog_tests", return_value=CATALOGO), \
         patch.object(eorden.db, "find_tests_by_area", side_effect=_area), \
         patch.object(eorden.db, "list_catalog_profiles_matching_category", side_effect=_profiles_by_category):
        return eorden._enforce_multiple_tests_capture(SESSION, ai, {}, mensaje)["captured_fields"]


def test_menu_from_a_mixed_request_adds_instead_of_replacing():
    """AREA + sueltos: al elegir del menú, sodio y potasio NO pueden desaparecer."""
    from app import agent
    cf = _pedido_mixto("necesitamos un análisis de orina, sodio y potasio")
    assert {"1404", "1405"} <= set(cf.get("selected_tests") or []), "los sueltos se absorben primero"
    with patch.object(agent.db, "get_tests_by_codes", return_value=[URO[0]]), \
         patch.object(agent.db, "list_catalog_tests", return_value=CATALOGO):
        agent._capture_test_menu_selection(SESSION, cf, [URO[0]])
    assert {"1404", "1405", "1601"} <= set(cf.get("selected_tests") or []), \
        "los tres pedidos sobreviven a la selección del menú"


def test_menu_chosen_from_scratch_still_replaces():
    """No-regresión: un menú que NO viene de un pedido mixto sigue reemplazando (era el
    comportamiento correcto y el resumen depende de él)."""
    from app import agent
    cf = {"_client_found": True, "selected_tests": ["9999"],
          "_test_menu_options": [{"code": "1601"}]}
    with patch.object(agent.db, "get_tests_by_codes", return_value=[URO[0]]), \
         patch.object(agent.db, "list_catalog_tests", return_value=CATALOGO):
        agent._capture_test_menu_selection(SESSION, cf, [URO[0]])
    assert cf.get("selected_tests") == ["1601"], "elección desde cero reemplaza"
    assert "9999" not in (cf.get("selected_tests") or [])


# ── ERR-087 (chat real 2026-07-22, conversación Chatwoot #4) ─────────────────────────
# 'Necesito análisis de sangre u orina, sodio y potasio' → el MODELO resumió exam_type a
# "análisis de sangre" (UN término vago) y la compuerta `< 2 ítems` devolvía el turno sin
# mirar el mensaje real: sodio/potasio se perdían y el cliente tenía que repetir todo.

HEMO = {"code": "0301", "name": "Hemograma", "price": 25000, "category": "Hematología"}


def test_err087_modelo_resume_a_termino_vago_no_pierde_el_pedido():
    """El caso real: exam_type vago de 1 ítem, pero el mensaje CRUDO trae 2 exactos + área
    → sodio y potasio quedan registrados y el área pendiente se ofrece (no se pierde nada)."""
    ai = {"intent": "route_scheduling",
          "captured_fields": {"_client_found": True, "exam_type": "análisis de sangre"}}
    with patch.object(eorden.db, "list_catalog_tests", return_value=CATALOGO + [HEMO]), \
         patch.object(eorden.db, "find_tests_by_area", side_effect=_area), \
         patch.object(eorden.db, "list_catalog_profiles_matching_category", return_value=[]):
        out = eorden._enforce_multiple_tests_capture(
            SESSION, ai, {}, "Necesito análisis de sangre u orina , sodio y potasio")
    cf = out["captured_fields"]
    assert {"1404", "1405"} <= set(cf.get("selected_tests") or []), "sodio/potasio se perdieron"
    resto = (out.get("reply") or "").lower()
    assert cf.get("_pending_ambiguous_items") or "uroanálisis" in resto or "1601" in resto, \
        "el término de área del pedido se tragó en silencio"


def test_err087_un_analisis_suelto_sigue_el_flujo_normal():
    """Control: 'quiero un hemograma' (1 exacto, sin pendientes) NO dispara el carril
    mixto — sigue el flujo normal de análisis suelto."""
    ai = {"intent": "route_scheduling",
          "captured_fields": {"_client_found": True, "exam_type": "Hemograma"}}
    with patch.object(eorden.db, "list_catalog_tests", return_value=CATALOGO + [HEMO]), \
         patch.object(eorden.db, "find_tests_by_area", side_effect=_area), \
         patch.object(eorden.db, "list_catalog_profiles_matching_category", return_value=[]):
        out = eorden._enforce_multiple_tests_capture(SESSION, ai, {}, "quiero un hemograma")
    assert not out["captured_fields"].get("selected_tests"), \
        "un análisis suelto no debe convertirse en perfil personalizado acá"


def test_err087_un_exacto_mas_area_tambien_se_rescata():
    """'un hemograma y algo de orina' con exam_type resumido: el exacto se registra y el
    área queda ofrecida/encolada."""
    ai = {"intent": "route_scheduling",
          "captured_fields": {"_client_found": True, "exam_type": "hemograma"}}
    with patch.object(eorden.db, "list_catalog_tests", return_value=CATALOGO + [HEMO]), \
         patch.object(eorden.db, "find_tests_by_area", side_effect=_area), \
         patch.object(eorden.db, "list_catalog_profiles_matching_category", return_value=[]):
        out = eorden._enforce_multiple_tests_capture(
            SESSION, ai, {}, "necesito un hemograma y algo de orina")
    cf = out["captured_fields"]
    resto = (out.get("reply") or "").lower()
    assert "0301" in set(cf.get("selected_tests") or []), "el hemograma no quedó registrado"
    assert cf.get("_pending_ambiguous_items") or "uroanálisis" in resto or "1601" in resto
