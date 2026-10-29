"""El Panel mostraba todo en 0 aunque el laboratorio estaba trabajando (ERR-191).

Se suma la actividad REAL de Anarvet (informes de hoy, 7 días y mes), la fecha de la última
conversación del bot, y los avisos de «sin datos» que nunca se activaban. Motorizados cuenta
los municipios en la cobertura (decía «100% · 0 pendientes» con 5 zonas sin motorizado).
"""
from datetime import date
from unittest.mock import patch

from app import panel_laboratorio


def _en_serie(**lecturas):
    salida = {}
    for nombre, (fn, defecto) in lecturas.items():
        try:
            salida[nombre] = fn()
        except Exception:  # noqa: BLE001
            salida[nombre] = defecto
    return salida


def _conteo(filtros, page, per_page):
    return [], {("2026-10-29", "2026-10-29"): 12, ("2026-10-23", "2026-10-29"): 140,
                ("2026-10-01", "2026-10-29"): 610}[(filtros["date_from"], filtros["date_to"])]


def test_cuenta_los_informes_de_hoy_semana_y_mes(monkeypatch):
    monkeypatch.setattr(panel_laboratorio, "ANARVET_ENABLED", True)
    with patch("app.panel_laboratorio.db.list_anarvet_informes", side_effect=_conteo), \
         patch("app.panel_laboratorio.db.max_anarvet_fecha_solicitud", return_value="2026-10-29"), \
         patch("app.panel_laboratorio.db.list_sessions", return_value=[{"updated_at": "2026-10-21T02:10:00+00:00"}]):
        r = panel_laboratorio.resumen(_en_serie, hoy=date(2026, 10, 29))

    assert (r["informes_hoy"], r["informes_semana"], r["informes_mes"]) == (12, 140, 610)
    assert r["ultimo_informe"] == "29/10/2026"
    assert r["ultima_conversacion"] == "20/10/2026"  # 02:10 UTC del 21 = 21:10 del 20 en Bogotá


def test_si_anarvet_falla_queda_en_blanco_sin_romper(monkeypatch):
    monkeypatch.setattr(panel_laboratorio, "ANARVET_ENABLED", True)
    with patch("app.panel_laboratorio.db.list_anarvet_informes", side_effect=RuntimeError("caído")), \
         patch("app.panel_laboratorio.db.max_anarvet_fecha_solicitud", side_effect=RuntimeError("caído")), \
         patch("app.panel_laboratorio.db.list_sessions", return_value=[]):
        r = panel_laboratorio.resumen(_en_serie, hoy=date(2026, 10, 29))

    assert r["informes_hoy"] is None and r["ultimo_informe"] == "" and r["ultima_conversacion"] == ""


def test_el_panel_muestra_el_laboratorio_y_explica_los_ceros():
    from flask import render_template
    from app.main import app
    from tests.test_dashboard import _base_context

    lab = {"anarvet": True, "informes_hoy": 12, "informes_semana": 140, "informes_mes": 610,
           "ultimo_informe": "29/10/2026", "ultima_conversacion": "20/10/2026"}
    contexto = _base_context(actividad_lab=lab, exec_billing={"month_total_fmt": "$0", "today_count": 0},
                             exec_requests_daily=[{"date": "2026-10-29", "count": 0}])
    with app.test_request_context("/dashboard"):
        html = render_template("dashboard.html", active_tab="dashboard", context=contexto)

    assert "Informes de hoy" in html and ">12<" in html and ">610<" in html
    assert "la última conversación del bot fue el 20/10/2026" in html
    assert "Sin solicitudes del bot ni del portal en los últimos 30 días." in html
    assert 'id="chart-requests-daily"' not in html


def test_motorizados_cuenta_los_municipios_en_la_cobertura():
    from app.dashboard import _build_motorizados_context

    clientes = [{"id": "a", "clinic_name": "Wavet", "city": "Soacha", "is_active": True, "client_courier_assignment": []}]
    soacha = {"code": "soacha", "name": "Soacha", "is_active": True, "lat": 4.58, "lng": -74.21}
    with patch("app.dashboard.db.list_couriers", return_value=[]), \
         patch("app.dashboard.db.list_courier_locality_coverage", return_value=[]), \
         patch("app.dashboard.db.list_territorial_zones", return_value=[]), \
         patch("app.dashboard.db.list_territorial_neighborhoods", return_value=[]), \
         patch("app.dashboard.maestros_db.list_municipios", return_value=[soacha]):
        resumen = _build_motorizados_context(clientes)["motorizados_summary"]

    assert resumen["total_localities"] == 21  # 20 localidades de Bogotá + Soacha
    assert resumen["clients_in_catalog_localities"] == 1
    assert resumen["clients_in_unassigned_localities"] == 1  # antes daba 0 al lado de «1 con riesgo»
    assert resumen["clients_total"] == 1
