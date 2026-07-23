"""
Regresión ERR-077 (prueba en vivo del usuario, 2026-07-21, chat 10): el bot ofreció un
menú de 6 perfiles recomendados, el cliente respondió "1, 3 y 6" y la orden quedó SOLO
con el 101 Perfil Parasitológico I. El 103 ($40.000) y el 1331 ($90.000) se perdieron sin
ninguna señal, y al insistir ("Te pedí el 1, 3 y 6") el bot respondió con la oferta
genérica de agregar análisis.

Causa: `_select_profile_from_menu` hacía `picks[0]` sobre una selección que el parser YA
resolvía completa ("un perfil es una sola elección"), y `_capture_profile_menu_selection`
borraba `_profile_menu_options`, así que la insistencia tampoco tenía contra qué matchear.

Es un bug de DINERO: la orden se confirma por $30.000 en vez de $160.000.
"""
from unittest.mock import patch

from app import agent, orders
from app.menus import _select_tests_from_menu

MENU = [
    {"code": "101", "name": "Perfil Parasitológico I", "price": 30000,
     "category": "Parasitológico", "species": "ambos", "description": "Coprológico"},
    {"code": "102", "name": "Perfil Parasitológico II", "price": 23000,
     "category": "Parasitológico", "species": "ambos", "description": "Copro, Coproscópico"},
    {"code": "103", "name": "Perfil Parasitológico III", "price": 40000,
     "category": "Parasitológico", "species": "ambos", "description": "3 seriadas"},
    {"code": "104", "name": "Perfil Parasitológico IV", "price": 25000,
     "category": "Parasitológico", "species": "ambos", "description": "Orina y Copro"},
    {"code": "1330", "name": "Panel Control de Salud", "price": 108000,
     "category": "Panel", "species": "ambos", "description": "Albúmina, ALT"},
    {"code": "1331", "name": "Panel Función Hepática", "price": 90000,
     "category": "Panel", "species": "ambos", "description": "Albúmina, AST"},
]

# Orden completa salvo el análisis: así el resumen se arma y el total es verificable.
FULL_ORDER = {
    "_client_found": True, "clinic_name": "Centro Veterinario La Uribe",
    "pickup_address": "AV CL 32 19-26", "requesting_doctor": "Diana Pérez",
    "patient_name": "Fifi", "species": "Equino", "breed": "Cuarto de Milla",
    "sex": "Macho", "patient_age": "5 años", "owner_name": "Jorge Toro",
    "observations": "Ninguna", "payment_method": "Efectivo",
}


def _profiles_by_codes(codes, species=None):
    wanted = {str(c) for c in codes}
    return [p for p in MENU if p["code"] in wanted]


def test_parser_ya_resolvia_los_tres():
    """El parser NUNCA fue el problema: detecta los 3. La pérdida era posterior."""
    picks = _select_tests_from_menu("1, 3 y 6", MENU)
    assert [p["code"] for p in picks] == ["101", "103", "1331"]


def test_seleccion_multiple_conserva_los_tres_perfiles():
    """'1, 3 y 6' deja los 3 perfiles en la orden, no solo el primero."""
    fields = dict(FULL_ORDER, _profile_menu_options=list(MENU))
    picks = agent._select_profiles_from_menu("1, 3 y 6", MENU)
    assert [p["code"] for p in picks] == ["101", "103", "1331"]

    with patch.object(orders.db, "get_catalog_profiles_by_codes", side_effect=_profiles_by_codes):
        out = orders._capture_profile_menu_selection(
            {"client_id": "c1"}, fields, picks[0], "1, 3 y 6", extra_profiles=picks[1:]
        )

    captured = out["captured_fields"]
    assert captured["_selected_profile_code"] == "101"
    extra = [p["code"] for p in captured.get("_extra_profiles") or []]
    assert extra == ["103", "1331"], "los perfiles 3 y 6 se perdieron"
    # El acuse nombra los tres: el cliente debe poder ver que no se perdió nada.
    assert "Parasitológico III" in out["reply"] and "Función Hepática" in out["reply"]


def test_el_resumen_suma_los_perfiles_extra():
    """Bug de DINERO: el total debe ser 30.000 + 40.000 + 90.000, no 30.000."""
    fields = dict(
        FULL_ORDER,
        exam_type="Perfil Parasitológico I",
        _selected_profile_code="101",
        _selected_profile_name="Perfil Parasitológico I",
        _selected_profile_price=30000,
        _extra_profiles=[
            {"code": "103", "name": "Perfil Parasitológico III", "price": 40000},
            {"code": "1331", "name": "Panel Función Hepática", "price": 90000},
        ],
    )
    with patch.object(orders.db, "get_tests_by_codes_or_names", return_value=[]):
        summary = orders._route_confirmation_summary(fields)

    assert summary is not None
    assert "Perfil Parasitológico III" in summary
    assert "Panel Función Hepática" in summary
    assert "160,000" in summary or "160.000" in summary


def test_seleccion_simple_no_cambia():
    """Control: 'el 1' sigue capturando UN perfil, sin residuo de extras (paso aprobado)."""
    fields = dict(FULL_ORDER, _profile_menu_options=list(MENU))
    picks = agent._select_profiles_from_menu("el 1", MENU)
    assert [p["code"] for p in picks] == ["101"]

    with patch.object(orders.db, "get_catalog_profiles_by_codes", side_effect=_profiles_by_codes):
        out = orders._capture_profile_menu_selection(
            {"client_id": "c1"}, fields, picks[0], "el 1", extra_profiles=picks[1:]
        )
    assert not out["captured_fields"].get("_extra_profiles")


def test_perfil_nuevo_no_arrastra_extras_de_una_orden_previa():
    """Multiorden: al fijar otro perfil base, los extras de la orden anterior no siguen."""
    fields = dict(
        FULL_ORDER,
        _profile_menu_options=list(MENU),
        _extra_profiles=[{"code": "103", "name": "Perfil Parasitológico III", "price": 40000}],
    )
    with patch.object(orders.db, "get_catalog_profiles_by_codes", side_effect=_profiles_by_codes):
        out = orders._capture_profile_menu_selection(
            {"client_id": "c1"}, fields, MENU[1], "el 2", extra_profiles=[]
        )
    assert not out["captured_fields"].get("_extra_profiles")
