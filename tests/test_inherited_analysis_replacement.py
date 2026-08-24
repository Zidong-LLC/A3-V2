"""
ERR-139 — El análisis HEREDADO de la orden anterior contaminaba la orden nueva (DINERO).

Test en vivo (2026-08-21, orden de Joy): al abrir la 3.ª orden el sistema heredó el 653
(Perfil Senior Canino III, $58.000) de la orden de Lulú y lo reofreció. El cliente declaró
"El análisis es 952" — y el 952 se SUMÓ como perfil adicional en vez de reemplazar al
heredado: la orden salió por $148.000 en vez de $90.000, con un perfil que el cliente
nunca pidió para ese paciente.

Regla: mientras `_analysis_inherited` esté encendida (el cliente no confirmó ni eligió),
una mención de perfil SIN verbo de agregar REEMPLAZA al heredado. Con verbo de agregar
("agregale el 952") la suma se respeta — es intención explícita.
"""
import pytest

from app.enforcers import orden


PERFIL_653 = {"code": "653", "name": "Perfil Senior Canino III", "price": 58000}
PERFIL_952 = {"code": "952", "name": "Perfil Toxicológico Órgano Fosforados", "price": 90000}
CATALOGO = {"653": PERFIL_653, "952": PERFIL_952}


@pytest.fixture(autouse=True)
def catalogo_de_perfiles(monkeypatch):
    def _by_codes(codes, species=None):
        return [CATALOGO[c] for c in codes if c in CATALOGO]

    monkeypatch.setattr(orden.db, "get_catalog_profiles_by_codes", _by_codes)


def _orden_con_653_heredado() -> dict:
    """El estado exacto tras 'Otra orden' + reoferta de estables (caso Joy)."""
    return {
        "_analysis_inherited": True,
        "exam_type": "Perfil Senior Canino III",
        "_selected_profile_code": "653",
        "_selected_profile_name": "Perfil Senior Canino III",
        "_selected_profile_price": 58000,
        "_profile_detail_offered": True,
    }


def test_declaracion_reemplaza_al_heredado():
    """'El análisis es 952' con el 653 heredado → el 952 queda de BASE, sin extras."""
    fields = _orden_con_653_heredado()
    attached, _ = orden._attach_profiles_by_code(fields, "El análisis es 952")
    assert [p["code"] for p in attached] == ["952"]
    assert fields["_selected_profile_code"] == "952"
    assert not fields.get("_extra_profiles"), "el 653 heredado no puede sobrevivir como extra"
    assert not fields.get("_analysis_inherited")


def test_agregar_explicito_respeta_al_heredado():
    """'Agregale el 952' es intención explícita de SUMAR: el 653 se queda de base."""
    fields = _orden_con_653_heredado()
    orden._attach_profiles_by_code(fields, "agregale el 952")
    assert fields["_selected_profile_code"] == "653"
    assert [p["code"] for p in fields.get("_extra_profiles") or []] == ["952"]


def test_confirmar_el_mismo_codigo_no_borra_nada():
    """'El 653' (el mismo heredado) confirma: base intacta y marca apagada."""
    fields = _orden_con_653_heredado()
    attached, already = orden._attach_profiles_by_code(fields, "el 653")
    assert attached == [] and [p["code"] for p in already] == ["653"]
    assert fields["_selected_profile_code"] == "653"
    assert not fields.get("_analysis_inherited")


def test_sin_marca_de_heredado_el_perfil_nuevo_se_suma():
    """No-regresión ERR-077: elegido POR el cliente (sin marca), otro perfil se suma."""
    fields = _orden_con_653_heredado()
    fields.pop("_analysis_inherited")
    orden._attach_profiles_by_code(fields, "El análisis es 952")
    assert fields["_selected_profile_code"] == "653"
    assert [p["code"] for p in fields.get("_extra_profiles") or []] == ["952"]


def test_la_frontera_de_orden_limpia_marca_y_extras():
    """ERR-139 (segunda vía): ni la marca ni los perfiles adicionales cruzan a otra orden."""
    from app import agent

    assert "_analysis_inherited" in agent._ORDER_RESET_FIELDS
    assert "_extra_profiles" in agent._ORDER_RESET_FIELDS
