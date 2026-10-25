"""Graba el video-recorrido de la plataforma A3 (solo lectura) y lo deja en MP4.

Uso: python tools/scripts/video_plataforma_a3.py
Levanta la app con video_demo_seguro (lee datos reales, no escribe nada), precarga las
pantallas y graba con Playwright un recorrido con subtítulos. Salida: output/video/.
"""
import csv
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import video_demo_seguro as demo  # noqa: E402
import video_placas as placas  # noqa: E402

ROOT = demo.ROOT
SALIDA = ROOT / "output" / "video"
BASE = f"http://127.0.0.1:{demo.PUERTO}"
CLINICA = "Emergencias Veterinarias Integrales"
ANARVET = "/resultados/anarvet?date_from=2026-08-01"
PANTALLAS = ["/dashboard", "/clientes", "/clientes/nuevo", "/muestras", "/motorizados", "/agenda",
             "/cargas", "/facturacion", ANARVET, "/portal/login"]


def _csv_demo(db) -> Path:
    tests = [t for t in db.list_catalog_tests(limit=50) if t.get("code") and t.get("price")][:2]
    ruta = SALIDA / "precios-ejemplo.csv"
    with ruta.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["codigo", "precio"])
        w.writerow([tests[0]["code"], tests[0]["price"]])
        w.writerow([tests[1]["code"], int(tests[1]["price"]) + 1000])
        w.writerow(["99999", "45000"])
        w.writerow([tests[0]["code"], "sin precio"])
    return ruta


def _ir(page, ruta, chip, texto, espera=4500):
    page.goto(BASE + ruta, wait_until="networkidle")
    placas.subtitulo(page, chip, texto)
    page.wait_for_timeout(espera)


def _paso(page, chip, texto, espera=4500):
    placas.subtitulo(page, chip, texto)
    page.wait_for_timeout(espera)


def _recorrido(page, db, nit, csv_ruta):
    placas.portada(page)
    _ir(page, "/login", "dev", "Ingreso del personal de A3. Hoy es un acceso compartido; se desarrolla el usuario propio por persona con tres perfiles (A2).", 6500)
    _ir(page, "/dashboard", "ok", "Panel ejecutivo: facturación del mes, alertas y carga operativa.")
    placas.desplazar(page, 3)
    _ir(page, "/clientes", "ok", "Clientes: los 1.013 clientes de A3 con NIT, dirección, motorizado y estado.")
    page.fill("[data-client-suggest]", "Emergencias")
    page.wait_for_timeout(2500)
    _paso(page, "ok", "Búsqueda por clínica, NIT, teléfono o correo.", 3000)
    page.goto(BASE + f"/clientes/{db.find_clients_by_tax_id(nit)[0]['id']}", wait_until="networkidle")
    _paso(page, "ok", "Ficha del cliente: se editan datos, NIT, dirección y motorizado, y se activa o desactiva.", 5500)
    placas.desplazar(page, 2)
    _ir(page, "/clientes/nuevo", "ok", "Alta de un cliente nuevo desde la plataforma.")
    _ir(page, "/muestras", "ok", "Catálogo y lista de precios: perfiles y análisis con su precio y especie.")
    placas.resaltar(page, "[data-catalog-edit]")
    page.click("[data-catalog-edit] >> nth=0")
    _paso(page, "ok", "Edición del precio y la especie de cada análisis o perfil. Cada cambio de precio queda registrado.", 5500)
    placas.resaltar(page, "details[data-discount-card] summary")
    page.click("details[data-discount-card] summary")
    _paso(page, "ok", "Descuentos por volumen, editables por A3.", 4500)
    _ir(page, "/motorizados", "ok", "Motorizados: se crean, editan, activan y desactivan (nombre, teléfono, disponibilidad y chat de avisos).", 6000)
    placas.resaltar(page, "#courier-coverage-map")
    _paso(page, "dev", "Cobertura y mapa: hoy muestran las localidades de Bogotá. Se agregan los municipios cercanos con su motorizado (A5).", 7000)
    _ir(page, "/agenda", "ok", "Agenda semanal por motorizado (recogidas de ejemplo, no reales).", 4500)
    placas.resaltar(page, "[data-agenda-courier]")
    selector = page.locator("[data-agenda-courier]").first
    opciones = selector.locator("option").all_inner_texts()
    selector.select_option(index=min(2, len(opciones) - 1))
    _paso(page, "ok", "Reasignar una recogida a otro motorizado: se guarda y se le avisa.", 5000)
    _paso(page, "part", "Se completa: reemplazar a un motorizado por día o por zona en un solo paso (A6).", 5500)
    _ir(page, "/cargas", "ok", "Cargas masivas de precios, clientes y portafolio por archivo.", 4000)
    page.select_option("select[name=tipo]", "precios")
    page.set_input_files("input[name=csv]", str(csv_ruta))
    page.wait_for_timeout(1200)
    page.click("button:has-text('Ver qué va a pasar')")
    page.wait_for_load_state("networkidle")
    _paso(page, "ok", "Antes de aplicar se ve qué cambia, qué queda igual y qué filas tienen error. Nada se guarda sin confirmar.", 7000)
    placas.desplazar(page, 3)
    _paso(page, "part", "Se completa: plantillas descargables y exportación a Excel de clientes, precios y motorizados (A4).", 5500)
    _ir(page, "/facturacion", "ok", "Facturación conectada a Alegra, con facturas y cartera por cliente.", 5000)
    placas.desplazar(page, 2)
    _paso(page, "dev", "Hito 1: la factura se emite sola al confirmarse el pago, pago en línea con Wompi y pago aplicado en Alegra.", 6500)
    _ir(page, ANARVET, "ok", "Resultados: espejo de los informes de Anarvet, sincronizado con el laboratorio.", 5000)
    enlace = page.locator("a[href*='/resultados/anarvet/']:not([target='_blank']):not([href$='/clientes'])").first
    if enlace.count():
        enlace.click()
        page.wait_for_load_state("networkidle")
        _paso(page, "ok", "Cada informe se abre completo y se publica en PDF para la veterinaria.", 6000)
    _ir(page, "/portal/login", "ok", "Portal de clientes: la veterinaria entra con su nombre y NIT.", 3500)
    page.fill("input[name=clinic_name]", CLINICA)
    page.fill("input[name=nit]", nit)
    page.wait_for_timeout(1200)
    page.click("button:has-text('Ingresar')")
    page.wait_for_load_state("networkidle")
    if page.locator("button:has-text('Entrar con esta sede')").count():
        page.click("button:has-text('Entrar con esta sede')")
        page.wait_for_load_state("networkidle")
    _ir(page, "/portal/mis/solicitudes/nueva", "ok", "La veterinaria crea su solicitud de recogida y elige los análisis.", 5500)
    _ir(page, "/portal/mis/resultados", "ok", "Aquí la veterinaria consulta y descarga los resultados que el laboratorio le publica.", 4500)
    _ir(page, "/portal/mis/cuenta", "ok", "Estado de cuenta del cliente.", 4000)
    _paso(page, "dev", "Se agrega: botones de acceso al portal desde la página web de A3 (A7).", 5000)
    placas.cierre(page)


def main() -> int:
    from playwright.sync_api import sync_playwright
    SALIDA.mkdir(parents=True, exist_ok=True)
    app = demo.preparar_app()
    from app.services import db
    cliente = next(c for c in db._client.table("clients").select("clinic_name, tax_id")
                   .eq("clinic_name", CLINICA).execute().data if c.get("tax_id"))
    nit = str(cliente["tax_id"])
    pre = app.test_client()
    for ruta in PANTALLAS:
        pre.get(ruta)
    csv_ruta = _csv_demo(db)
    demo.levantar_servidor(app)
    with sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(channel="chrome")
        except Exception:
            browser = pw.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1280, "height": 720}, locale="es-CO",
                                  record_video_dir=str(SALIDA), record_video_size={"width": 1280, "height": 720})
        page = ctx.new_page()
        _recorrido(page, db, nit, csv_ruta)
        webm = Path(page.video.path())
        ctx.close()
        browser.close()
    mp4 = SALIDA / "Recorrido_Plataforma_A3_2026-10-09.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(webm), "-c:v", "libx264", "-preset", "slow",
                    "-crf", "24", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(mp4)], check=True)
    webm.unlink(missing_ok=True)
    print(f"VIDEO: {mp4} ({mp4.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
