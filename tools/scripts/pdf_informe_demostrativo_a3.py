"""Convierte el informe demostrativo de A3 a PDF."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HTML = ROOT / "data" / "informe-demostrativo-a3.html"
PDF = ROOT / "Informe_Demostrativo_A3_Acuerdos_y_Plataforma.pdf"


def main() -> int:
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(channel="chrome")
        except Exception:
            browser = pw.chromium.launch()
        page = browser.new_page()
        page.goto(HTML.as_uri(), wait_until="load")
        try:
            page.wait_for_function("Array.from(document.images).every(function (i) { return i.complete; })", timeout=8000)
        except PlaywrightError:
            pass
        page.pdf(path=str(PDF), format="A4", print_background=True,
                 margin={"top": "0", "bottom": "0", "left": "0", "right": "0"})
        browser.close()
    assert PDF.stat().st_size > 100000
    print(f"PDF: {PDF} ({PDF.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
