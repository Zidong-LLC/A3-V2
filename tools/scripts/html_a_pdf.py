"""Convierte un HTML de documento A3 en PDF A4, con pie y numeración de páginas.

Uso: python tools/scripts/html_a_pdf.py <html> <pdf> "<texto del pie>"
"""
import sys
from pathlib import Path


def _pie(texto: str) -> str:
    return (
        '<div style="width:100%;padding:0 16mm;font-family:Arial,sans-serif;font-size:7.5pt;'
        'color:#6b6468;display:flex;justify-content:space-between;">'
        f"<span>{texto}</span>"
        '<span>Página <span class="pageNumber"></span> de <span class="totalPages"></span></span></div>'
    )


def convertir(html: Path, pdf: Path, pie: str) -> None:
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import sync_playwright

    pdf.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(channel="chrome")
        except Exception:
            browser = pw.chromium.launch()
        page = browser.new_page()
        page.goto(html.resolve().as_uri(), wait_until="load")
        try:
            page.wait_for_function("document.fonts.status === 'loaded'", timeout=8000)
        except PlaywrightError:
            pass
        page.pdf(path=str(pdf), format="A4", print_background=True, display_header_footer=True,
                 header_template="<div></div>", footer_template=_pie(pie),
                 margin={"top": "14mm", "bottom": "18mm", "left": "16mm", "right": "16mm"})
        browser.close()
    print(f"PDF: {pdf} ({pdf.stat().st_size} bytes)")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit(__doc__)
    convertir(Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3])
