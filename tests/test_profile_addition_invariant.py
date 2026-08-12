"""
Regresión ERR-050 (chat 4 real, 2026-07-04): agregar un análisis a un perfil ya elegido.

Cinco fallos reproducidos en la conversación real (perfil 152 seleccionado, falta pago):
1. "quiero agregarle un analisis mas a este perfil" → mostraba el menú de perfiles
   recomendados por especie (Perfiles Cachorros) en vez de preguntar cuál agregar.
2. "quiero el perfil 152 y agregarle un analisis mas a este si ?" → repetía el mismo menú.
3. "quiero agregarle un analisis de orina al perfil" → fuzzy-match a un test suelto
   ("Listo, agrego 1507-Cortisol en Orina $33k") sin confirmar, en vez del menú del área.
4. "que analisis de orina hacen?" → muestrario mixto de todas las áreas que además
   BORRABA selected_tests y exam_type (el Cortisol desapareció en silencio).
5. Resumen final: "Perfil Prequirúrgico I — $24.000" — el Parcial de Orina agregado
   quedó solo como texto en exam_type, selected_tests vacío, y el total perdió $16.000.

Invariante que estos tests protegen: todo agregado vive en selected_tests (estructurado)
y el resumen/total sale SIEMPRE de la estructura. Ver errores-soluciones.md (ERR-050).
"""
from unittest.mock import patch

from app import agent

PROFILE_152 = {
    "code": "152", "name": "Perfil Prequirúrgico I", "species": "ambos",
    "description": "Cuadro Hemático, ALT, Creatinina", "price": 24000,
}
CACHORROS = [
    {"code": "202", "name": "Perfil Cachorros II", "price": 46000},
    {"code": "203", "name": "Perfil Cachorros III", "price": 113000},
]
URO_TESTS = [
    {"code": "1507", "name": "Cortisol en Orina", "price": 33000, "category": "Uroanálisis"},
    {"code": "1601", "name": "Parcial de Orina (14 parámetros)", "price": 16000, "category": "Uroanálisis"},
    {"code": "1602", "name": "Lectura Sedimento Urinario", "price": 21000, "category": "Uroanálisis"},
    {"code": "2102", "name": "Urocultivo y Antibiograma", "price": 46000, "category": "Uroanálisis"},
]
MIXED_SAMPLER = [
    {"code": "1101", "name": "Cuadro Hemático Completo", "price": 14000, "category": "Hematología"},
    {"code": "1601", "name": "Parcial de Orina (14 parámetros)", "price": 16000, "category": "Uroanálisis"},
]

# Estado tras elegir "el 1" del menú de prequirúrgicos (como en la conversación real).
BASE_FIELDS = {
    "_client_found": True,
    "clinic_name": "Pet Agro Colombia",
    "pickup_address": "CL 78C SUR 18G 67",
    "_address_confirmed": True,
    "requesting_doctor": "Dr. Alcojor",
    "patient_name": "Anahi",
    "species": "Canino",
    "breed": "Pitbull",
    "sex": "Hembra",
    "patient_age": "7 años",
    "owner_name": "Gaston",
    "observations": "sin observaciones",
    "exam_type": "Perfil Prequirúrgico I",
    "_selected_profile_code": "152",
    "_selected_profile_name": "Perfil Prequirúrgico I",
    "_selected_profile_price": 24000,
    "_offering_extra_analysis": True,
}


def _fake_tests_lookup(items):
    """Réplica del matching real: código exacto o substring del nombre normalizado."""
    out, seen = [], set()
    for item in items:
        key = agent._catalog_item_key(item)
        if not key:
            continue
        for row in URO_TESTS + MIXED_SAMPLER:
            row_code = str(row["code"])
            name_key = agent._catalog_item_key(row["name"])
            if (key == row_code or key == name_key or key in name_key) and row_code not in seen:
                out.append(row)
                seen.add(row_code)
                break
    return out


def _fake_area(value, species=None, limit=15):
    if "orina" in agent._catalog_item_key(value):
        return "Uroanálisis", URO_TESTS[:limit]
    return None, []


def _run_turn(fields, user_message):
    """Corre el turno determinista de la oferta de agregado (sin AI), como en process_turn."""
    session = {"client_id": "client-A"}
    with patch.object(agent.db, "find_tests_by_area", side_effect=_fake_area), \
         patch.object(agent.db, "get_tests_by_codes_or_names", side_effect=_fake_tests_lookup), \
         patch.object(agent.db, "get_tests_by_codes", side_effect=_fake_tests_lookup), \
         patch.object(agent.db, "get_catalog_profiles_by_codes", return_value=[PROFILE_152]), \
         patch.object(agent.db, "list_catalog_profiles_for_species", return_value=CACHORROS):
        return agent._handle_extra_analysis_answer(session, fields, user_message)


def test_add_unspecified_asks_which_not_profile_menu():
    """Error 1: 'agregarle un análisis más a este perfil' pregunta CUÁL agregar;
    nunca ofrece perfiles nuevos por especie (Cachorros)."""
    fields = dict(BASE_FIELDS)
    out = _run_turn(fields, "quiero agregarle un analisis mas a este perfil")
    assert out is not None
    assert "recomendar" not in out["reply"].lower()
    assert "cachorros" not in out["reply"].lower()
    assert out["captured_fields"].get("_profile_menu_options") is None
    assert out["captured_fields"].get("_awaiting_additional_test") == "add"
    assert out["captured_fields"]["_selected_profile_code"] == "152"


def test_add_with_profile_code_keeps_profile_and_asks_which():
    """Error 2: 'el perfil 152 y agregarle un análisis más' mantiene el 152 y pregunta
    cuál agregar, sin repetir el menú de recomendación."""
    fields = dict(BASE_FIELDS)
    out = _run_turn(fields, "quiero el perfil 152 y agregarle un analisis mas a este si ?")
    assert "recomendar" not in out["reply"].lower()
    assert out["captured_fields"]["_selected_profile_code"] == "152"
    assert out["captured_fields"].get("_awaiting_additional_test") == "add"


def test_add_area_mention_shows_area_menu_not_fuzzy_test():
    """Error 3: 'agregarle un análisis de orina' muestra el menú de Uroanálisis marcado
    para AGREGAR; jamás resuelve 'orina' a un test suelto (Cortisol) sin confirmar."""
    fields = dict(BASE_FIELDS)
    out = _run_turn(fields, "quiero agregarle un analisis de orina al perfil")
    assert "1601" in out["reply"]          # el menú lista el área completa
    assert "cortisol" not in agent._catalog_item_key(str(fields.get("selected_tests")))
    assert not agent._as_text_items(fields.get("selected_tests"))  # nada agregado a ciegas
    assert out["captured_fields"].get("_test_menu_adds_to_profile") is True
    assert out["captured_fields"]["_selected_profile_code"] == "152"


def test_remove_request_still_goes_to_named_resolution():
    """Un pedido de QUITAR no entra a la rama de agregado: sigue resolviendo el test
    nombrado y lo quita (comportamiento previo intacto)."""
    fields = dict(BASE_FIELDS, selected_tests=["1601"])
    out = _run_turn(fields, "quitale el parcial de orina (14 parámetros)")
    assert "quito" in out["reply"].lower()
    assert "1601" not in agent._as_text_items(fields.get("selected_tests"))


def test_area_question_in_confirmation_adds_menu_before_fuzzy():
    """Fase de confirmación: 'agregale un análisis de orina' (afirmativo, sin '?')
    también va al menú del área, no al fuzzy-match."""
    fields = dict(BASE_FIELDS, payment_method="contraentrega")
    fields.pop("_offering_extra_analysis", None)
    with patch.object(agent.db, "find_tests_by_area", side_effect=_fake_area), \
         patch.object(agent.db, "get_tests_by_codes_or_names", side_effect=_fake_tests_lookup):
        out = agent._confirmation_analysis_adjustment(
            {"client_id": "client-A"}, fields, "agregale un analisis de orina", None
        )
    assert out is not None
    assert out["captured_fields"].get("_test_menu_adds_to_profile") is True
    assert "1601" in out["reply"]
    assert not agent._as_text_items(fields.get("selected_tests"))


def test_menu_selection_with_surrounding_words_matches_base_name():
    """Error 5 (captura): 'el parcial de orina esta bien!' selecciona 'Parcial de Orina
    (14 parámetros)' del menú aunque la frase traiga palabras alrededor."""
    picks = agent._select_tests_from_menu("el parcial de orina esta bien!", URO_TESTS)
    assert [p["code"] for p in picks] == ["1601"]


def test_menu_selection_short_names_do_not_false_match():
    """El matching por nombre-base no puede disparar con nombres cortos dentro de otras
    palabras ('PT' ⊄ 'acepto')."""
    options = [{"code": "1201", "name": "PT (Tiempo de Protrombina)", "price": 18000}]
    assert agent._select_tests_from_menu("acepto", options) == []


def test_exam_type_free_text_addition_lands_in_selected_tests():
    """Error 5 (invariante): si el modelo anota el agregado como texto libre en exam_type
    ('Perfil Prequirúrgico I + Parcial de Orina (14 parámetros) $16k'), el guardrail lo
    resuelve a selected_tests y restaura exam_type al nombre del perfil."""
    fields = dict(BASE_FIELDS,
                  exam_type="Perfil Prequirúrgico I + Parcial de Orina (14 parámetros) $16k",
                  selected_tests=[])
    ai_response = agent._base_route_response("...", fields)
    with patch.object(agent.db, "get_tests_by_codes_or_names", side_effect=_fake_tests_lookup):
        out = agent._enforce_profile_exam_type_integrity(ai_response)
    assert out["captured_fields"]["exam_type"] == "Perfil Prequirúrgico I"
    assert agent._as_text_items(out["captured_fields"]["selected_tests"]) == ["1601"]


def test_exam_type_restored_when_wiped_with_profile_active():
    """Error 6a: exam_type vacío con perfil base activo se restaura (evita re-preguntar
    el perfil después del pago)."""
    fields = dict(BASE_FIELDS, exam_type=None)
    ai_response = agent._base_route_response("...", fields)
    out = agent._enforce_profile_exam_type_integrity(ai_response)
    assert out["captured_fields"]["exam_type"] == "Perfil Prequirúrgico I"


def test_summary_total_includes_structured_addition():
    """La plata: resumen con perfil 152 + Parcial de Orina estructurado = $40.000."""
    fields = dict(BASE_FIELDS, selected_tests=["1601"], removed_tests=[],
                  payment_method="contraentrega")
    with patch.object(agent.db, "get_tests_by_codes_or_names", side_effect=_fake_tests_lookup), \
         patch.object(agent.db, "get_tests_by_codes", side_effect=_fake_tests_lookup):
        summary = agent._route_confirmation_summary(fields)
    assert summary is not None
    assert "Parcial de Orina" in summary
    assert "$40.000" in summary


def test_catalog_question_never_wipes_order_in_progress():
    """Error 4: '¿qué análisis de orina hacen?' con perfil y agregados en curso muestra
    el menú del ÁREA marcado para agregar, sin borrar selected_tests ni exam_type."""
    fields = dict(BASE_FIELDS, selected_tests=["1507"])
    with patch.object(agent.db, "find_tests_by_area", side_effect=_fake_area):
        out = agent._area_options_for_profile_addition(fields, "que analisis de orina hacen?")
    assert out is not None
    assert "1601" in out["reply"]
    assert fields["exam_type"] == "Perfil Prequirúrgico I"
    assert agent._as_text_items(fields["selected_tests"]) == ["1507"]
    assert fields.get("_test_menu_adds_to_profile") is True
