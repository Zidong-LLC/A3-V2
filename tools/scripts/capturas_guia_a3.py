"""Capturas de pantalla para la Guía de uso de la plataforma A3.

Uso: python tools/scripts/capturas_guia_a3.py
Levanta la app en modo solo lectura (video_demo_seguro: lee datos reales, no escribe nada)
y guarda cada pantalla en capacitacion/fuentes/img/. Volver a correrlo actualiza la guía.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import video_demo_seguro as demo  # noqa: E402

ROOT = demo.ROOT
IMG = ROOT / "capacitacion" / "fuentes" / "img"
BASE = f"http://127.0.0.1:{demo.PUERTO}"
CLINICA = "Emergencias Veterinarias Integrales"
CSV_DEMO = ROOT / "capacitacion" / "ejemplos" / "clientes_demo_carga_masiva.csv"


def _pantalla(page, ruta, nombre, espera=1200):
    page.goto(BASE + ruta, wait_until="networkidle")
    page.wait_for_timeout(espera)
    page.screenshot(path=str(IMG / f"{nombre}.png"))


def _elemento(page, selector, nombre, espera=600):
    el = page.locator(selector).first
    el.scroll_into_view_if_needed()
    page.wait_for_timeout(espera)
    el.screenshot(path=str(IMG / f"{nombre}.png"))


def _capturas(page, cliente_id, nit):
    _pantalla(page, "/login", "login")
    _pantalla(page, "/dashboard", "panel", 2000)
    _elemento(page, "aside.crm-sidebar", "menu")
    _pantalla(page, "/operacion", "operacion", 1500)
    _pantalla(page, "/clientes", "clientes", 1500)
    _pantalla(page, f"/clientes/{cliente_id}", "ficha")
    _elemento(page, "[data-ficha-cliente]", "ficha_datos")
    _pantalla(page, "/clientes/nuevo", "cliente_nuevo")
    _pantalla(page, "/solicitudes", "solicitudes", 1500)
    _pantalla(page, "/solicitudes/nueva", "solicitud_nueva")
    _pantalla(page, "/pedidos", "pedidos", 1500)
    _pantalla(page, "/motorizados", "motorizados", 2500)
    _elemento(page, "[data-traslado]", "traslado")
    _elemento(page, ".courier-cards .courier-card", "motorizado_tarjeta")
    _elemento(page, "#courier-coverage-map", "mapa", 2500)
    _pantalla(page, "/agenda", "agenda")
    _pantalla(page, "/muestras", "muestras", 1500)
    page.click("[data-catalog-edit] >> nth=0")
    _elemento(page, ".lab-catalog-card", "precio_editar")
    page.click("details[data-discount-card] summary")
    _elemento(page, "details[data-discount-card]", "descuentos")
    _pantalla(page, "/resultados", "resultados")
    _pantalla(page, "/resultados/anarvet?date_from=2026-08-01", "anarvet", 1500)
    enlace = page.locator("a[href*='/resultados/anarvet/']:not([target='_blank']):not([href$='/clientes'])").first
    if enlace.count():
        enlace.click()
        page.wait_for_load_state("networkidle")
        page.screenshot(path=str(IMG / "anarvet_informe.png"))
    _pantalla(page, "/facturacion", "facturacion", 2000)
    _pantalla(page, "/cargas", "cargas")
    page.set_input_files("input[name=csv]", str(CSV_DEMO))
    page.click("button:has-text('Ver qué va a pasar')")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(800)
    page.screenshot(path=str(IMG / "cargas_plan.png"), full_page=True)
    _pantalla(page, "/usuarios", "usuarios")
    page.screenshot(path=str(IMG / "usuarios_completo.png"), full_page=True)
    # Portal de la veterinaria
    page.goto(BASE + "/portal/login", wait_until="networkidle")
    page.screenshot(path=str(IMG / "portal_login.png"))
    page.fill("input[name=clinic_name]", CLINICA)
    page.fill("input[name=nit]", nit)
    page.click("button:has-text('Ingresar')")
    page.wait_for_load_state("networkidle")
    if page.locator("button:has-text('Entrar con esta sede')").count():
        page.click("button:has-text('Entrar con esta sede')")
        page.wait_for_load_state("networkidle")
    _pantalla(page, "/portal/mis/solicitudes", "portal_solicitudes")
    _pantalla(page, "/portal/mis/solicitudes/nueva", "portal_nueva")
    _pantalla(page, "/portal/mis/resultados", "portal_resultados")
    _pantalla(page, "/portal/mis/cuenta", "portal_cuenta")


def main() -> int:
    from playwright.sync_api import sync_playwright
    IMG.mkdir(parents=True, exist_ok=True)
    app = demo.preparar_app()
    from app.services import db
    cliente = db._client.table("clients").select("id, tax_id").eq("clinic_name", CLINICA).execute().data[0]
    demo.levantar_servidor(app)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1.5)
        _capturas(page, cliente["id"], str(cliente["tax_id"]))
        browser.close()
    print(f"{len(list(IMG.glob('*.png')))} capturas en {IMG}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
