"""Pedido de A3 (2026-11-09): «si el cliente tiene varios análisis y uno se cargó mal o se
pidieron dos de más, poder borrar ese». Acá, la cuenta: qué líneas tiene una orden y cómo
queda el `profile` —lo que después se factura— al sacarle una."""
import pytest

from app import billing, orden_edicion

SUELTOS = {  # como lo guarda el chat: análisis sueltos bajo un rótulo sin código ni precio
    "base_profile": {"code": None, "name": "Perfil personalizado (3 análisis)", "price": 0},
    "included_tests": [], "extra_profiles": [], "removed_tests": [],
    "added_tests": [{"code": "1101", "name": "Cuadro Hemático Completo", "price": 16000},
                    {"code": "1404", "name": "Potasio", "price": 12000},
                    {"code": "1405", "name": "Sodio", "price": 12000}],
    "total_estimated": 40000,
    "price_adjustment": {"base": 0, "added": 40000, "removed": 0, "subtotal": 40000, "volume_discount": 0, "total": 40000},
}
CON_PERFILES = {  # como lo guarda «Nueva Orden»: perfil base, un adicional y un análisis
    "base_profile": {"code": "952", "name": "Perfil Toxicológico", "price": 90000},
    "included_tests": ["Colinesterasa"], "removed_tests": [],
    "extra_profiles": [{"code": "653", "name": "Perfil Renal", "price": 45000}],
    "added_tests": [{"code": "1903", "name": "Citología PAF", "price": 52000}],
    "total_estimated": 187000, "price_adjustment": {"base": 90000, "added": 97000, "removed": 0, "total": 187000},
}


def _facturado(perfil) -> int:
    return sum(round(l["price"] * (1 - l.get("discount", 0) / 100)) for l in billing.build_invoice_lines(perfil))


def test_las_lineas_salen_en_el_orden_en_que_se_facturan():
    assert [(l["tipo"], l["code"], l["price"]) for l in orden_edicion.lineas(CON_PERFILES)] == [
        ("Perfil", "952", 90000), ("Perfil adicional", "653", 45000), ("Análisis", "1903", 52000)]
    assert [l["code"] for l in orden_edicion.lineas(SUELTOS)] == ["1101", "1404", "1405"], \
        "el rótulo «Perfil personalizado» no es una línea"
    assert orden_edicion.lineas(None) == []


def test_el_perfil_base_muestra_su_precio_neto_de_lo_removido():
    perfil = dict(CON_PERFILES, removed_tests=[{"code": "1", "name": "X", "price": 10000}])
    assert orden_edicion.lineas(perfil)[0]["price"] == 80000


def test_quitar_un_analisis_suelto_recalcula_el_total_y_el_rotulo(monkeypatch):
    monkeypatch.setattr("app.rules.calculate_discount", lambda n, subtotal: 0)
    nuevo, quitada = orden_edicion.quitar(SUELTOS, 1)
    assert quitada["code"] == "1404"
    assert [t["code"] for t in nuevo["added_tests"]] == ["1101", "1405"]
    assert nuevo["base_profile"]["name"] == "Perfil personalizado (2 análisis)"
    assert nuevo["total_estimated"] == 28000 == _facturado(nuevo), "lo que se guarda es lo que se factura"
    assert len(SUELTOS["added_tests"]) == 3, "no se toca el perfil original: es el respaldo"


def test_quitar_un_analisis_de_una_orden_con_perfiles():
    nuevo, quitada = orden_edicion.quitar(CON_PERFILES, 2)
    assert quitada["code"] == "1903" and nuevo["added_tests"] == []
    assert nuevo["total_estimated"] == 135000 == _facturado(nuevo)


def test_quitar_un_perfil_adicional():
    nuevo, quitada = orden_edicion.quitar(CON_PERFILES, 1)
    assert quitada["code"] == "653" and nuevo["extra_profiles"] == []
    assert nuevo["base_profile"]["code"] == "952"
    assert nuevo["total_estimated"] == 142000 == _facturado(nuevo)


def test_quitar_el_perfil_base_sube_al_adicional():
    nuevo, quitada = orden_edicion.quitar(CON_PERFILES, 0)
    assert quitada["code"] == "952"
    assert nuevo["base_profile"] == {"code": "653", "name": "Perfil Renal", "price": 45000}
    assert nuevo["extra_profiles"] == [] and nuevo["included_tests"] == []
    assert nuevo["total_estimated"] == 97000 == _facturado(nuevo)


def test_quitar_el_perfil_base_sin_adicionales_deja_los_analisis_sueltos(monkeypatch):
    monkeypatch.setattr("app.rules.calculate_discount", lambda n, subtotal: 0)
    perfil = dict(CON_PERFILES, extra_profiles=[])
    nuevo, _ = orden_edicion.quitar(perfil, 0)
    assert nuevo["base_profile"]["code"] is None
    assert nuevo["base_profile"]["name"] == "Perfil personalizado (1 análisis)"
    assert nuevo["total_estimated"] == 52000 == _facturado(nuevo)


def test_el_ultimo_analisis_no_se_quita_se_elimina_la_orden():
    uno = dict(SUELTOS, added_tests=SUELTOS["added_tests"][:1])
    with pytest.raises(ValueError, match="único análisis"):
        orden_edicion.quitar(uno, 0)
    with pytest.raises(ValueError, match="ya no está"):
        orden_edicion.quitar(SUELTOS, 7)


def test_el_texto_de_la_columna_sigue_a_la_orden():
    antes = orden_edicion.lineas(CON_PERFILES)
    nuevo, _ = orden_edicion.quitar(CON_PERFILES, 1)
    # «Nueva Orden» guarda un nombre por línea: se va el que se quitó.
    assert orden_edicion.etiqueta("Perfil Toxicológico, Perfil Renal, Citología PAF", antes, 1, nuevo) \
        == "Perfil Toxicológico, Citología PAF"
    # El chat guarda el rótulo: se actualiza la cantidad.
    antes = orden_edicion.lineas(SUELTOS)
    nuevo, _ = orden_edicion.quitar(SUELTOS, 0)
    assert orden_edicion.etiqueta("Perfil personalizado (3 análisis)", antes, 0, nuevo) \
        == "Perfil personalizado (2 análisis)"
    # Un perfil del chat con un análisis agregado: el texto era el perfil y sigue siéndolo.
    antes = orden_edicion.lineas(CON_PERFILES)
    nuevo, _ = orden_edicion.quitar(CON_PERFILES, 2)
    assert orden_edicion.etiqueta("Perfil Toxicológico", antes, 2, nuevo) == "Perfil Toxicológico"
