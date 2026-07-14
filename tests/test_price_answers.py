"""
Regresión: el agente debe responder el PRECIO real del catálogo cuando el cliente pregunta
"¿cuánto cuesta X?" o "¿cuánto serían todos esos análisis?", y mostrar el precio al lado de
cada análisis al registrarlo. Antes deflectaba con un genérico "depende del análisis".
Ver tasks/errores-soluciones.md ERR-042.
"""
from unittest.mock import patch

from app import agent

CATALOG = [
    {"code": "0001", "name": "Hemograma Completo", "price": 30000, "category": "Hematología"},
    {"code": "0201", "name": "Glucosa", "price": 18000, "category": "Química"},
    {"code": "1601", "name": "Uroanálisis Completo", "price": 35000, "category": "Uroanálisis"},
]
BY = {c["code"]: c for c in CATALOG}


def _by_codes_or_names(items):
    out, seen = [], set()
    for raw in items or []:
        k = str(raw).strip().lower()
        for row in CATALOG:
            if k == row["code"] or k in row["name"].lower():
                if row["code"] not in seen:
                    out.append(row); seen.add(row["code"])
                break
    return out


def _answer(fields, msg):
    with patch.object(agent.db, "get_tests_by_codes_or_names", side_effect=_by_codes_or_names), \
         patch.object(agent.db, "list_catalog_tests", return_value=CATALOG):
        return agent._catalog_price_answer(fields, msg)


def test_specific_analysis_price():
    """'¿cuánto sale el hemograma?' responde con el valor real del catálogo."""
    ans = _answer({}, "¿cuánto sale el hemograma?")
    assert ans is not None
    assert "30,000" in ans and "Hemograma" in ans


def test_total_of_selected_tests():
    """'¿cuánto serían todos esos análisis?' suma los elegidos y muestra el total con el
    descuento por volumen explícito (subtotal $48k − 12% = $42,240)."""
    fields = {"selected_tests": ["0001", "0201"]}
    ans = _answer(fields, "¿cuánto serían todos esos análisis?")
    assert ans is not None
    assert "48,000" in ans          # subtotal visible
    assert "42,240" in ans          # total con descuento por volumen
    assert "descuento" in ans.lower()


def test_selected_profile_price_when_no_named_analysis():
    """Si no nombra análisis y hay un perfil elegido, responde su precio."""
    fields = {"_selected_profile_name": "Perfil Canino I", "_selected_profile_price": 40000}
    ans = _answer(fields, "¿y cuánto cuesta?")
    assert ans is not None and "40,000" in ans


def test_non_price_question_returns_none():
    """Un mensaje que no pregunta precio no dispara respuesta de precio."""
    assert _answer({"selected_tests": ["0001"]}, "el paciente se llama Toby") is None


def test_price_from_menu_options_selection():
    """Tras mostrar un menú, '¿cuánto el primero?' resuelve por la opción mostrada."""
    fields = {"_test_menu_options": [{"code": "1601", "name": "Uroanálisis Completo", "price": 35000}]}
    with patch.object(agent.db, "get_tests_by_codes_or_names", return_value=[]), \
         patch.object(agent.db, "list_catalog_tests", return_value=[]):
        ans = agent._catalog_price_answer(fields, "¿cuánto el primero?")
    assert ans is not None and "35,000" in ans
