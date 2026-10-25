"""Capturas locales de pantallas reales para el informe demostrativo de A3."""
import os
import re
import sys
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "data" / "evidencias-informe-demostrativo-a3"
LOCAL_CSS = "\n".join(
    (ROOT / "app" / "static" / name).read_text(encoding="utf-8")
    for name in ("os-kit.css", "app.css", "portal.css")
)


def _safe_environment() -> None:
    values = {
        "TELEGRAM_BOT_TOKEN": "demo-token", "TELEGRAM_WEBHOOK_SECRET": "demo-secret",
        "TELEGRAM_WEBHOOK_URL": "https://demo.invalid/webhook", "SUPABASE_URL": "https://demo.invalid",
        "SUPABASE_SERVICE_ROLE_KEY": "eyJhbGciOiJIUzI1NiJ9.eyJyb2xlIjoic2VydmljZV9yb2xlIn0.demo",
        "OPENAI_API_KEY": "demo-key", "FLASK_SECRET_KEY": "demo-secret",
        "DASHBOARD_ADMIN_PASSWORD": "demo-password", "APP_ENV": "test",
        "PLATFORM_API_TOKEN": "demo-platform-token", "ANARVET_ENABLED": "false",
        "ALEGRA_ENABLED": "false", "PORTAL_DEMO_MODE": "false",
    }
    os.environ.update(values)


def _decorate(html: str) -> str:
    banner = "<div class=\"evidence-banner\">CAPTURA DEMOSTRATIVA LOCAL · datos ficticios · no prueba de disponibilidad en producción</div>"
    style = "<style>.evidence-banner{position:fixed;z-index:9999;right:14px;bottom:14px;padding:7px 10px;border-radius:5px;background:#122238;color:#fff;font:600 11px Arial;letter-spacing:.2px;box-shadow:0 2px 10px #0005}</style>"
    html = re.sub(r'<link[^>]+href="/static/[^"]+"[^>]*>', "", html)
    html = html.replace("</head>", f"<style>{LOCAL_CSS}</style>{style}</head>")
    return re.sub(r"(<body\b[^>]*>)", r"\1" + banner, html, count=1)


def _write_shot(page, name: str, html: str) -> None:
    page.set_content(_decorate(html), wait_until="load")
    page.wait_for_timeout(500)
    page.screenshot(path=str(OUT / f"{name}.png"), full_page=False)


def _motorizados_html(app):
    from flask import render_template, session
    from app.dashboard import _empty_context

    context = _empty_context()
    couriers = [
        {"id": "courier-1", "name": "Camila Demo", "phone": "300 000 0101", "availability": "available", "color": "#7a0d20", "is_active": True, "source": "db", "zone_number": 3, "coverage_count": 3, "clients_count_from_coverage": 24, "localities_text": "Bosa, Kennedy, Fontibón", "chatwoot_conversation_id": "1001"},
        {"id": "courier-2", "name": "Diego Demo", "phone": "300 000 0102", "availability": "on_route", "color": "#0e7490", "is_active": True, "source": "db", "zone_number": 5, "coverage_count": 2, "clients_count_from_coverage": 15, "localities_text": "Engativá, Suba", "chatwoot_conversation_id": "1002"},
    ]
    context.update({
        "couriers_rows": couriers, "couriers_options": couriers,
        "motorizados_summary": {"coverage_rate": 85, "assigned_localities": 17, "total_localities": 20, "clients_in_assigned_localities": 39, "clients_in_catalog_localities": 42, "clients_in_unassigned_localities": 3, "localities_with_clients_without_coverage": 1, "busiest_courier_name": "Camila Demo", "busiest_courier_clients": 24},
        "motorizados_alerts": [{"level": "warning", "title": "Cobertura pendiente", "detail": "1 localidad demostrativa sin asignar."}],
        "territorial_zone_rows": [{"zone_number": 3, "courier_name": "Camila Demo", "total_barrios": 124, "total_upz": 3, "localities_text": "Bosa, Kennedy"}, {"zone_number": 5, "courier_name": "Diego Demo", "total_barrios": 91, "total_upz": 2, "localities_text": "Engativá, Suba"}],
        "localities_rows": [{"locality_name": "Bosa", "coverage_state": "Cobertura configurada", "clients_count": 12, "locality_code": "bosa", "assigned_courier_id": "courier-1"}, {"locality_name": "Kennedy", "coverage_state": "Cobertura configurada", "clients_count": 12, "locality_code": "kennedy", "assigned_courier_id": "courier-1"}, {"locality_name": "Suba", "coverage_state": "Cobertura configurada", "clients_count": 15, "locality_code": "suba", "assigned_courier_id": "courier-2"}],
    })
    with app.test_request_context("/motorizados"):
        session["dashboard_authenticated"] = True
        session["dashboard_username"] = "Equipo A3"
        return render_template("dashboard.html", active_tab="motorizados", context=context, username="Equipo A3", notice="", notice_type="info")


def _agenda_html(app):
    from flask import render_template, session

    monday = date(2026, 9, 21)
    columns = [{"clave": (monday + timedelta(days=i)).isoformat(), "nombre": day, "dia": (monday + timedelta(days=i)).strftime("%d/%m"), "hoy": i == 1} for i, day in enumerate(("Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado"))]
    days = {column["clave"]: [] for column in columns}
    days["2026-09-22"] = [{"id": "request-1", "order_number": "A3-DEMO-001", "patient_name": "Luna", "pickup_address": "Dirección demostrativa", "assigned_courier_id": "courier-1", "clients": {"clinic_name": "Clínica Demostración"}}]
    days["2026-09-24"] = [{"id": "request-2", "order_number": "A3-DEMO-002", "patient_name": "Max", "pickup_address": "Dirección demostrativa", "assigned_courier_id": "courier-1", "clients": {"clinic_name": "Veterinaria Ejemplo"}}]
    couriers = [{"id": "courier-1", "name": "Camila Demo"}, {"id": "courier-2", "name": "Diego Demo"}]
    rows = [{"id": "courier-1", "nombre": "Camila Demo", "color": "#7a0d20", "total": 2, "dias": days}, {"id": "courier-2", "nombre": "Diego Demo", "color": "#0e7490", "total": 0, "dias": {key: [] for key in days}}, {"id": "sin_asignar", "nombre": "Sin asignar", "color": "", "total": 0, "dias": {key: [] for key in days}}]
    with app.test_request_context("/agenda?semana=2026-09-21"):
        session["dashboard_authenticated"] = True
        session["dashboard_username"] = "Equipo A3"
        return render_template("dashboard_agenda.html", username="Equipo A3", columnas=columns, filas=rows, couriers=couriers, total=2, semana_actual="2026-09-21", semana_anterior="2026-09-14", semana_siguiente="2026-09-28", rango="21/09 al 26/09/2026")


def _portal_html(app, template: str, **context):
    from flask import render_template, session

    with app.test_request_context("/portal/mis/solicitudes"):
        session["portal_client_id"] = "11111111-1111-1111-1111-111111111111"
        session["portal_clinic_name"] = "Clínica Demostración"
        with patch("app.services.portal_db.count_unread_notifications", return_value=2):
            return render_template(template, **context)


def _results_html(app, mirror: bool = False):
    from flask import render_template, session

    context = {"vista": "anarvet" if mirror else "informes", "username": "Equipo A3", "anarvet_enabled": True, "filters": {"patient": "", "owner": "", "clinic": "", "order_number": "", "date_from": "", "date_to": ""}, "results": [{"id": "33333333-3333-3333-3333-333333333333", "created_at": "2026-09-22", "order_number": "A3-DEMO-001", "clients": {"clinic_name": "Clínica Demostración"}, "patient_name": "Luna", "owner_name": "Paciente demostrativo", "exam_name": "Hemograma", "published": True}], "preset_client": None, "anarvet_informes": [{"codigo": "DEMO-100", "fecha_solicitud": "2026-09-22", "nombre_cliente": "Clínica Demostración", "mascota": "Luna", "nombre_propietario": "Paciente demostrativo", "especie": "Canino", "raza": "Mestizo", "examen_codigos": "H4", "analitos": 12, "analitos_validados": 12, "ultima_validacion": "2026-09-22", "cod_cliente": "DEMO"}], "anarvet_total": 1, "anarvet_page": 1, "anarvet_pages": 1, "anarvet_filters": {"search": "", "cod_cliente": "", "date_from": "2026-09-15", "date_to": ""}}
    with app.test_request_context("/resultados?vista=anarvet" if mirror else "/resultados"):
        session["dashboard_authenticated"] = True
        session["dashboard_username"] = "Equipo A3"
        return render_template("dashboard_results.html", **context)


def _billing_html(app):
    from flask import render_template, session
    from app.dashboard import _empty_context

    context = _empty_context()
    context.update({"alegra_enabled": True, "invoices_actions_locked": True, "billing_view": "facturas", "invoices_metrics": {"today_count": 1, "month_total": 320000, "year_total": 320000, "avg_ticket": 320000, "invoices_count": 1}, "invoices_total": 1, "invoice_status_options": [{"value": "draft", "label": "Borrador"}], "invoices_rows": [{"alegra_invoice_id": "demo-1", "number": "DEMO-001", "invoice_date": "2026-09-22", "client_name": "Clínica Demostración", "client_nit": "900000000-1", "document_type": "Factura", "number_template": "DEMO", "subtotal": 320000, "tax": 0, "total": 320000, "status": "draft", "request_id": "request-demo", "origin": "pedido"}], "invoices_pages": 1, "invoices_page": 1})
    with app.test_request_context("/facturacion"):
        session["dashboard_authenticated"] = True
        session["dashboard_username"] = "Equipo A3"
        return render_template("dashboard.html", active_tab="facturacion", context=context, username="Equipo A3", notice="", notice_type="info")


def main() -> int:
    _safe_environment()
    from app.main import app
    from playwright.sync_api import sync_playwright

    OUT.mkdir(parents=True, exist_ok=True)
    request_filters = {"patient": "", "order_number": "", "status": "", "date_from": "", "date_to": ""}
    shots = {
        "01-motorizados": _motorizados_html(app), "02-agenda": _agenda_html(app),
        "03-portal-solicitudes": _portal_html(app, "portal/client_requests.html", requests=[{"id": "11111111-1111-1111-1111-111111111111", "order_number": "A3-DEMO-001", "requested_at": "2026-09-22", "patient_name": "Luna", "exam_type": "Hemograma", "scheduled_pickup_date": "2026-09-22", "couriers": {"name": "Camila Demo"}, "status": "on_route"}], filters=request_filters, status_labels={"on_route": "En ruta", "in_lab": "En laboratorio"}, active_tab="solicitudes"),
        "04-portal-resultados": _portal_html(app, "portal/client_results.html", results=[{"id": "22222222-2222-2222-2222-222222222222", "published_at": "2026-09-22", "order_number": "A3-DEMO-001", "patient_name": "Luna", "owner_name": "Paciente demostrativo", "exam_name": "Hemograma"}], filters={"patient": "", "order_number": "", "date_from": "", "date_to": ""}, active_tab="resultados"),
        "05-anarvet": _results_html(app, mirror=True), "06-facturacion": _billing_html(app),
    }
    with sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(channel="chrome")
        except Exception:
            browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1500, "height": 1000}, device_scale_factor=1)
        for name, html in shots.items():
            _write_shot(page, name, html)
        browser.close()
    assert all(path.stat().st_size > 10000 for path in OUT.glob("*.png"))
    print(f"Capturas: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
