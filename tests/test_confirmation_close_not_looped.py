"""
Regresión ERR-080 (prueba en vivo del usuario, 2026-07-21, chat 10): el cliente confirmó
el resumen con "Si" y el bot respondió "Claro. ¿Qué análisis quieres agregar?" en bucle
("El perfil 1331" → misma pregunta; "1331" → misma pregunta) hasta que escribió "Exit".
La orden NUNCA se registró (`request_id=None` en la sesión real).

Causa (dos capas):
1. `_awaiting_additional_test` quedó pegado desde ANTES de la confirmación (turno "Si 3");
   `_confirmation_analysis_adjustment` corre antes del cierre determinístico, así que el
   "Si" se intentaba resolver como análisis, fallaba y re-armaba el flag.
2. "1331" es código de PERFIL: `get_tests_by_codes_or_names` no resuelve perfiles, así que
   ni siquiera nombrando el código exacto había salida del bucle.
"""
from unittest.mock import patch

from app.enforcers import confirmacion

PANEL_1331 = {"code": "1331", "name": "Panel Función Hepática", "price": 90000,
              "category": "Panel", "species": "ambos", "description": "Albúmina, AST"}

HEMOGRAMA = {"code": "201", "name": "Hemograma", "price": 25000}

# Orden completa con perfil base 101, como quedó la orden real del chat 10.
BASE = {
    "_client_found": True, "clinic_name": "Centro Veterinario La Uribe",
    "pickup_address": "CL 172A 21A-28", "requesting_doctor": "Diana Pérez",
    "patient_name": "Fifi", "species": "Equino", "breed": "Cuarto de Milla",
    "sex": "Macho", "patient_age": "5 años", "owner_name": "Jorge Toro",
    "observations": "Ninguna", "payment_method": "contraentrega",
    "exam_type": "Perfil Parasitológico I",
    "_selected_profile_code": "101",
    "_selected_profile_name": "Perfil Parasitológico I",
    "_selected_profile_price": 30000,
}

SESSION = {"client_id": "c1"}


def _ai(fields):
    return {
        "intent": "route_scheduling",
        "captured_fields": fields,
        "reply": "",
        "user_intent_signal": None,
        "message_mode": "flow_progress",
        "phase": "fase_4_confirmacion",
    }


def _sin_areas():
    return patch.object(confirmacion, "_area_options_for_profile_addition",
                        lambda *a, **k: None)


def test_el_resumen_limpia_el_flag_pegado_y_el_si_cierra():
    """El escenario real completo: el flag quedó pegado de una fase anterior; al mostrar
    el resumen debe limpiarse, y el "Si" siguiente debe CERRAR la orden, no repreguntar."""
    fields = dict(BASE, _awaiting_additional_test="add")

    with patch.object(confirmacion.db, "get_tests_by_codes_or_names", return_value=[]):
        shown = confirmacion._enforce_confirmation_step(
            SESSION, _ai(fields), fields, "fase_3_captura_datos", "Motorizado"
        )
    assert "resumo la orden" in shown["reply"]
    assert "_awaiting_additional_test" not in fields, "el resumen no limpió el flag pegado"

    with patch.object(confirmacion.db, "get_tests_by_codes_or_names", return_value=[]):
        out = confirmacion._enforce_confirmation_step(
            SESSION, _ai(fields), fields, confirmacion.CONFIRMATION_PHASE, "Si"
        )
    assert out["phase"] == "fase_6_cierre", "el 'Si' no cerró la orden"
    assert "Quedó registrado" in out["reply"]


def test_codigo_de_perfil_en_confirmacion_se_agrega_sin_bucle():
    """'1331' mientras el bot espera qué agregar: debe sumar el perfil como adicional
    (mecanismo de ERR-077) y re-mostrar el resumen con el total, no repreguntar."""
    fields = dict(BASE, _awaiting_additional_test="add")

    with patch.object(confirmacion.db, "get_tests_by_codes_or_names", return_value=[]), \
         patch.object(confirmacion.db, "get_catalog_profiles_by_codes", return_value=[PANEL_1331]), \
         _sin_areas():
        out = confirmacion._confirmation_analysis_adjustment(SESSION, fields, "1331", None)

    assert out is not None
    assert [p["code"] for p in fields.get("_extra_profiles") or []] == ["1331"]
    assert "_awaiting_additional_test" not in fields
    assert "Panel Función Hepática" in out["reply"]
    # Bug de dinero: 30.000 (base) + 90.000 (1331) — el total debe reflejarlo.
    assert "120,000" in out["reply"] or "120.000" in out["reply"]


def test_perfil_repetido_no_se_duplica():
    """Agregar el mismo perfil dos veces no lo cobra dos veces."""
    fields = dict(BASE, _awaiting_additional_test="add",
                  _extra_profiles=[{"code": "1331", "name": "Panel Función Hepática",
                                    "price": 90000}])
    with patch.object(confirmacion.db, "get_tests_by_codes_or_names", return_value=[]), \
         patch.object(confirmacion.db, "get_catalog_profiles_by_codes", return_value=[PANEL_1331]), \
         _sin_areas():
        out = confirmacion._confirmation_analysis_adjustment(SESSION, fields, "1331", None)

    assert out is not None
    assert [p["code"] for p in fields["_extra_profiles"]] == ["1331"]


def test_agregar_analisis_normal_en_confirmacion_sigue_igual():
    """Control (paso aprobado): un análisis del catálogo se agrega como siempre."""
    fields = dict(BASE, _awaiting_additional_test="add")

    def _tests(items):
        wanted = " ".join(str(i).lower() for i in items)
        return [HEMOGRAMA] if ("hemograma" in wanted or "201" in wanted) else []

    with patch.object(confirmacion.db, "get_tests_by_codes_or_names", side_effect=_tests), \
         _sin_areas():
        out = confirmacion._confirmation_analysis_adjustment(SESSION, fields, "hemograma", None)

    assert out is not None
    assert "201" in (fields.get("selected_tests") or [])
    assert "_awaiting_additional_test" not in fields


def test_si_tras_pregunta_legitima_de_agregar_no_cierra_en_falso():
    """Control: si el bot ACABA de preguntar '¿qué análisis quieres agregar?' dentro de la
    confirmación y el cliente dice 'si', se repregunta (no se cierra ni se inventa nada)."""
    fields = dict(BASE, _awaiting_additional_test="add")

    with patch.object(confirmacion.db, "get_tests_by_codes_or_names", return_value=[]), \
         patch.object(confirmacion.db, "get_catalog_profiles_by_codes", return_value=[]), \
         patch.object(confirmacion.db, "find_catalog_profile", return_value=None), \
         _sin_areas():
        out = confirmacion._confirmation_analysis_adjustment(SESSION, fields, "si", None)

    assert out is not None
    assert "agregar" in out["reply"]
    assert not fields.get("_extra_profiles")
