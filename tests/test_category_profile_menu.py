"""
Regresión ERR-045 (prueba del usuario, 2026-07-03, chat 4): el cliente pidió un perfil
prequirúrgico y el bot recomendó perfiles genéricos por especie (Cachorros para una perra
de 2 años) aunque el catálogo tiene 11 perfiles Prequirúrgicos armados (152-162); luego,
con la etiqueta PREQUIRURGICO activa, ante "¿no tienes perfiles armados?" re-preguntó la
especie ya capturada y el turno siguiente saltó al pago con un exam_type inexistente en
el catálogo (sin análisis concretos ni valor en el resumen). Fix: menú determinista de
perfiles armados por categoría nombrada, antes de la lista por especie y de las pruebas
sueltas por etiqueta.
"""
from unittest.mock import patch

from app import agent
from app.services import db as db_module

PREQ_PROFILES = [
    {"code": "152", "name": "Perfil Prequirúrgico I", "price": 24000,
     "category": "Prequirúrgico", "species": "ambos", "description": "CH, PT"},
    {"code": "153", "name": "Perfil Prequirúrgico II", "price": 36000,
     "category": "Prequirúrgico", "species": "ambos", "description": "CH, PT, PTT"},
]
CACHORROS = {"code": "202", "name": "Perfil Cachorros II", "price": 46000,
             "category": "Cachorros", "species": "canino", "description": "CH, Parvo"}
URO = [
    {"code": "1601", "name": "Parcial de Orina", "price": 16000, "category": "Uroanálisis"},
]
BASE = {"_client_found": True, "species": "Canino"}
HISTORY_ASKED_EXAM = [{"role": "bot", "content": "Por último, ¿qué análisis o perfil desean?"}]


def _route_resp(fields):
    return agent._base_route_response("...", dict(fields))


def test_filter_matches_category_without_accents_or_spaces():
    """'pre quirúrgico' (con espacio y tilde) matchea la categoría 'Prequirúrgico'."""
    rows = PREQ_PROFILES + [CACHORROS]
    out = db_module.filter_profiles_by_category_mention(
        rows, "Cual me recomiendas pre quirúrgico q perfil tienen?"
    )
    assert [r["code"] for r in out] == ["152", "153"]


def test_filter_returns_empty_without_category_mention():
    rows = PREQ_PROFILES + [CACHORROS]
    assert db_module.filter_profiles_by_category_mention(rows, "no sé qué pedir") == []


def test_recommendation_with_named_category_offers_armed_profiles():
    """'recomiéndame pre quirúrgico' ofrece los perfiles de ESA categoría, no la
    lista genérica por especie (que mostraba Cachorros)."""
    ai = _route_resp(BASE)
    with patch.object(agent.db, "list_catalog_profiles_matching_category",
                      return_value=PREQ_PROFILES), \
         patch.object(agent.db, "list_catalog_profiles_for_species",
                      return_value=[CACHORROS]):
        out = agent._enforce_profile_recommendation_help(
            {"client_id": "c1"}, ai, "Cual me recomiendas pre quirúrgico q perfil tienen?",
            HISTORY_ASKED_EXAM,
        )
    codes = [o["code"] for o in out["captured_fields"]["_profile_menu_options"]]
    assert codes == ["152", "153"]
    assert "152" in out["reply"] and "202" not in out["reply"]


def test_diagnostic_label_help_prefers_armed_profiles_over_loose_tests():
    """Si la etiqueta (ej. PREQUIRURGICO) tiene perfiles armados en el catálogo, se
    ofrecen esos en menú; no se arranca el armado a medida con pruebas sueltas."""
    ai = _route_resp(BASE)
    with patch.object(agent.db, "find_diagnostic_label", return_value="PREQUIRURGICO"), \
         patch.object(agent.db, "list_catalog_profiles_matching_category",
                      return_value=PREQ_PROFILES):
        out = agent._enforce_diagnostic_label_help(
            {"client_id": "c1"}, ai, "necesito un prequirurgico", dict(BASE), HISTORY_ASKED_EXAM
        )
    assert out["captured_fields"].get("_diagnostic_label") is None
    assert out["captured_fields"]["_profile_menu_options"]
    assert "armamos a medida" in out["reply"]


def test_diagnostic_label_help_keeps_loose_tests_when_no_armed_profiles():
    """Sin perfiles armados de la categoría, el flujo de etiqueta sigue igual que antes."""
    ai = _route_resp(BASE)
    with patch.object(agent.db, "find_diagnostic_label", return_value="RENAL"), \
         patch.object(agent.db, "list_catalog_profiles_matching_category", return_value=[]), \
         patch.object(agent.db, "get_tests_for_label", return_value=URO), \
         patch.object(agent.db, "find_tests_by_area", return_value=(None, [])):
        out = agent._enforce_diagnostic_label_help(
            {"client_id": "c1"}, ai, "necesito función renal", dict(BASE), HISTORY_ASKED_EXAM
        )
    assert out["captured_fields"]["_diagnostic_label"] == "RENAL"


def test_armed_profiles_question_with_active_label_shows_category_menu():
    """Con la etiqueta activa, '¿no tienes perfiles armados?' muestra el menú de la
    categoría sin re-preguntar la especie ya capturada (turno 16:29:49 del reporte)."""
    fields = dict(BASE, _diagnostic_label="PREQUIRURGICO", selected_tests=[], removed_tests=[])
    with patch.object(agent.db, "list_catalog_profiles_matching_category",
                      return_value=PREQ_PROFILES):
        out = agent._diagnostic_label_profile_turn({"client_id": "c1"}, fields, "No tienes perfiles armados?")
    assert out is not None
    assert out["captured_fields"]["_profile_menu_options"]
    assert out["captured_fields"].get("_diagnostic_label") is None
    assert "especie" not in out["reply"].lower()
    assert "pago" not in out["reply"].lower()


def test_asks_for_armed_profiles_detector():
    assert agent._asks_for_armed_profiles("No tienes perfiles armados?")
    assert agent._asks_for_armed_profiles("¿hay perfiles prearmados?")
    assert not agent._asks_for_armed_profiles("quiero armar un perfil")
    assert not agent._asks_for_armed_profiles("ya te dije q especie es")


# ── ERR-048: "Tienes perfiles pre quirúrgico?" (con espacio) — prueba real 2026-07-03 ──
# La etiqueta diagnóstica no matchea "pre quirúrgico" separado, así que el flujo caía al
# menú genérico por especie y encima _enforce_first_missing_after_progress lo pisaba con
# "Perfecto, lo anoto. ¿qué análisis o perfil desean?".


def test_category_menu_fires_even_when_label_lookup_fails():
    """Sin etiqueta resuelta ('pre quirúrgico' con espacio), la mención de la categoría
    en el mensaje igual ofrece los perfiles armados."""
    ai = _route_resp(BASE)
    with patch.object(agent.db, "find_diagnostic_label", return_value=None), \
         patch.object(agent.db, "list_catalog_profiles_matching_category",
                      return_value=PREQ_PROFILES):
        out = agent._enforce_diagnostic_label_help(
            {"client_id": "c1"}, ai, "Tienes perfiles pre quirúrgico?", dict(BASE), HISTORY_ASKED_EXAM
        )
    codes = [o["code"] for o in out["captured_fields"]["_profile_menu_options"]]
    assert codes == ["152", "153"]


def test_first_missing_guard_does_not_stomp_profile_menu():
    """Con un menú de perfiles recién ofrecido, la plantilla del dato faltante NO
    reemplaza la respuesta (el menú ES la pregunta del análisis)."""
    fields = dict(BASE, _profile_menu_options=[{"code": "152", "name": "x", "price": 1}],
                  observations="sin observaciones")
    ai = agent._base_route_response("Para prequirúrgico tenemos estos perfiles armados: ...", fields)
    prev = dict(BASE)  # observations cambió en este turno -> progressed=True
    out = agent._enforce_first_missing_after_progress({"client_id": "c1"}, ai, prev)
    assert out["reply"].startswith("Para prequirúrgico")
