"""ERR-097: la solicitud del portal debe resolver contra el catálogo real.

Antes el portal mandaba `exam_type` como texto libre y la orden se guardaba con
`base_profile = {"code": null, "price": 0}`: entraba trabajo sin plata asociada.
"""
from unittest.mock import patch

from app.portal.client_requests import resolve_catalog_selection

PERFIL = {
    "code": "P-01", "name": "Perfil renal", "price": 85000,
    "description": "Creatinina, BUN",
}
TESTS = [
    {"code": "T-10", "name": "Hemograma", "price": 32000},
    {"code": "T-11", "name": "Glucosa", "price": 18000},
]


def _resolve(profile_code, test_codes, profile=None, tests=None):
    with patch("app.portal.client_requests.db.find_catalog_profile", return_value=profile), \
         patch("app.portal.client_requests.db.get_tests_by_codes_or_names",
               return_value=tests if tests is not None else []):
        return resolve_catalog_selection(profile_code, test_codes)


def test_profile_carries_code_name_and_price():
    fields = _resolve("P-01", [], profile=PERFIL)

    assert fields["_selected_profile_code"] == "P-01"
    assert fields["_selected_profile_name"] == "Perfil renal"
    assert fields["_selected_profile_price"] == 85000
    assert fields["_selected_profile_description"] == "Creatinina, BUN"
    assert fields["exam_type"] == "Perfil renal"


def test_loose_tests_without_profile_become_selected_tests():
    """Sin perfil, los análisis sueltos arman un perfil personalizado."""
    fields = _resolve("", ["T-10", "T-11"], tests=TESTS)

    assert fields["selected_tests"] == ["T-10", "T-11"]
    assert "_selected_profile_code" not in fields
    assert fields["exam_type"] == "Hemograma, Glucosa"


def test_profile_plus_extra_tests():
    fields = _resolve("P-01", ["T-10"], profile=PERFIL, tests=[TESTS[0]])

    assert fields["_selected_profile_code"] == "P-01"
    assert fields["selected_tests"] == ["T-10"]
    assert fields["exam_type"] == "Perfil renal, Hemograma"


def test_unknown_codes_are_discarded_never_invented():
    """Un código que no está en el catálogo no puede generar un precio."""
    fields = _resolve("NO-EXISTE", ["TAMPOCO"], profile=None, tests=[])

    assert fields["exam_type"] == ""
    assert "_selected_profile_code" not in fields
    assert "selected_tests" not in fields


def test_empty_exam_type_is_what_the_view_rejects():
    """La vista exige exam_type no vacío: sin catálogo válido no se crea la orden."""
    assert not _resolve("", [], profile=None, tests=[])["exam_type"]
