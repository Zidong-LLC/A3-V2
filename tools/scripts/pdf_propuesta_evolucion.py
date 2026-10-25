"""Genera el PDF de la propuesta de evolución de la plataforma A3."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HTML = ROOT / "data" / "propuesta-evolucion-a3-20260928.html"
PDF = ROOT / "output" / "pdf" / "Propuesta_Evolucion_A3_USD1080_2026-09-28.pdf"

FOOTER = (
    '<div style="width:100%;padding:0 16mm;font-family:Arial,sans-serif;font-size:7.5pt;'
    'color:#6b6468;display:flex;justify-content:space-between;">'
    "<span>Propuesta de evolución · A3 Laboratorio Veterinario · 28 de septiembre de 2026</span>"
    '<span>Página <span class="pageNumber"></span> de <span class="totalPages"></span></span></div>'
)


def main() -> int:
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import sync_playwright

    PDF.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(channel="chrome")
        except Exception:
            browser = pw.chromium.launch()
        page = browser.new_page()
        page.goto(HTML.as_uri(), wait_until="load")
        try:
            page.wait_for_function("document.fonts.status === 'loaded'", timeout=8000)
        except PlaywrightError:
            pass
        page.pdf(
            path=str(PDF),
            format="A4",
            print_background=True,
            display_header_footer=True,
            header_template="<div></div>",
            footer_template=FOOTER,
            margin={"top": "14mm", "bottom": "18mm", "left": "16mm", "right": "16mm"},
        )
        browser.close()
    print(f"PDF: {PDF} ({PDF.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
