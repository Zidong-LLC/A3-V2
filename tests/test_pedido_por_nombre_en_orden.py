"""El cliente pide por NOMBRE, no por código (pedido del usuario, 2026-08-25).

La llamada 9 (21/08) dejó el caso del 1903: el cliente lo pidió y el bot no lo ubicó.
El código ya se resuelve; falta blindar la otra mitad — que un cliente que dice
"agrégame una citología PAF" obtenga exactamente el mismo resultado que quien dice 1903.

Se prueban los DOS carriles determinísticos que atienden el pedido a mitad de orden:
el de la oferta ("¿otro análisis o seguimos?") y el de la confirmación.
"""
import pytest

from app import orders
from app.enforcers import orden as enf_orden

TEST_1903 = {"code": "1903", "name": "Citología PAF", "price": 52000,
             "category": "Convenio SERVIPAT", "species": "ambos", "sample": "Enviar 3 Laminas"}
TEST_1901 = {"code": "1901", "name": "Citología Vaginal", "price": 15000,
             "category": "Citología", "species": "ambos", "sample": "Enviar 2 Laminas"}
TEST_1601 = {"code": "1601", "name": "Parcial de Orina (14 parámetros)", "price": 16000,
             "category": "Uroanálisis", "species": "ambos", "sample": "Orina Fresca"}
CATALOGO = [TEST_1903, TEST_1901, TEST_1601]


@pytest.fixture(autouse=True)
def catalogo(monkeypatch):
    for mod in (orders, enf_orden):
        monkeypatch.setattr(mod.db, "list_catalog_tests", lambda **k: list(CATALOGO))
        monkeypatch.setattr(mod.db, "get_tests_by_codes_or_names",
                            lambda terms: [r for r in CATALOGO
                                           if any(str(t).strip() == r["code"] for t in terms)])
    monkeypatch.setattr(enf_orden.db, "get_catalog_profiles_by_codes", lambda *a, **k: [])


def _orden_con_perfil() -> dict:
    """Orden ya cerrada en su perfil base, con la oferta de agregar activa."""
    return {
        "_client_found": True, "species": "Canino",
        "exam_type": "Perfil Senior Canino III",
        "_selected_profile_code": "653",
        "_selected_profile_name": "Perfil Senior Canino III",
        "_selected_profile_price": 58000,
        "_offering_extra_analysis": True,
    }


@pytest.mark.parametrize("frase", [
    "agrégame una citología PAF",
    "sumale la citologia paf",
    "quiero agregar Citología PAF",
])
def test_agregar_por_nombre_completo_carga_el_analisis(frase):
    fields = _orden_con_perfil()
    resp = enf_orden._handle_extra_analysis_answer({}, fields, frase)

    assert resp is not None, f"el carril no atendió: {frase}"
    assert "1903" in (fields.get("selected_tests") or []), f"no agregó el 1903 con: {frase}"
    assert "citología paf" in resp["reply"].lower()


def test_nombre_de_grupo_ofrece_opciones_en_vez_de_adivinar():
    """'una citología' a secas no nombra UNA: se ofrecen las dos (la común y la del
    convenio) — regla de dinero: ante la duda, ofrecer, nunca elegir por el cliente."""
    fields = _orden_con_perfil()
    resp = enf_orden._handle_extra_analysis_answer({}, fields, "agrégame una citología")

    assert resp is not None
    assert not fields.get("selected_tests"), "no debe agregar sin match inequívoco"
    reply = resp["reply"]
    assert "1903" in reply and "1901" in reply, "las dos opciones deben ofrecerse"


def test_el_codigo_y_el_nombre_dan_el_mismo_resultado():
    """Invariante del pedido: decir 1903 o decir 'Citología PAF' es lo mismo."""
    por_codigo = _orden_con_perfil()
    enf_orden._handle_extra_analysis_answer({}, por_codigo, "agrégame el 1903")

    por_nombre = _orden_con_perfil()
    enf_orden._handle_extra_analysis_answer({}, por_nombre, "agrégame la Citología PAF")

    assert por_codigo.get("selected_tests") == por_nombre.get("selected_tests") == ["1903"]
