"""ERR-067 (chat real 2026-07-17): 'le quiero agregar un análisis de orina sodio y potasio'
— pedido MIXTO (área ambigua + tests nombrados) perdía sodio/potasio: el menú del área
respondía primero y se tragaba el resto. Y el compuesto con typo ('arrestar' por 'agregar')
perdía TODO el agregado por depender del verbo. Tests de lógica pura sobre los mensajes
reales, sin fingir el modelo (L51)."""
from unittest.mock import patch

from app import orders

POTASIO = {"code": "1404", "name": "Potasio", "price": 12000, "category": "Química"}
SODIO = {"code": "1405", "name": "Sodio", "price": 12000, "category": "Química"}
URO = [{"code": "1601", "name": "Parcial de Orina (14 parámetros)", "price": 16000,
        "category": "Uroanálisis", "sample": "Orina Fresca"},
       {"code": "1602", "name": "Lectura Sedimento Urinario", "price": 7000,
        "category": "Uroanálisis", "sample": "Orina Fresca"}]
CATALOGO = [POTASIO, SODIO] + URO

BASE = {"_client_found": True, "species": "Bovino", "_selected_profile_code": "152",
        "_selected_profile_name": "Perfil Prequirúrgico I", "_selected_profile_price": 24000,
        "exam_type": "Perfil Prequirúrgico I"}
SESSION = {"client_id": "c1"}


def _run(msg):
    fields = dict(BASE)
    with patch.object(orders.db, "list_catalog_tests", return_value=CATALOGO), \
         patch.object(orders.db, "find_tests_by_area", return_value=("Uroanálisis", URO)), \
         patch.object(orders.db, "get_tests_by_codes_or_names", return_value=[]):
        out = orders._selected_profile_addition_response(SESSION, fields, msg, "Listo, registro 152.")
    return out, fields


def test_mixed_area_plus_named_decomposes():
    """El mensaje real: sodio y potasio se AGREGAN con precio, y orina se ofrece como menú."""
    out, fields = _run("Le quiero agregar un análisis de orina sodio y potasio")
    codes = set(fields.get("selected_tests") or [])
    assert {"1404", "1405"} <= codes                      # nombrados: agregados
    assert fields.get("_test_menu_options")               # área: menú ofrecido
    assert "Sodio" in out["reply"] and "Potasio" in out["reply"]
    assert "uroanálisis" in out["reply"].lower() or "1601" in out["reply"]


def test_typo_verb_does_not_lose_the_addition():
    """'arrestar' (typo de agregar): el contenido manda, el verbo no importa."""
    out, fields = _run("Le quiero arrestar aparte un análisis de orina sodio y potasio si?")
    assert {"1404", "1405"} <= set(fields.get("selected_tests") or [])
    assert fields.get("_test_menu_options")


def test_plain_profile_selection_mentions_nothing():
    """'el 152' pelado no menciona nada agregable: no dispara agregados ni menús."""
    fields = dict(BASE)
    with patch.object(orders.db, "list_catalog_tests", return_value=CATALOGO), \
         patch.object(orders.db, "find_tests_by_area", return_value=(None, [])):
        res = orders._profile_addition_if_mentioned(SESSION, fields, "el 152", "Listo.")
    assert res is None
    assert not fields.get("selected_tests")


def test_mixed_during_extra_offer_also_decomposes():
    """Mismo patrón en la oferta '¿agregás otro?': 'orina sodio y potasio' (sin verbo de
    agregar) suma los nombrados Y ofrece el menú del área — antes el área se ignoraba."""
    from app.enforcers import orden as eorden
    fields = dict(BASE, _offering_extra_analysis=True)
    with patch.object(eorden.db, "list_catalog_tests", return_value=CATALOGO), \
         patch.object(eorden.db, "find_tests_by_area", return_value=("Uroanálisis", URO)), \
         patch.object(eorden.db, "get_tests_by_codes_or_names", return_value=[]):
        out = eorden._handle_extra_analysis_answer(SESSION, fields, "orina sodio y potasio")
    assert {"1404", "1405"} <= set(fields.get("selected_tests") or [])
    assert fields.get("_test_menu_options")
    assert "Sodio" in out["reply"] and "uroanálisis" in out["reply"].lower()


def test_multiple_ambiguous_resolve_step_by_step_in_order():
    """Feature 2026-07-17: 'orina y un prequirurgico' — ambos con opciones. Primero el menú
    de orina; al elegir, el bot solo sigue con el siguiente pedido (cola en orden)."""
    fields = dict(BASE)
    fields.pop("_selected_profile_code"); fields.pop("_selected_profile_name")
    fields.pop("_selected_profile_price"); fields.pop("exam_type")
    PREQ = [{"code": "152", "name": "Perfil Prequirúrgico I", "price": 24000}]

    def fake_area(term, species=None, limit=15):
        return ("Uroanálisis", URO) if "orina" in term.lower() else (None, [])

    def fake_cats(term, species=None, limit=11):
        return PREQ if "prequirurgico" in term.lower() or "prequirúrgico" in term.lower() else []

    with patch.object(orders.db, "list_catalog_tests", return_value=CATALOGO), \
         patch.object(orders.db, "find_tests_by_area", side_effect=fake_area), \
         patch.object(orders.db, "list_catalog_profiles_matching_category", side_effect=fake_cats), \
         patch.object(orders.db, "get_tests_by_codes_or_names", return_value=[]):
        out = orders._profile_addition_if_mentioned(
            SESSION, fields, "quiero un analisis de orina y un prequirurgico", "Listo.")
        # 1) primero el menú de orina; el prequirúrgico queda EN COLA
        assert out and "uroanálisis" in out["reply"].lower()
        assert fields.get("_pending_ambiguous_items")
        # 2) el cliente elige del menú → al asentarse, sigue SOLO con el prequirúrgico
        fields["selected_tests"] = ["1601"]
        fields.pop("_test_menu_options", None)
        out2 = orders._analysis_settled_response(SESSION, dict(BASE, **fields), "Listo, agrego 1601.")
        assert "ahora vamos con lo siguiente" in out2["reply"].lower()
        assert "prequir" in out2["reply"].lower()
        assert not (out2["captured_fields"].get("_pending_ambiguous_items"))   # cola drenada
