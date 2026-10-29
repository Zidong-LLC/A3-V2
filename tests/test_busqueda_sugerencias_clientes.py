"""Sugerencias del buscador de clientes (ERR-189, reporte del usuario 2026-10-29).

«Busqué un cliente que sé que estaba y no aparecía»: el autocompletar consultaba solo la
palabra más larga, cortaba en 60 por orden alfabético y recién después afinaba. Con 100
«Veterinaria A…» delante, «Veterinaria Soacha» no salía ni escrita exacta (205 de 861
clientes reales), y sin tildes («canon») no encontraba «Cañon».
"""
from unittest.mock import patch

from app.services import db

RELLENO = [{"id": f"r{i}", "clinic_name": f"Veterinaria A{i:03d}", "tax_id": f"9000{i:05d}",
            "zone": "", "is_active": True} for i in range(100)]
SOACHA = {"id": "s1", "clinic_name": "Veterinaria Soacha", "tax_id": "122665", "zone": "", "is_active": True}
CANON = {"id": "c1", "clinic_name": "Luz Cañon", "tax_id": "1002646570", "zone": "", "is_active": True}
VIEJA = {"id": "v1", "clinic_name": "Veterinaria Soacha Vieja", "tax_id": "", "zone": "", "is_active": False}


def _buscar(termino, limit=12):
    with patch.object(db, "_paginado", return_value=RELLENO + [SOACHA, CANON, VIEJA]):
        return [f["id"] for f in db.search_clients_for_dashboard(termino, limit=limit)]


def test_el_nombre_exacto_aparece_aunque_haya_cien_parecidos_antes():
    assert _buscar("Veterinaria Soacha")[0] == "s1"


def test_palabras_en_otro_orden_y_sin_tildes():
    assert "s1" in _buscar("soacha veterinaria")
    assert _buscar("luz canon") == ["c1"]


def test_por_nit_con_o_sin_puntos():
    assert _buscar("122665") == ["s1"]
    assert _buscar("1.002.646.570") == ["c1"]


def test_los_inactivos_van_despues_de_los_activos():
    assert _buscar("soacha") == ["s1", "v1"]


def test_menos_de_dos_letras_no_busca():
    assert _buscar("v") == []


def test_la_palabra_entera_va_antes_que_la_que_esta_dentro_de_otra():
    """«cotas» está dentro de cada «Mascotas»: el cliente «Vet+Cotas» quedaba afuera."""
    mascotas = [{"id": f"m{i}", "clinic_name": f"Mascotas {i:03d}", "tax_id": "", "zone": "",
                 "is_active": True} for i in range(30)]
    cotas = {"id": "vc", "clinic_name": "Vet+Cotas", "tax_id": "80893868-8", "zone": "", "is_active": True}
    with patch.object(db, "_paginado", return_value=mascotas + [cotas]):
        assert db.search_clients_for_dashboard("cotas")[0]["id"] == "vc"
