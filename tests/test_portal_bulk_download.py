"""Descarga masiva de resultados (ítem 20 del roadmap firmado, día 73)."""
import io
import zipfile

from app.portal.client_results import _zip_entry_name


def test_zip_entry_uses_order_and_patient():
    name = _zip_entry_name({"order_number": "A3-00042", "patient_name": "Firulais"}, set())

    assert name == "A3-00042-Firulais.pdf"


def test_zip_entry_strips_path_traversal():
    """El nombre viene de datos del usuario: no puede escapar de la carpeta."""
    name = _zip_entry_name(
        {"order_number": "../../etc", "patient_name": "pass/wd"}, set()
    )

    assert "/" not in name and ".." not in name
    assert name.endswith(".pdf")


def test_zip_entry_deduplicates_repeated_names():
    used: set[str] = set()
    row = {"order_number": "A3-1", "patient_name": "Luna"}

    first = _zip_entry_name(row, used)
    second = _zip_entry_name(row, used)
    third = _zip_entry_name(row, used)

    assert [first, second, third] == ["A3-1-Luna.pdf", "A3-1-Luna-2.pdf", "A3-1-Luna-3.pdf"]


def test_zip_entry_falls_back_when_there_is_no_usable_name():
    assert _zip_entry_name({}, set()) == "resultado.pdf"
    assert _zip_entry_name({"order_number": "///", "patient_name": None}, set()) == "resultado.pdf"


def test_zip_bundle_is_readable_with_expected_entries():
    """El archivo generado se abre y trae un PDF por resultado."""
    buffer = io.BytesIO()
    used: set[str] = set()
    rows = [
        ({"order_number": "A3-1", "patient_name": "Luna"}, b"%PDF-1"),
        ({"order_number": "A3-2", "patient_name": "Rocco"}, b"%PDF-2"),
    ]
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as bundle:
        for row, data in rows:
            bundle.writestr(_zip_entry_name(row, used), data)

    buffer.seek(0)
    with zipfile.ZipFile(buffer) as bundle:
        assert bundle.namelist() == ["A3-1-Luna.pdf", "A3-2-Rocco.pdf"]
        assert bundle.read("A3-2-Rocco.pdf") == b"%PDF-2"
