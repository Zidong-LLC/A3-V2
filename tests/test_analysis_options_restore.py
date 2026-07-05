"""
Regresión (reporte del usuario, 2026-06-22): al pedir el análisis, cuando el cliente
respondía vago/por área/por síntoma ("no sé", "algo de orina", "dolor de panza"), el bot
DEJÓ de mostrar la lista seleccionable de perfiles/análisis con precios reales. El modelo
improvisaba la lista en el texto (sin menú detrás, no seleccionable, riesgo de inventar
precios) porque los guards de área/etiqueta dependían de que el AI guardara el término en
exam_type. Fix: usar el mensaje del usuario como respaldo + catch-all a perfiles por especie.
Ver RESUELTO-016.
"""
from unittest.mock import patch

from app import agent

URO = [
    {"code": "1601", "name": "Parcial de Orina", "price": 16000, "category": "Uroanálisis"},
    {"code": "1602", "name": "Urocultivo", "price": 28000, "category": "Uroanálisis"},
]
CANINE_PROFILES = [
    {"code": "151", "name": "Perfil General", "price": 32000, "description": "CH, Orina"},
    {"code": "202", "name": "Perfil Cachorros II", "price": 46000, "description": "CH, Parvo"},
]
HISTORY_ASKED_EXAM = [{"role": "bot", "content": "Por último, ¿qué análisis o perfil desean?"}]

BASE = {"_client_found": True, "species": "Canino"}


def _route_resp(fields):
    return agent._base_route_response("...", dict(fields))


def test_area_list_fires_from_user_message_when_exam_type_empty():
    """'algo de orina' con exam_type vacío igual despliega el menú de área seleccionable."""
    ai = _route_resp(BASE)
    with patch.object(agent.db, "find_tests_by_area", return_value=("Uroanálisis", URO)):
        out = agent._enforce_test_category_help(
            {"client_id": "c1"}, ai, dict(BASE), "algo de orina", HISTORY_ASKED_EXAM
        )
    assert out["captured_fields"]["_test_menu_options"]
    assert "1601" in out["reply"]


def test_diagnostic_label_fires_from_user_message_when_exam_type_empty():
    """'función renal' con exam_type vacío arranca el perfil por etiqueta diagnóstica."""
    ai = _route_resp(BASE)
    with patch.object(agent.db, "find_diagnostic_label", return_value="RENAL"), \
         patch.object(agent.db, "list_catalog_profiles_matching_category", return_value=[]), \
         patch.object(agent.db, "get_tests_for_label", return_value=URO), \
         patch.object(agent.db, "find_tests_by_area", return_value=(None, [])):
        out = agent._enforce_diagnostic_label_help(
            {"client_id": "c1"}, ai, "necesito función renal", dict(BASE), HISTORY_ASKED_EXAM
        )
    assert out["captured_fields"]["_diagnostic_label"] == "RENAL"


def test_vague_symptom_falls_back_to_species_profiles_menu():
    """'dolor de panza' sin área ni etiqueta cae a perfiles por especie SELECCIONABLES."""
    ai = _route_resp(BASE)
    with patch.object(agent.db, "get_tests_by_codes_or_names", return_value=[]), \
         patch.object(agent.db, "list_catalog_profiles_for_species", return_value=CANINE_PROFILES):
        out = agent._enforce_analysis_help_fallback(
            {"client_id": "c1"}, ai, dict(BASE), "algo raro para mi perro", HISTORY_ASKED_EXAM
        )
    assert out["captured_fields"]["_profile_menu_options"]
    assert "151" in out["reply"]


def test_specific_test_is_not_hijacked_by_fallback():
    """Si el cliente nombra un análisis del catálogo, el fallback NO muestra lista."""
    ai = _route_resp(BASE)
    with patch.object(agent.db, "get_tests_by_codes_or_names", return_value=URO), \
         patch.object(agent.db, "list_catalog_profiles_for_species", return_value=CANINE_PROFILES):
        out = agent._enforce_analysis_help_fallback(
            {"client_id": "c1"}, ai, dict(BASE), "un urocultivo", HISTORY_ASKED_EXAM
        )
    assert out["captured_fields"].get("_profile_menu_options") is None


def test_candidate_falls_back_to_message_only_when_asked_exam():
    """El respaldo al mensaje solo aplica si el bot acaba de pedir el análisis."""
    assert agent._analysis_help_candidate({}, {}, "algo de orina", HISTORY_ASKED_EXAM) == "algo de orina"
    other_hist = [{"role": "bot", "content": "¿Cuál es el nombre del paciente?"}]
    assert agent._analysis_help_candidate({}, {}, "algo de orina", other_hist) is None
    # Si el AI capturó exam_type nuevo, se usa ese.
    assert agent._analysis_help_candidate({"exam_type": "orina"}, {}, "x", other_hist) == "orina"
