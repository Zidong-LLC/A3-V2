"""El menú lateral es uno solo, y la sección de Muestras queda con catálogo y perfiles.

El menú estaba copiado a mano en ocho plantillas y no todas tenían la misma lista: al
entrar a Agenda, Cargas, Resultados o la ficha del cliente desaparecían Solicitudes y
Pedidos.
"""
import pathlib
import re
from unittest.mock import patch

PLANTILLAS = sorted(pathlib.Path("app/templates").glob("dashboard*.html"))
SECCIONES = ("Panel", "Operacion", "Clientes", "Solicitudes", "Pedidos", "Facturacion",
             "Motorizados", "Agenda", "Muestras", "Resultados", "Cargas")


def _get_test_client():
    from app.main import app

    app.config["TESTING"] = True
    return app.test_client()


def _login(client):
    with client.session_transaction() as sess:
        sess["dashboard_authenticated"] = True
        sess["dashboard_username"] = "admin"


def _contexto(**extra):
    from tests.test_dashboard import _base_context

    return _base_context(client_type_options={}, vat_regime_options={},
                         motorizados_summary={}, **extra)


# ── El menú ──────────────────────────────────────────────────────────────────

def test_ninguna_plantilla_escribe_su_propio_menu():
    """Si alguien vuelve a copiarlo a mano, este test lo detecta."""
    propias = [p.name for p in PLANTILLAS if '<aside class="crm-sidebar">' in p.read_text(encoding="utf-8")]
    assert propias == [], f"estas plantillas tienen su propio menú: {propias}"


def test_todas_incluyen_el_menu_compartido():
    sin_menu = [p.name for p in PLANTILLAS if "_sidebar.html" not in p.read_text(encoding="utf-8")]
    assert sin_menu == []


def test_el_menu_compartido_tiene_las_once_secciones():
    parcial = (pathlib.Path("app/templates") / "_sidebar.html").read_text(encoding="utf-8")
    etiquetas = re.findall(r"'([A-ZÁÉÍÓÚ][a-záéíóú]+)'\)", parcial)
    for seccion in SECCIONES:
        assert seccion in parcial, seccion
    assert "Cerrar sesion" in parcial


def test_cada_pantalla_muestra_las_once_secciones():
    client = _get_test_client()
    _login(client)
    with patch("app.dashboard.build_dashboard_context", return_value=_contexto()), \
         patch("app.dashboard.db.list_pedidos_for_dashboard", return_value=[]), \
         patch("app.dashboard_agenda.db.list_pickups_between", return_value=[]), \
         patch("app.dashboard_agenda.db.list_active_couriers", return_value=[]):
        for ruta in ("/dashboard", "/clientes", "/solicitudes", "/pedidos", "/muestras", "/agenda"):
            cuerpo = client.get(ruta).get_data(as_text=True)
            faltan = [s for s in SECCIONES if f"<span>{s}</span>" not in cuerpo]
            assert faltan == [], f"a {ruta} le faltan {faltan}"


# ── Muestras: catálogo y perfiles ────────────────────────────────────────────

def test_la_seccion_ya_no_trae_el_proceso_de_muestras():
    client = _get_test_client()
    _login(client)
    with patch("app.dashboard.build_dashboard_context", return_value=_contexto()):
        cuerpo = client.get("/muestras").get_data(as_text=True)
    assert "data-sample-process-board" not in cuerpo
    assert 'data-tab-panel="proceso"' not in cuerpo
    assert "Catalogo y perfiles" in cuerpo
    assert "Perfiles personalizados" in cuerpo


def test_los_descuentos_arrancan_plegados_con_su_resumen():
    client = _get_test_client()
    _login(client)
    tramos = [{"min_tests": 2, "pct": 0.12}, {"min_tests": 10, "pct": 0.27}]
    with patch("app.dashboard.build_dashboard_context", return_value=_contexto(discount_tiers_rows=tramos)):
        cuerpo = client.get("/muestras").get_data(as_text=True)
    assert '<details class="catalog-panel discount-panel"' in cuerpo
    assert "open" not in cuerpo.split("discount-panel")[1][:60]   # arranca cerrado
    # Los tramos se guardan como fracción: el resumen los muestra en porcentaje.
    assert "(12%) hasta 27%" in cuerpo


def test_el_catalogo_avisa_cuando_nada_coincide():
    client = _get_test_client()
    _login(client)
    with patch("app.dashboard.build_dashboard_context", return_value=_contexto()):
        cuerpo = client.get("/muestras").get_data(as_text=True)
    assert "data-builder-count" in cuerpo
    assert "Ningun perfil ni analisis coincide" in cuerpo


# ── Perfiles guardados ───────────────────────────────────────────────────────

def test_los_perfiles_guardados_se_agrupan_por_veterinaria():
    client = _get_test_client()
    _login(client)
    perfiles = [
        {"id": "p-1", "name": "Perfil A", "client_name": "Animal Pets", "items_json": [], "created_at": "2026-08-25T22:09:00"},
        {"id": "p-2", "name": "Perfil B", "client_name": "Animal Pets", "items_json": [], "created_at": "2026-08-25T22:10:00"},
        {"id": "p-3", "name": "Perfil C", "client_name": "Zoopecas", "items_json": [], "created_at": "2026-08-26T09:00:00"},
    ]
    with patch("app.dashboard.build_dashboard_context", return_value=_contexto(custom_profiles=perfiles)):
        cuerpo = client.get("/muestras").get_data(as_text=True)
    assert cuerpo.count("data-profiles-group") == 2          # un grupo por veterinaria
    assert cuerpo.count("custom-profile-card") >= 3          # los tres perfiles
    assert "data-profiles-search" in cuerpo
    assert "25/08 22:09" in cuerpo                            # fecha legible, no el ISO
    assert "data-rename-profile" in cuerpo


def test_renombrar_exige_nombre_y_no_toca_otros_campos():
    client = _get_test_client()
    _login(client)
    with patch("app.dashboard.db.update_custom_profile", return_value={"id": "p-1"}) as editar:
        vacio = client.post("/api/dashboard/rename-custom-profile", json={"profile_id": "p-1", "name": "   "})
        ok = client.post("/api/dashboard/rename-custom-profile",
                         json={"profile_id": "p-1", "name": " Perfil nuevo ", "items_json": [1]})
    assert vacio.status_code == 400
    assert ok.status_code == 200
    editar.assert_called_once_with("p-1", {"name": "Perfil nuevo"})


def test_update_custom_profile_solo_cambia_el_nombre():
    from unittest.mock import MagicMock

    from app.services import db as dbs

    cliente = MagicMock()
    with patch.object(dbs, "_client", cliente):
        assert dbs.update_custom_profile("p-1", {"name": "  "}) is None
        dbs.update_custom_profile("p-1", {"name": "Nuevo", "client_id": "otro"})
    assert cliente.table.return_value.update.call_args.args[0] == {"name": "Nuevo"}


def test_nada_de_otras_pantallas_depende_del_centro_operativo():
    """Cuatro cosas vivían dentro del bloque que arranca con `if (!panel) return;` del
    Centro Operativo, y ese panel solo existe en /operacion: el editor de descuentos, el
    lápiz del catálogo, el cierre manual de un pedido y el gráfico de tendencias. En sus
    propias pantallas no hacían nada."""
    js = (pathlib.Path("app/static") / "dashboard.js").read_text(encoding="utf-8")
    corte = js.index("const panel = document.getElementById('op-detail-panel')")
    cierre = js.index(chr(10) + "})();", corte)
    for marca in ("data-discount-card", "data-catalog-edit", "data-pedido-close", "exec-metrics-data"):
        assert js.index(marca) > cierre, f"{marca} quedo dentro del bloque del Centro Operativo"


def test_el_editor_de_descuentos_no_usa_ayudas_de_otro_bloque():
    """`postJsonSafe` vive dentro del IIFE grande: usarlo desde afuera reventaba con
    «postJsonSafe is not defined» al guardar."""
    js = (pathlib.Path("app/static") / "dashboard.js").read_text(encoding="utf-8")
    bloque = js[js.index("data-discount-card"):]
    bloque = bloque[:bloque.index("\n})();")]
    codigo = "".join(
        l for l in bloque.splitlines(keepends=True)
        if not l.strip().startswith("//")
    )
    assert "postJsonSafe" not in codigo
    assert "discount-tiers" in codigo



def test_el_constructor_de_perfil_a_medida_se_retiro():
    """Decisión del usuario: registraba muestras sueltas que no se veían en ninguna
    pantalla, y lo que guardaba a mano quedaba fuera del circuito del agente. Los perfiles
    que crea el agente se siguen viendo, buscando, renombrando y borrando."""
    plantilla = (pathlib.Path("app/templates") / "dashboard.html").read_text(encoding="utf-8")
    js = (pathlib.Path("app/static") / "dashboard.js").read_text(encoding="utf-8")
    for marca in ("builder-sticky", "data-builder-client", "data-builder-summary",
                  "data-builder-add", "data-load-profile"):
        assert marca not in plantilla, marca
    assert "data-builder-save-profile" not in js
    # el catálogo conserva su buscador y sus filtros
    assert "data-builder-catalog" in plantilla
    assert "data-builder-search" in plantilla
