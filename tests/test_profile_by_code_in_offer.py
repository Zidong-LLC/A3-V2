"""
Un PERFIL pedido por su CÓDIGO en la ventana "¿querés agregar otro análisis o perfil?".

Los perfiles viven en `catalog_profiles` y el resolvedor de la oferta solo miraba
`catalog_tests`, así que "perfil 903" no resolvía nada: el turno caía a "¿qué análisis
querés agregar?" y el perfil se perdía. Encontrado con el simulador de cliente humano sobre
datos reales (2026-08-12): el cliente pidió el 903 dos veces y la orden cerró sin él.

ERR-080 ya había cubierto exactamente esto para la CONFIRMACIÓN; la ventana de la oferta
había quedado sin cubrir.
"""
import pytest

from app.enforcers import orden


PERFIL_903 = {"code": "903", "name": "Perfil Cardiaco III", "price": 55000}
PERFIL_701 = {"code": "701", "name": "Perfil Prequirúrgico I", "price": 24000}
CATALOGO = {"903": PERFIL_903, "701": PERFIL_701}


@pytest.fixture(autouse=True)
def catalogo_de_perfiles(monkeypatch):
    """Mock de infraestructura: solo la consulta a Supabase, no la lógica."""
    def _by_codes(codes, species=None):
        return [CATALOGO[c] for c in codes if c in CATALOGO]

    monkeypatch.setattr(orden.db, "get_catalog_profiles_by_codes", _by_codes)


def test_perfil_por_codigo_se_engancha_como_base():
    """Sin perfil previo, el código pedido queda de perfil base."""
    fields = {}
    attached, _ = orden._attach_profiles_by_code(fields, "perfil 903")
    assert [p["code"] for p in attached] == ["903"]
    assert fields["_selected_profile_code"] == "903"


def test_codigo_pelado_tambien_resuelve():
    """El cliente que insiste con '903' a secas debe ser atendido igual."""
    fields = {}
    assert orden._attach_profiles_by_code(fields, "903")[0]
    assert fields["_selected_profile_code"] == "903"


def test_con_perfil_base_el_nuevo_se_suma_como_adicional():
    """Mecanismo de ERR-077: el resumen muestra y suma los perfiles extra."""
    fields = {"_selected_profile_code": "701"}
    orden._attach_profiles_by_code(fields, "agregame el perfil 903")
    assert [p["code"] for p in fields["_extra_profiles"]] == ["903"]


def test_no_duplica_un_perfil_ya_enganchado():
    fields = {"_selected_profile_code": "903"}
    attached, already = orden._attach_profiles_by_code(fields, "el 903")
    assert attached == [] and [p["code"] for p in already] == ["903"]
    assert not fields.get("_extra_profiles")


def test_pedido_mixto_no_pierde_el_perfil():
    """'el 1101 y el perfil 701': 1101 es un ANÁLISIS y no debe tapar al perfil."""
    fields = {}
    attached, _ = orden._attach_profiles_by_code(fields, "necesito el 1101 y el perfil 701")
    assert [p["code"] for p in attached] == ["701"]


def test_un_mensaje_sin_codigos_no_engancha_nada():
    fields = {}
    assert orden._attach_profiles_by_code(fields, "sí, dale") == ([], [])
    assert fields == {}


def test_codigo_que_no_es_perfil_no_engancha_nada():
    """1101 es un análisis, no un perfil: este carril no debe tocarlo."""
    fields = {}
    assert orden._attach_profiles_by_code(fields, "el 1101") == ([], [])
    assert not fields.get("_selected_profile_code")
